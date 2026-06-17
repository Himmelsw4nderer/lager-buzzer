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
from pathlib import Path

import paho.mqtt.client as mqtt

# Import database functions
from database import get_all_buzzers, get_buzzer, get_db_path, init_db, save_buzzer
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

# ============================================================================
# Data Structures
# ============================================================================


class Buzzer:
    def __init__(
        self,
        client_id,
        ip_address=None,
        name=None,
        color=None,
        enabled=True,
        buzz_count=0,
        last_buzz_time=None,
    ):
        self.client_id = client_id
        self.ip_address = ip_address
        self.name = (
            name if name is not None else client_id
        )  # Defaults to ID until renamed
        self.enabled = enabled  # Used to lock out wrong answers
        self.last_buzz_time = last_buzz_time
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

    def save(self):
        """Persist this buzzer's data to the database."""
        db_path = get_db_path()
        return save_buzzer(
            db_path=db_path,
            client_id=self.client_id,
            name=self.name,
            color=self.color,
            enabled=self.enabled,
            ip_address=self.ip_address,
            buzz_count=self.buzz_count,
            last_buzz_time=self.last_buzz_time,
        )


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
mqtt_setup_lock = threading.Lock()

# Database path (computed once at startup)
DB_PATH = get_db_path()

# ============================================================================
# Database Functions
# ============================================================================


def load_buzzers_from_db():
    """Load all buzzers from the database into memory."""
    global buzzers
    db_buzzers = get_all_buzzers(DB_PATH)
    with buzzers_lock:
        for client_id, db_data in db_buzzers.items():
            if client_id not in buzzers:
                buzzers[client_id] = Buzzer(
                    client_id=db_data["client_id"],
                    ip_address=db_data.get("ip_address"),
                    name=db_data["name"],
                    color=db_data.get("color"),
                    enabled=bool(db_data["enabled"]),
                    buzz_count=db_data.get("buzz_count", 0),
                    last_buzz_time=db_data.get("last_buzz_time"),
                )
    logger.info(f"Loaded {len(db_buzzers)} buzzers from database")


# ============================================================================
# Helper Functions
# ============================================================================


def get_or_create_buzzer(client_id, ip_address=None):
    with buzzers_lock:
        # First check if buzzer is already in memory
        if client_id in buzzers:
            if ip_address and not buzzers[client_id].ip_address:
                buzzers[client_id].ip_address = ip_address
                buzzers[client_id].save()
            return buzzers[client_id]

        # Try to load from database
        db_path = get_db_path()
        db_buzzer = get_buzzer(db_path, client_id)

        if db_buzzer:
            # Create Buzzer object from database data
            buzzer = Buzzer(
                client_id=db_buzzer["client_id"],
                ip_address=ip_address or db_buzzer.get("ip_address"),
                name=db_buzzer["name"],
                color=db_buzzer.get("color"),
                enabled=bool(db_buzzer["enabled"]),
                buzz_count=db_buzzer.get("buzz_count", 0),
                last_buzz_time=db_buzzer.get("last_buzz_time"),
            )
        else:
            # Create new buzzer with defaults
            buzzer = Buzzer(client_id, ip_address)
            buzzer.save()  # Persist the new buzzer to database

        buzzers[client_id] = buzzer
        return buzzer


def extract_buzzer_id(payload_dict, topic):
    for key in ["client_id", "buzzer_id", "mac", "ip"]:
        if key in payload_dict:
            return str(payload_dict[key])
    return topic.split("/")[-1]


def add_buzz_event(topic, payload_dict, timestamp):
    buzzer_id = extract_buzzer_id(payload_dict, topic)
    buzzer_ip = payload_dict.get("ip", None)

    with buzzers_lock:
        buzzer = get_or_create_buzzer(buzzer_id, buzzer_ip)
        buzzer.last_buzz_time = timestamp
        buzzer.buzz_count += 1
        buzzer.save()  # Persist the updated buzz count and timestamp

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

    # Use lock to prevent concurrent setup attempts
    with mqtt_setup_lock:
        # If MQTT is already set up and connected, don't reinitialize
        if mqtt_client is not None and mqtt_client.is_connected():
            return

        # If MQTT client exists but is disconnected, try to reconnect
        if mqtt_client is not None and not mqtt_client.is_connected():
            try:
                logger.info("MQTT disconnected, attempting to reconnect...")
                mqtt_client.reconnect()
                return
            except Exception as e:
                logger.warning(
                    f"MQTT reconnect failed: {e}. Will retry with new client."
                )
                mqtt_client = None

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
                    logger.error(
                        f"MQTT connection failed after {retries} attempts: {e}"
                    )
                    # Create a dummy client to avoid None reference errors
                    mqtt_client = None


def check_mqtt_connection():
    """Periodically check MQTT connection and reconnect if needed."""
    while True:
        time.sleep(30)  # Check every 30 seconds
        if mqtt_client is None or not mqtt_client.is_connected():
            setup_mqtt()


# Initialize database
init_db()

# Load existing buzzers from database
load_buzzers_from_db()

# Initialize MQTT when module is loaded
setup_mqtt()

# Start background thread to monitor MQTT connection
mqtt_monitor_thread = threading.Thread(target=check_mqtt_connection, daemon=True)
mqtt_monitor_thread.start()


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
            if "name" in data:
                buzzers[client_id].name = data["name"]
            if "enabled" in data:
                buzzers[client_id].enabled = bool(data["enabled"])
            if "color" in data:
                buzzers[client_id].color = data["color"]
            # Save changes to database
            buzzers[client_id].save()
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
            buzzer.save()  # Persist the change to database
    return jsonify({"status": "success", "message": "All buzzers enabled"})


@app.route("/api/round/buzzes", methods=["GET"])
def get_round_buzzes():
    with round_lock:
        buzzes_order = list(current_round["buzzes"].keys())
    return jsonify({"buzzes": buzzes_order})


if __name__ == "__main__":
    setup_mqtt()
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True)
