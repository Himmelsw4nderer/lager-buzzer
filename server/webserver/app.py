#!/usr/bin/env python3
"""
LagerBuzzer Web Server
Kolpingjugend Edition - with Name & Enable/Disable Support
"""

import json
import logging
import os
import sys
import threading
import time
from collections import OrderedDict

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template, request

# Add current directory to path for database module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize database
from database import get_all_buzzers, get_buzzer, init_db, save_buzzer

app = Flask(__name__)

# Initialize database on startup
init_db()

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_BUZZ_TOPIC = os.getenv("MQTT_BUZZ_TOPIC", "lagerbuzzer/buzz")
MQTT_WINNER_TOPIC = os.getenv("MQTT_WINNER_TOPIC", "lagerbuzzer/winner")
WEB_PORT = int(os.getenv("WEB_PORT", 5000))

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger(__name__)

# ============================================================================
# Data Structures
# ============================================================================


class Buzzer:
    def __init__(self, client_id, ip_address=None):
        self.client_id = client_id
        self.ip_address = ip_address
        self.name = client_id  # Defaults to ID until renamed
        self.enabled = True  # Used to lock out wrong answers
        self.last_buzz_time = None
        self.buzz_count = 0
        self.color = None  # Custom color for this buzzer

    def to_dict(self):
        return {
            "client_id": self.client_id,
            "ip_address": self.ip_address,
            "name": self.name,
            "enabled": self.enabled,
            "buzz_count": self.buzz_count,
            "color": self.color,
        }


class BuzzEvent:
    def __init__(self, topic, payload, timestamp_received, buzzer_id):
        self.topic = topic
        self.payload = payload
        self.timestamp_received = timestamp_received
        self.buzzer_id = buzzer_id


# ============================================================================
# Global State
# ============================================================================

buzz_events = []
MAX_EVENTS = 100
buzzer_events_lock = threading.Lock()

buzzers = {}  # client_id -> Buzzer object
buzzers_lock = threading.Lock()


def load_buzzers_from_db():
    """Load all buzzers from the database into memory."""
    with buzzers_lock:
        db_buzzers = get_all_buzzers()
        for client_id, data in db_buzzers.items():
            if client_id not in buzzers:
                buzzer = Buzzer(client_id, data.get("ip_address"))
                buzzer.name = data.get("name", client_id)
                buzzer.enabled = bool(data.get("enabled", True))
                buzzer.buzz_count = int(data.get("buzz_count", 0))
                buzzer.color = data.get("color")
                buzzer.last_buzz_time = data.get("last_buzz_time")
                buzzers[client_id] = buzzer


# Load buzzers from database at startup
load_buzzers_from_db()

current_round = {
    "active": True,
    "started_at": time.time(),
    "buzzes": OrderedDict(),
    "winner": None,
    "locked": False,
}
round_lock = threading.Lock()

mqtt_client = None

# ============================================================================
# Helper Functions
# ============================================================================


def get_or_create_buzzer(client_id, ip_address=None):
    with buzzers_lock:
        if client_id not in buzzers:
            # Check if buzzer exists in database
            db_data = get_buzzer(client_id)
            if db_data:
                buzzer = Buzzer(client_id, db_data.get("ip_address") or ip_address)
                buzzer.name = db_data.get("name", client_id)
                buzzer.enabled = bool(db_data.get("enabled", True))
                buzzer.buzz_count = int(db_data.get("buzz_count", 0))
                buzzer.color = db_data.get("color")
                buzzer.last_buzz_time = db_data.get("last_buzz_time")
                buzzers[client_id] = buzzer
            else:
                buzzers[client_id] = Buzzer(client_id, ip_address)
                # Save new buzzer to database
                save_buzzer(
                    client_id=client_id,
                    ip_address=ip_address,
                    name=client_id,
                    enabled=True,
                    buzz_count=0,
                    color=None,
                    last_buzz_time=None,
                )
        else:
            # Update IP address if provided
            if ip_address and not buzzers[client_id].ip_address:
                buzzers[client_id].ip_address = ip_address
                save_buzzer(client_id=client_id, ip_address=ip_address)
        return buzzers[client_id]


def extract_buzzer_id(payload_dict, topic):
    for key in ["client_id", "buzzer_id", "mac", "ip", "name"]:
        if key in payload_dict:
            return str(payload_dict[key])
    return topic.split("/")[-1]


def add_buzz_event(topic, payload_dict, timestamp):
    buzzer_id = extract_buzzer_id(payload_dict, topic)
    buzzer_ip = payload_dict.get("ip", None)

    buzzer = get_or_create_buzzer(buzzer_id, buzzer_ip)
    buzzer.last_buzz_time = timestamp
    buzzer.buzz_count += 1

    # Save updated buzz count and last buzz time to database
    save_buzzer(
        client_id=buzzer_id, buzz_count=buzzer.buzz_count, last_buzz_time=timestamp
    )

    event = BuzzEvent(topic, payload_dict, timestamp, buzzer_id)

    with buzzer_events_lock:
        buzz_events.append(event)
        if len(buzz_events) > MAX_EVENTS:
            buzz_events.pop(0)

    # Core Logic: Ignore disabled buzzers and locked rounds
    with round_lock:
        if not current_round["active"] or current_round["locked"]:
            return event

        # If the buzzer is disabled (e.g. wrong answer in quiz), ignore their buzz
        if not buzzer.enabled:
            return event

        if buzzer_id not in current_round["buzzes"]:
            current_round["buzzes"][buzzer_id] = event
            if current_round["winner"] is None:
                current_round["winner"] = buzzer_id
                logger.info(f"🏆 Gewinner: {buzzer.name} ({buzzer_id})")
                # Publish winner notification to all buzzers
                publish_winner(buzzer_id)

    return event


