#!/usr/bin/env python3
"""
LagerBuzzer Web Server - Enhanced
Flask-based web interface with full buzzer management system
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

# ============================================================================
# Data Structures
# ============================================================================


class Buzzer:
    """Represents a buzzer device."""

    def __init__(self, client_id, ip_address=None):
        self.client_id = client_id
        self.ip_address = ip_address
        self.name = client_id  # Default name is client_id
        self.enabled = True  # Initially enabled
        self.locked = False  # Not locked by default
        self.last_buzz_time = None
        self.buzz_count = 0
        self.roundtrip_times = []  # List of RTT measurements

    def to_dict(self):
        return {
            "client_id": self.client_id,
            "ip_address": self.ip_address,
            "name": self.name,
            "enabled": self.enabled,
            "locked": self.locked,
            "buzz_count": self.buzz_count,
            "avg_rtt": sum(self.roundtrip_times) / len(self.roundtrip_times)
            if self.roundtrip_times
            else 0,
        }


class BuzzEvent:
    """Represents a buzz event with calculated timing."""

    def __init__(self, topic, payload, timestamp_received, buzzer_id=None):
        self.topic = topic
        self.payload = payload
        self.timestamp_received = timestamp_received
        self.buzzer_id = buzzer_id

        # Calculate corrected timestamp and RTT
        self.corrected_timestamp = self._calculate_corrected_timestamp()
        self.roundtrip_time = self._calculate_rtt()

    def _calculate_rtt(self):
        """Calculate roundtrip time in milliseconds."""
        try:
            T1 = self.payload.get(
                "time_sync", 0
            )  # Server unix timestamp when time_sync was sent
            T2 = self.payload.get(
                "time_sync_received", 0
            )  # Client millis() when time_sync received
            T4 = self.payload.get(
                "send_timestamp", 0
            )  # Client millis() when buzz was sent
            T5 = self.timestamp_received  # Server unix timestamp when buzz received

            if T1 == 0 or T5 == 0:
                return 0

            # Convert all to milliseconds for calculation
            # T1 is in seconds, so T1_ms = T1 * 1000
            # T5 is in seconds, so T5_ms = T5 * 1000
            T1_ms = T1 * 1000
            T5_ms = T5 * 1000

            # Time elapsed on client between sync receive and buzz send
            client_elapsed = T4 - T2

            # Time elapsed on server between sync send and buzz receive
            server_elapsed = T5_ms - T1_ms

            # RTT = server_elapsed - client_elapsed
            # This gives us the roundtrip time
            rtt_ms = server_elapsed - client_elapsed

            return max(0, rtt_ms)
        except Exception as e:
            logger.error(f"Error calculating RTT: {e}")
            return 0

    def _calculate_corrected_timestamp(self):
        """Calculate the corrected button press timestamp in unix seconds."""
        try:
            T1 = self.payload.get("time_sync", 0)  # Server unix timestamp
            T2 = self.payload.get("time_sync_received", 0)  # Client millis()
            T3 = self.payload.get(
                "button_press", 0
            )  # Client millis() - actual button press
            T4 = self.payload.get("send_timestamp", 0)  # Client millis() - when sent
            T5 = self.timestamp_received  # Server unix timestamp - when received

            if T1 == 0 or T5 == 0:
                return T5

            # Calculate one-way latency estimate
            # client_elapsed = time from sync receive to buzz send (in client time)
            client_elapsed = (T4 - T2) / 1000.0  # Convert to seconds

            # server_elapsed = time from sync send to buzz receive (in server time)
            server_elapsed = T5 - T1

            # One-way latency = (server_elapsed - client_elapsed) / 2
            latency = (server_elapsed - client_elapsed) / 2

            # Time from sync receive to button press (in client time)
            button_offset = (T3 - T2) / 1000.0  # Convert to seconds

            # Corrected button press time = T1 + button_offset - latency
            # T1 is when sync was sent
            # button_offset is how long after sync receive the button was pressed
            # latency is how long it took for messages to travel
            corrected = T1 + button_offset - latency

            return corrected
        except Exception as e:
            logger.error(f"Error calculating corrected timestamp: {e}")
            return self.timestamp_received

    def to_dict(self):
        return {
            "topic": self.topic,
            "payload": self.payload,
            "timestamp_received": self.timestamp_received,
            "buzzer_id": self.buzzer_id,
            "corrected_timestamp": self.corrected_timestamp,
            "roundtrip_time_ms": round(self.roundtrip_time, 2),
        }


# ============================================================================
# Global State
# ============================================================================

# Store buzz events (thread-safe with lock)
buzz_events = []
MAX_EVENTS = 200
buzzer_events_lock = threading.Lock()

# Buzzer registry
buzzers = {}  # client_id -> Buzzer object
buzzers_lock = threading.Lock()

# Current round state
current_round = {
    "active": False,
    "started_at": None,
    "buzzes": OrderedDict(),  # buzzer_id -> BuzzEvent
    "winner": None,
    "locked": False,
}
round_lock = threading.Lock()

# MQTT client
mqtt_client = None


# ============================================================================
# Helper Functions
# ============================================================================


def get_buzzer_by_id(client_id):
    """Get or create a buzzer by client ID."""
    with buzzers_lock:
        if client_id not in buzzers:
            buzzers[client_id] = Buzzer(client_id)
        return buzzers[client_id]


def get_buzzer_by_ip(ip_address):
    """Find buzzer by IP address."""
    with buzzers_lock:
        for buzzer in buzzers.values():
            if buzzer.ip_address == ip_address:
                return buzzer
        return None


def extract_buzzer_id_from_payload(payload_dict):
    """Extract buzzer ID from the payload dictionary."""
    # Try various fields that might identify the buzzer
    if "mac" in payload_dict:
        return str(payload_dict["mac"])
    elif "client_id" in payload_dict:
        return str(payload_dict["client_id"])
    elif "buzzer_id" in payload_dict:
        return str(payload_dict["buzzer_id"])
    elif "ip" in payload_dict:
        return str(payload_dict["ip"])

    # If no explicit ID, create one based on the data
    # The BuzzSync library sends: time_sync, time_sync_received, button_press, send_timestamp
    # We can use a combination of these as a pseudo-unique identifier
    import hashlib

    unique_str = f"{payload_dict.get('time_sync', '')}-{payload_dict.get('time_sync_received', '')}-{payload_dict.get('send_timestamp', '')}"
    return f"buzzer-{hashlib.md5(unique_str.encode()).hexdigest()[:8]}"


def add_buzz_event(event_data, buzzer_id=None):
    """Add a buzz event to the list and update round state."""
    event = BuzzEvent(
        topic=event_data["topic"],
        payload=event_data["payload"],
        timestamp_received=event_data["timestamp_received"],
        buzzer_id=buzzer_id,
    )

    with buzzer_events_lock:
        buzz_events.append(event)
        if len(buzz_events) > MAX_EVENTS:
            buzz_events.pop(0)

    # Update buzzer stats
    if buzzer_id:
        buzzer = get_buzzer_by_id(buzzer_id)
        buzzer.last_buzz_time = event.timestamp_received
        buzzer.buzz_count += 1
        if event.roundtrip_time > 0:
            buzzer.roundtrip_times.append(event.roundtrip_time)
            if len(buzzer.roundtrip_times) > 10:
                buzzer.roundtrip_times.pop(0)

    # Handle round logic
    handle_buzz_in_round(event, buzzer_id)

    return event


def handle_buzz_in_round(event, buzzer_id):
    """Handle a buzz event in the context of the current round."""
    with round_lock:
        if not current_round["active"]:
            return

        if current_round["locked"]:
            logger.info(f"Round is locked, ignoring buzz from {buzzer_id}")
            return

        # Check if buzzer is locked or disabled
        if buzzer_id:
            buzzer = get_buzzer_by_id(buzzer_id)
            if buzzer.locked or not buzzer.enabled:
                logger.info(f"Buzzer {buzzer_id} is locked or disabled, ignoring buzz")
                return

        # Add to round
        current_round["buzzes"][buzzer_id or "unknown"] = event

        # Determine winner based on corrected timestamp
        if current_round["winner"] is None:
            # First buzz is the winner
            current_round["winner"] = buzzer_id or "unknown"
            logger.info(
                f"First buzz! Winner: {current_round['winner']} at {event.corrected_timestamp}"
            )
        else:
            # Compare corrected timestamps
            winner_event = current_round["buzzes"][current_round["winner"]]
            if event.corrected_timestamp < winner_event.corrected_timestamp:
                current_round["winner"] = buzzer_id or "unknown"
                logger.info(
                    f"New winner: {current_round['winner']} at {event.corrected_timestamp} (was {winner_event.buzzer_id} at {winner_event.corrected_timestamp})"
                )


def reset_round():
    """Reset the current round."""
    with round_lock:
        current_round["active"] = False
        current_round["started_at"] = None
        current_round["buzzes"].clear()
        current_round["winner"] = None
        current_round["locked"] = False


def start_round():
    """Start a new round."""
    with round_lock:
        reset_round()
        current_round["active"] = True
        current_round["started_at"] = time.time()
        logger.info("New round started")


def lock_round():
    """Lock the current round (no more buzzes accepted)."""
    with round_lock:
        current_round["locked"] = True
        logger.info("Round locked")


def unlock_round():
    """Unlock the current round."""
    with round_lock:
        current_round["locked"] = False
        logger.info("Round unlocked")


# ============================================================================
# MQTT Callbacks
# ============================================================================


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

        # Extract buzzer ID and IP
        buzzer_id = extract_buzzer_id_from_payload(data)
        buzzer_ip = data.get("ip")

        # Get or create buzzer
        buzzer = get_buzzer_by_id(buzzer_id)

        # Update buzzer IP if available
        if buzzer_ip and not buzzer.ip_address:
            buzzer.ip_address = buzzer_ip

        # Create event with metadata
        event_data = {
            "topic": msg.topic,
            "payload": data,
            "timestamp_received": time.time(),
        }

        # Add event
        event = add_buzz_event(event_data, buzzer_id)

        logger.debug(f"Received buzz from {buzzer_id}")
        logger.debug(f"  Payload: {json.dumps(data, indent=2)}")
        logger.debug(f"  Corrected timestamp: {event.corrected_timestamp:.6f}")
        logger.debug(f"  Roundtrip time: {event.roundtrip_time:.2f}ms")

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON payload: {payload}")
    except Exception as e:
        logger.error(f"Error processing MQTT message: {e}")
        import traceback

        logger.error(traceback.format_exc())


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


# ============================================================================
# Flask Routes
# ============================================================================


@app.route("/")
def index():
    """Main page showing buzz events and management interface."""
    return render_template("index.html")


@app.route("/api/events")
def get_events():
    """API endpoint to get buzz events as JSON."""
    with buzzer_events_lock:
        events_copy = list(buzz_events)

    # Reverse to show newest first
    events_copy.reverse()

    return jsonify([e.to_dict() for e in events_copy])


@app.route("/api/stats")
def get_stats():
    """API endpoint to get statistics."""
    with buzzer_events_lock:
        total_events = len(buzz_events)

    with buzzers_lock:
        total_buzzers = len(buzzers)
        enabled_buzzers = sum(1 for b in buzzers.values() if b.enabled)

    with round_lock:
        round_info = {
            "active": current_round["active"],
            "started_at": current_round["started_at"],
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
            "subscribed_to": MQTT_BUZZ_TOPIC,
            "round": round_info,
        }
    )


@app.route("/api/buzzers", methods=["GET"])
def get_buzzers():
    """Get list of all registered buzzers."""
    with buzzers_lock:
        return jsonify({kid: b.to_dict() for kid, b in buzzers.items()})


@app.route("/api/buzzers/<client_id>", methods=["GET", "PUT", "DELETE"])
def manage_buzzer(client_id):
    """Manage a specific buzzer."""
    if request.method == "GET":
        buzzer = get_buzzer_by_id(client_id)
        if buzzer:
            return jsonify(buzzer.to_dict())
        return jsonify({"error": "Buzzer not found"}), 404

    elif request.method == "PUT":
        data = request.get_json()
        buzzer = get_buzzer_by_id(client_id)

        if not buzzer:
            return jsonify({"error": "Buzzer not found"}), 404

        if "name" in data:
            buzzer.name = data["name"]
        if "enabled" in data:
            buzzer.enabled = bool(data["enabled"])
        if "locked" in data:
            buzzer.locked = bool(data["locked"])
        if "ip_address" in data:
            buzzer.ip_address = data["ip_address"]

        return jsonify(buzzer.to_dict())

    elif request.method == "DELETE":
        with buzzers_lock:
            if client_id in buzzers:
                del buzzers[client_id]
                return jsonify({"message": "Buzzer deleted"})
        return jsonify({"error": "Buzzer not found"}), 404


@app.route("/api/buzzers/<client_id>/lock", methods=["POST"])
def lock_buzzer(client_id):
    """Lock a specific buzzer."""
    buzzer = get_buzzer_by_id(client_id)
    if not buzzer:
        return jsonify({"error": "Buzzer not found"}), 404

    buzzer.locked = True
    return jsonify(buzzer.to_dict())


@app.route("/api/buzzers/<client_id>/unlock", methods=["POST"])
def unlock_buzzer(client_id):
    """Unlock a specific buzzer."""
    buzzer = get_buzzer_by_id(client_id)
    if not buzzer:
        return jsonify({"error": "Buzzer not found"}), 404

    buzzer.locked = False
    return jsonify(buzzer.to_dict())


@app.route("/api/buzzers/<client_id>/enable", methods=["POST"])
def enable_buzzer(client_id):
    """Enable a specific buzzer."""
    buzzer = get_buzzer_by_id(client_id)
    if not buzzer:
        return jsonify({"error": "Buzzer not found"}), 404

    buzzer.enabled = True
    return jsonify(buzzer.to_dict())


@app.route("/api/buzzers/<client_id>/disable", methods=["POST"])
def disable_buzzer(client_id):
    """Disable a specific buzzer."""
    buzzer = get_buzzer_by_id(client_id)
    if not buzzer:
        return jsonify({"error": "Buzzer not found"}), 404

    buzzer.enabled = False
    return jsonify(buzzer.to_dict())


@app.route("/api/round", methods=["GET", "POST", "DELETE"])
def manage_round():
    """Manage the current round."""
    if request.method == "GET":
        with round_lock:
            buzzes_list = [
                {"buzzer_id": bid, "event": e.to_dict()}
                for bid, e in current_round["buzzes"].items()
            ]
            return jsonify(
                {
                    "active": current_round["active"],
                    "started_at": current_round["started_at"],
                    "buzzes": buzzes_list,
                    "winner": current_round["winner"],
                    "locked": current_round["locked"],
                }
            )

    elif request.method == "POST":
        action = request.get_json().get("action", "start")

        if action == "start":
            start_round()
            return jsonify({"message": "Round started"})
        elif action == "stop":
            with round_lock:
                current_round["active"] = False
            return jsonify({"message": "Round stopped"})
        elif action == "reset":
            reset_round()
            return jsonify({"message": "Round reset"})
        elif action == "lock":
            lock_round()
            return jsonify({"message": "Round locked"})
        elif action == "unlock":
            unlock_round()
            return jsonify({"message": "Round unlocked"})
        else:
            return jsonify({"error": "Invalid action"}), 400

    elif request.method == "DELETE":
        reset_round()
        return jsonify({"message": "Round deleted"})


@app.route("/api/round/winner")
def get_winner():
    """Get the current round winner."""
    with round_lock:
        if current_round["winner"]:
            buzzer = get_buzzer_by_id(current_round["winner"])
            if buzzer:
                event = current_round["buzzes"].get(current_round["winner"])
                return jsonify(
                    {
                        "buzzer_id": current_round["winner"],
                        "buzzer_name": buzzer.name,
                        "corrected_timestamp": event.corrected_timestamp
                        if event
                        else None,
                        "roundtrip_time_ms": event.roundtrip_time if event else None,
                        "button_press": event.payload.get("button_press")
                        if event
                        else None,
                        "send_timestamp": event.payload.get("send_timestamp")
                        if event
                        else None,
                    }
                )
        return jsonify({"winner": None})


@app.route("/api/buzzers/clear", methods=["POST"])
def clear_buzzers():
    """Clear all registered buzzers."""
    with buzzers_lock:
        buzzers.clear()
    return jsonify({"message": "All buzzers cleared"})


@app.route("/api/events/clear", methods=["POST"])
def clear_events():
    """Clear all buzz events."""
    with buzzer_events_lock:
        buzz_events.clear()
    return jsonify({"message": "All events cleared"})


# ============================================================================
# Main
# ============================================================================


def main():
    # Setup MQTT
    if not setup_mqtt():
        logger.warning("Starting without MQTT connection")

    # Start Flask app
    logger.info(f"Starting web server on port {WEB_PORT}")
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
