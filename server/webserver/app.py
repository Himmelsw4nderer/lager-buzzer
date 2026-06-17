#!/usr/bin/env python3
"""
LagerBuzzer Web Server
Kolpingjugend Edition - with Name & Enable/Disable Support
"""

import json
import logging
import os
import threading
import time
from collections import OrderedDict

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_BUZZ_TOPIC = os.getenv("MQTT_BUZZ_TOPIC", "lagerbuzzer/buzz")
MQTT_WINNER_TOPIC = os.getenv("MQTT_WINNER_TOPIC", "lagerbuzzer/winner")
WEB_PORT = int(os.getenv("WEB_PORT", 5000))

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger(__name__)

# Import database module
from db import (
    create_or_update_buzzer as db_create_or_update_buzzer,
)
from db import (
    get_all_buzzers as db_get_all_buzzers,
)
from db import (
    get_buzzer as db_get_buzzer,
)
from db import (
    get_db_cursor,
)
from db import (
    increment_buzz_count as db_increment_buzz_count,
)
from db import (
    update_buzzer_field as db_update_buzzer_field,
)

# ============================================================================
# Data Structures
# ============================================================================


class Buzzer:
    def __init__(
        self,
        client_id,
        ip_address=None,
        name=None,
        enabled=True,
        buzz_count=0,
        color=None,
    ):
        self.client_id = client_id
        self.ip_address = ip_address
        self.name = name or client_id  # Defaults to ID until renamed
        self.enabled = enabled  # Used to lock out wrong answers
        self.last_buzz_time = None
        self.buzz_count = buzz_count
        self.color = color  # Custom color for this buzzer

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

current_round = {
    "active": True,
    "started_at": time.time(),
    "buzzes": OrderedDict(),
    "winner": None,
    "locked": False,
}
round_lock = threading.Lock()

mqtt_client = None


def load_buzzers_from_db():
    """Load all buzzers from database into memory on startup."""
    global buzzers
    with buzzers_lock:
        all_buzzers = db_get_all_buzzers()
        buzzers = {}
        for client_id, buzzer_data in all_buzzers.items():
            buzzers[client_id] = Buzzer(
                client_id=buzzer_data["client_id"],
                ip_address=buzzer_data["ip_address"],
                name=buzzer_data["name"],
                enabled=buzzer_data["enabled"],
                buzz_count=buzzer_data["buzz_count"],
                color=buzzer_data["color"],
            )


# ============================================================================
# Helper Functions
# ============================================================================


def get_or_create_buzzer(client_id, ip_address=None):
    """Get or create a buzzer, syncing with database."""
    with buzzers_lock:
        # First check in-memory cache
        if client_id in buzzers:
            # Update IP address if provided and not set
            if ip_address and not buzzers[client_id].ip_address:
                buzzers[client_id].ip_address = ip_address
                # Also update in database
                db_update_buzzer_field(client_id, "ip_address", ip_address)
            return buzzers[client_id]

        # Check database
        db_buzzer = db_get_buzzer(client_id)
        if db_buzzer:
            # Load from database into memory
            buzzers[client_id] = Buzzer(
                client_id=db_buzzer["client_id"],
                ip_address=db_buzzer["ip_address"] or ip_address,
                name=db_buzzer["name"],
                enabled=db_buzzer["enabled"],
                buzz_count=db_buzzer["buzz_count"],
                color=db_buzzer["color"],
            )
            # Update IP if provided
            if ip_address and not buzzers[client_id].ip_address:
                buzzers[client_id].ip_address = ip_address
                db_update_buzzer_field(client_id, "ip_address", ip_address)
            return buzzers[client_id]

        # Create new buzzer in both memory and database
        new_buzzer = Buzzer(client_id, ip_address)
        db_create_or_update_buzzer(
            client_id=client_id,
            ip_address=ip_address,
            name=client_id,
            enabled=True,
            buzz_count=0,
            color=None,
        )
        buzzers[client_id] = new_buzzer
        return new_buzzer


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

    # Update buzz count in database
    db_increment_buzz_count(buzzer_id)

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
            # Load buzzers from database after successful MQTT connection
            load_buzzers_from_db()
            logger.info(f"Loaded {len(buzzers)} buzzers from database")
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
                # Still try to load buzzers from database
                load_buzzers_from_db()
                logger.info(f"Loaded {len(buzzers)} buzzers from database")


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
        # If buzzer not in memory, try to load from database
        if client_id not in buzzers:
            db_buzzer = db_get_buzzer(client_id)
            if db_buzzer:
                buzzers[client_id] = Buzzer(
                    client_id=db_buzzer["client_id"],
                    ip_address=db_buzzer["ip_address"],
                    name=db_buzzer["name"],
                    enabled=db_buzzer["enabled"],
                    buzz_count=db_buzzer["buzz_count"],
                    color=db_buzzer["color"],
                )
            else:
                return jsonify({"error": "Buzzer nicht gefunden"}), 404

        if "name" in data:
            buzzers[client_id].name = data["name"]
            db_update_buzzer_field(client_id, "name", data["name"])
        if "enabled" in data:
            buzzers[client_id].enabled = bool(data["enabled"])
            db_update_buzzer_field(client_id, "enabled", bool(data["enabled"]))
        if "color" in data:
            buzzers[client_id].color = data["color"]
            db_update_buzzer_field(client_id, "color", data["color"])
        return jsonify(buzzers[client_id].to_dict())


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
    # Update all buzzers in database directly
    with get_db_cursor() as cursor:
        cursor.execute("UPDATE buzzers SET enabled = 1, updated_at = CURRENT_TIMESTAMP")

    # Also update in-memory cache
    with buzzers_lock:
        for buzzer in buzzers.values():
            buzzer.enabled = True

    return jsonify({"status": "success", "message": "All buzzers enabled"})


@app.route("/api/round/buzzes", methods=["GET"])
def get_round_buzzes():
    with round_lock:
        buzzes_order = list(current_round["buzzes"].keys())
    return jsonify({"buzzes": buzzes_order})


if __name__ == "__main__":
    setup_mqtt()
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True)