# ============================================================================
# MQTT Callbacks
# ============================================================================


def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Verbunden mit MQTT Broker.")
        client.subscribe(MQTT_BUZZ_TOPIC, qos=0)


def on_mqtt_message(client, userdata, msg):
    try:
        now = time.time()
        payload_str = msg.payload.decode("utf-8").strip()
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = {"message": payload_str}
        add_buzz_event(msg.topic, data, now)
    except Exception as e:
        logger.error(f"Fehler: {e}")


def publish_winner(winner_id):
    """Publish winner notification to all buzzers."""
    if mqtt_client and mqtt_client.is_connected():
        payload = json.dumps({"winner": winner_id})
        result = mqtt_client.publish(MQTT_WINNER_TOPIC, payload, qos=0, retain=False)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Published winner: {winner_id} to {MQTT_WINNER_TOPIC}")
        else:
            logger.error(f"Failed to publish winner: {mqtt.error_string(result.rc)}")
    else:
        logger.warning("MQTT client not connected, cannot publish winner")


def setup_mqtt():
    global mqtt_client
    retries = 5
    retry_delay = 2

    for attempt in range(retries):
        try:
            mqtt_client = mqtt.Client()
            mqtt_client.on_connect = on_mqtt_connect
            mqtt_client.on_message = on_mqtt_message
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            mqtt_client.loop_start()
            logger.info(f"Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
            return
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(
                    f"MQTT connection failed (attempt {attempt + 1}/{retries}): {e}. Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"MQTT connection failed after {retries} attempts: {e}")
                # Create a dummy client to avoid None reference errors
                mqtt_client = None


# Initialize MQTT when module is loaded
setup_mqtt()


# ============================================================================
# Flask Endpoints
# ============================================================================


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def get_stats():
    with buzzers_lock:
        total_buzzers = len(buzzers)
    with round_lock:
        round_info = {
            "winner": current_round["winner"],
            "locked": current_round["locked"],
        }
    return jsonify(
        {
            "total_buzzers": total_buzzers,
            "mqtt_connected": mqtt_client.is_connected() if mqtt_client else False,
            "round": round_info,
        }
    )


@app.route("/api/buzzers", methods=["GET"])
def get_buzzers():
    with buzzers_lock:
        return jsonify({bid: b.to_dict() for bid, b in buzzers.items()})


@app.route("/api/buzzers/<client_id>", methods=["PUT"])
def update_buzzer(client_id):
    data = request.get_json() or {}
    with buzzers_lock:
        if client_id in buzzers:
            updated_fields = {}
            if "name" in data:
                buzzers[client_id].name = data["name"]
                updated_fields["name"] = data["name"]
            if "enabled" in data:
                buzzers[client_id].enabled = bool(data["enabled"])
                updated_fields["enabled"] = buzzers[client_id].enabled
            if "color" in data:
                buzzers[client_id].color = data["color"]
                updated_fields["color"] = data["color"]

            # Save to database
            if updated_fields:
                save_buzzer(
                    client_id=client_id,
                    name=data.get("name"),
                    enabled=data.get("enabled"),
                    color=data.get("color"),
                )

            return jsonify(buzzers[client_id].to_dict())
    return jsonify({"error": "Buzzer nicht gefunden"}), 404


@app.route("/api/round", methods=["GET", "POST"])
def manage_round():
    global current_round
    if request.method == "GET":
        with round_lock:
            return jsonify(
                {"winner": current_round["winner"], "locked": current_round["locked"]}
            )

    action = (request.get_json() or {}).get("action", "reset")
    with round_lock:
        if action == "reset":
            current_round["buzzes"].clear()
            current_round["winner"] = None
            current_round["locked"] = False
            # Publish empty winner to turn off all buzzer notifications
            publish_winner("")
        elif action == "lock":
            current_round["locked"] = True
        elif action == "clear_winner":
            current_round["winner"] = None
            current_round["locked"] = False
            # Publish empty winner to turn off all buzzer notifications
            publish_winner("")
    return jsonify({"status": "success"})


@app.route("/api/buzzers/enable_all", methods=["POST"])
def enable_all_buzzers():
    with buzzers_lock:
        for buzzer in buzzers.values():
            buzzer.enabled = True
            # Save to database
            save_buzzer(client_id=buzzer.client_id, enabled=True)
    return jsonify({"status": "success", "message": "All buzzers enabled"})


@app.route("/api/round/buzzes", methods=["GET"])
def get_round_buzzes():
    with round_lock:
        buzzes_order = list(current_round["buzzes"].keys())
    return jsonify({"buzzes": buzzes_order})


if __name__ == "__main__":
    setup_mqtt()
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True)
