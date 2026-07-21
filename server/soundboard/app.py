#!/usr/bin/env python3
"""
LagerBuzzer Soundboard Service
Plays a configured sound file on the Raspberry Pi when a buzzer assigned
to the currently active mode is pressed.
"""

import json
import logging
import os
import subprocess
import threading
import time

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request

app = Flask(__name__)

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_BUZZ_TOPIC = os.getenv("MQTT_BUZZ_TOPIC", "lagerbuzzer/buzz")
WEB_PORT = int(os.getenv("WEB_PORT", 5000))
MODES_FILE = os.getenv("MODES_FILE", "modes.json")
SOUNDS_DIR = os.getenv("SOUNDS_DIR", "sounds")
PLAYER_CMD = os.getenv("PLAYER_CMD", "mpg123")

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger(__name__)

# ============================================================================
# Global State
# ============================================================================

# modes: {name: {"name": ..., "buzzer_ids": [...], "sound_file": "..."}}
modes = {}
active_mode = None
mode_lock = threading.Lock()

mqtt_client = None

# ============================================================================
# Helper Functions
# ============================================================================


def load_modes():
    global modes
    try:
        with open(MODES_FILE) as f:
            data = json.load(f)
        modes = {m["name"]: m for m in data.get("modes", [])}
        logger.info(f"Loaded {len(modes)} mode(s) from {MODES_FILE}: {list(modes.keys())}")
    except FileNotFoundError:
        logger.warning(f"{MODES_FILE} not found, starting with no modes configured")
        modes = {}


def extract_buzzer_id(payload_dict, topic):
    for key in ["client_id", "buzzer_id", "mac", "ip", "name"]:
        if key in payload_dict:
            return str(payload_dict[key])
    return topic.split("/")[-1]


def play_sound(sound_file):
    path = os.path.join(SOUNDS_DIR, sound_file)
    if not os.path.isfile(path):
        logger.error(f"Sound file not found: {path}")
        return
    logger.info(f"Playing {path}")
    subprocess.Popen(
        [PLAYER_CMD, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


# ============================================================================
# MQTT Callbacks
# ============================================================================


def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Verbunden mit MQTT Broker.")
        client.subscribe(MQTT_BUZZ_TOPIC, qos=0)


def on_mqtt_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8").strip()
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = {"message": payload_str}

        buzzer_id = extract_buzzer_id(data, msg.topic)

        with mode_lock:
            mode = modes.get(active_mode) if active_mode else None

        if mode and buzzer_id in mode["buzzer_ids"]:
            play_sound(mode["sound_file"])
    except Exception as e:
        logger.error(f"Fehler: {e}")


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
                mqtt_client = None


# Initialize modes and MQTT when module is loaded
load_modes()
setup_mqtt()

# ============================================================================
# Flask Endpoints
# ============================================================================


@app.route("/api/modes", methods=["GET"])
def get_modes():
    with mode_lock:
        return jsonify({"modes": list(modes.values()), "active_mode": active_mode})


@app.route("/api/mode/active", methods=["POST"])
def set_active_mode():
    global active_mode
    data = request.get_json() or {}
    name = data.get("name")
    with mode_lock:
        if name is not None and name not in modes:
            return jsonify({"error": f"Unknown mode: {name}"}), 404
        active_mode = name
    logger.info(f"Active mode set to: {active_mode}")
    return jsonify({"status": "success", "active_mode": active_mode})


@app.route("/api/status", methods=["GET"])
def get_status():
    with mode_lock:
        return jsonify(
            {
                "mqtt_connected": mqtt_client.is_connected() if mqtt_client else False,
                "active_mode": active_mode,
                "modes": list(modes.keys()),
            }
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True)
