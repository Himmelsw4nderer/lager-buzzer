#!/usr/bin/env python3
"""
LagerBuzzer Web Server
Flask-based web interface that displays buzz events from MQTT
"""

import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
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

# Store buzz events (thread-safe with lock)
buzz_events = []
MAX_EVENTS = 100  # Keep last 100 events
events_lock = threading.Lock()

# MQTT client
mqtt_client = None


def add_buzz_event(event):
    """Add a buzz event to the list."""
    with events_lock:
        buzz_events.append(event)
        if len(buzz_events) > MAX_EVENTS:
            buzz_events.pop(0)


def on_mqtt_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker."""
    if rc == 0:
        logger.info(f"Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_BUZZ_TOPIC, qos=0)
        logger.info(f"Subscribed to topic: {MQTT_BUZZ_TOPIC}")
    else:
        logger.error(f"MQTT connection failed with code {rc}")


def on_mqtt_message(client, userdata, msg):
    """Callback when receiving an MQTT message."""
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        # Create event with metadata
        event = {"topic": msg.topic, "payload": data, "timestamp_received": time.time()}

        add_buzz_event(event)
        logger.debug(f"Received buzz: {json.dumps(data, indent=2)}")

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON payload: {payload}")
    except Exception as e:
        logger.error(f"Error processing MQTT message: {e}")


def setup_mqtt():
    """Set up MQTT client and start connection."""
    global mqtt_client

    mqtt_client = mqtt.Client("webserver-subscriber")
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message

    # Enable logging
    mqtt_client.enable_logger(logger)

    try:
        logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        logger.error(f"Failed to connect to MQTT: {e}")
        return False


@app.route("/")
def index():
    """Main page showing buzz events."""
    return render_template("index.html")


@app.route("/api/events")
def get_events():
    """API endpoint to get buzz events as JSON."""
    with events_lock:
        # Return a copy of the events list
        events_copy = list(buzz_events)

    # Reverse to show newest first
    events_copy.reverse()
    return jsonify(events_copy)


@app.route("/api/stats")
def get_stats():
    """API endpoint to get statistics."""
    with events_lock:
        total_events = len(buzz_events)

    return jsonify(
        {
            "total_events": total_events,
            "mqtt_connected": mqtt_client.is_connected() if mqtt_client else False,
            "subscribed_to": MQTT_BUZZ_TOPIC,
        }
    )


def main():
    # Setup MQTT
    if not setup_mqtt():
        logger.warning("Starting without MQTT connection")

    # Start Flask app
    logger.info(f"Starting web server on port {WEB_PORT}")
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
