#!/usr/bin/env python3
"""
Discovery Responder for LagerBuzzer
Answers UDP broadcast discovery requests from buzzers so they can find the
MQTT broker's current address without a hardcoded IP. Buzzers take the source
address of the reply as the broker address, so this service never needs to
know or report its own IP.

No authentication - anyone on the LAN can query this, same trust model as
the unauthenticated MQTT broker it points buzzers at.
"""

import logging
import os
import signal
import socket
import sys

DISCOVERY_PORT = int(os.getenv("DISCOVERY_PORT", 42424))
REQUEST_PAYLOAD = b"LAGERBUZZER_DISCOVER"
RESPONSE_PAYLOAD = b"LAGERBUZZER_ACK"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [Discovery] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

running = True


def signal_handler(sig, frame):
    global running
    logger.info(f"Received signal {sig}, shutting down...")
    running = False


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", DISCOVERY_PORT))
    sock.settimeout(1.0)

    logger.info(f"Listening for discovery requests on UDP port {DISCOVERY_PORT}")

    while running:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        except OSError:
            break

        if data == REQUEST_PAYLOAD:
            sock.sendto(RESPONSE_PAYLOAD, addr)
            logger.info(f"Discovery request from {addr[0]}:{addr[1]}, replied")

    sock.close()
    logger.info("Discovery responder stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
