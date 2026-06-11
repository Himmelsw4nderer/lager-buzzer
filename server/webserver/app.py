#!/usr/bin/env python3
"""
LagerBuzzer Web Server - Architecture-Compatible
Flask-based web interface tailored for direct MQTT button messages.
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
WEB_PORT = int(os.getenv("WEB_PORT", 5000))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [WebServer] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================================
# Data Structures
# ============================================================================


class Buzzer:
    """Represents a buzzer device."""

    def __init__(self, client_id, ip_address=None):
        self.client_id = client_id
        self.ip_address = ip_address
        self.name = client_id
        self.enabled = True
        self.locked = False
        self.last_buzz_time = None
        self.buzz_count = 0

    def to_dict(self):
        return {
            "client_id": self.client_id,
            "ip_address": self.ip_address,
            "name": self.name,
            "enabled": self.enabled,
            "locked": self.locked,
            "buzz_count": self.buzz_count,
            "last_buzz_time": self.last_buzz_time,
        }


class BuzzEvent:
    """Represents a clean buzz event."""

    def __init__(self, topic, payload, timestamp_received, buzzer_id):
        self.topic = topic
        self.payload = payload
        self.timestamp_received = timestamp_received
        self.buzzer_id = buzzer_id

    def to_dict(self):
        return {
            "topic": self.topic,
            "payload": self.payload,
            "timestamp_received": self.timestamp_received,
            "buzzer_id": self.buzzer_id,
        }


# ============================================================================
# Global State
# ============================================================================

buzz_events = []
MAX_EVENTS = 100
buzzer_events_lock = threading.Lock()

buzzers = {}  # client_id -> Buzzer object
buzzers_lock = threading.Lock()

current_round = {
    "active": True,  # Default to True so things work immediately
    "started_at": time.time(),
    "buzzes": OrderedDict(),  # buzzer_id -> BuzzEvent
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
            buzzers[client_id] = Buzzer(client_id, ip_address)
        if ip_address and not buzzers[client_id].ip_address:
            buzzers[client_id].ip_address = ip_address
        return buzzers[client_id]


def extract_buzzer_id(payload_dict, topic):
    """Safely finds identity keys matching standard client payloads."""
    for key in ["client_id", "buzzer_id", "mac", "ip", "name"]:
        if key in payload_dict:
            return str(payload_dict[key])
    # Fallback to topic name elements if payload is empty
    return topic.split("/")[-1]


def add_buzz_event(topic, payload_dict, timestamp):
    buzzer_id = extract_buzzer_id(payload_dict, topic)
    buzzer_ip = payload_dict.get("ip", None)

    # Track metrics
    buzzer = get_or_create_buzzer(buzzer_id, buzzer_ip)
    buzzer.last_buzz_time = timestamp
    buzzer.buzz_count += 1

    event = BuzzEvent(topic, payload_dict, timestamp, buzzer_id)

    with buzzer_events_lock:
        buzz_events.append(event)
        if len(buzz_events) > MAX_EVENTS:
            buzz_events.pop(0)

    # Round logic evaluation
    with round_lock:
        if not current_round["active"] or current_round["locked"]:
            return event

        if buzzer.locked or not buzzer.enabled:
            return event

        if buzzer_id not in current_round["buzzes"]:
            current_round["buzzes"][buzzer_id] = event
            if current_round["winner"] is None:
                current_round["winner"] = buzzer_id
                logger.info(f"🏆 Winner determined: {buzzer_id}")

    return event


# ============================================================================
# MQTT Callbacks
# ============================================================================


def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to MQTT broker at {MQTT_BROKER}")
        client.subscribe(MQTT_BUZZ_TOPIC, qos=0)
    else:
        logger.error(f"MQTT connection failed with code {rc}")


def on_mqtt_message(client, userdata, msg):
    try:
        now = time.time()
        payload_str = msg.payload.decode("utf-8").strip()

        # Accept raw text strings OR structured JSON string payloads
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = {"message": payload_str}

        add_buzz_event(msg.topic, data, now)
    except Exception as e:
        logger.error(f"Error handling incoming message: {e}")


def setup_mqtt():
    global mqtt_client
    try:
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_message = on_mqtt_message
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        logger.error(f"Failed to boot MQTT: {e}")
        return False


# ============================================================================
# Flask Endpoints
# ============================================================================


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def get_stats():
    with buzzer_events_lock:
        total_events = len(buzz_events)
    with buzzers_lock:
        total_buzzers = len(buzzers)
        enabled_buzzers = sum(1 for b in buzzers.values() if b.enabled)
    with round_lock:
        round_info = {
            "active": current_round["active"],
            "buzz_count": len(current_round["buzzes"]),
            "winner": current_round["winner"],
            "locked": current_round["locked"],
        }
    return jsonify(
        {
            "total_events": total_events,
            "total_buzzers": total_buzzers,
            "enabled_buzzers": enabled_buzzers,
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
            return jsonify(buzzers[client_id].to_dict())
    return jsonify({"error": "Not Found"}), 404


@app.route("/api/round", methods=["GET", "POST"])
def manage_round():
    global current_round
    if request.method == "GET":
        with round_lock:
            return jsonify(
                {
                    "active": current_round["active"],
                    "winner": current_round["winner"],
                    "locked": current_round["locked"],
                    "buzzes": list(current_round["buzzes"].keys()),
                }
            )

    action = (request.get_json() or {}).get("action", "reset")
    with round_lock:
        if action == "reset":
            current_round["buzzes"].clear()
            current_round["winner"] = None
            current_round["locked"] = False
            current_round["active"] = True
        elif action == "lock":
            current_round["locked"] = True
    return jsonify({"status": "success"})


if __name__ == "__main__":
    setup_mqtt()
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True)
