#!/usr/bin/env python3
"""
Time Sync Publisher for LagerBuzzer
Publishes current Unix timestamp to MQTT topic: lagerbuzzer/time_sync
Payload format: {"time_stamp": <unix_timestamp>}
"""

import json
import logging
import os
import signal
import sys
import time

import paho.mqtt.client as mqtt

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "lagerbuzzer/time_sync")
INTERVAL_MS = int(os.getenv("INTERVAL_MS", 5000))  # 5 seconds default

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [TimeSync] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Global flag for clean shutdown
running = True


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    global running
    logger.info(f"Received signal {sig}, shutting down...")
    running = False


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker."""
    if rc == 0:
        logger.info(f"Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    else:
        logger.error(f"Connection failed with code {rc}")


def publish_time_sync(client):
    """Publish current timestamp to MQTT."""
    timestamp = int(time.time())
    payload = json.dumps({"time_stamp": timestamp})

    result = client.publish(MQTT_TOPIC, payload, qos=0, retain=False)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.debug(f"Published time_sync: {timestamp}")
    else:
        logger.error(f"Failed to publish: {mqtt.error_string(result.rc)}")


def main():
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create MQTT client
    client = mqtt.Client("timesync-publisher")
    client.on_connect = on_connect

    # Enable logging for MQTT client
    client.enable_logger(logger)

    try:
        # Connect to broker
        logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()

        # Wait for connection
        time.sleep(1)

        if not client.is_connected():
            logger.error("Failed to connect to MQTT broker")
            return 1

        logger.info(f"Starting time sync publisher. Interval: {INTERVAL_MS}ms")
        logger.info(f"Publishing to topic: {MQTT_TOPIC}")

        interval_seconds = INTERVAL_MS / 1000.0

        # Main loop
        while running:
            publish_time_sync(client)

            # Sleep for the interval, but check for shutdown periodically
            sleep_remaining = interval_seconds
            while sleep_remaining > 0.1 and running:
                time.sleep(0.1)
                sleep_remaining -= 0.1

            if not running:
                break

        logger.info("Shutting down...")
        client.loop_stop()
        client.disconnect()
        logger.info("Time sync publisher stopped")
        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
