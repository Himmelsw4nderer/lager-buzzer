#include "BuzzerDiscovery.h"
#include <ESP8266WiFi.h>

namespace {
const char* const REQUEST_PAYLOAD = "LAGERBUZZER_DISCOVER";
const char* const RESPONSE_PAYLOAD = "LAGERBUZZER_ACK";
}  // namespace

BuzzerDiscovery::BuzzerDiscovery() {}

const String& BuzzerDiscovery::discoverBlocking(uint32_t perAttemptTimeoutMs) {
    _udp.begin(DISCOVERY_PORT);

    while (true) {
        _broadcastRequest();

        if (_awaitResponse(perAttemptTimeoutMs)) {
            _udp.stop();
            return _serverIp;
        }

        Serial.println("[BuzzerDiscovery] No response, retrying...");
        // Jittered so many buzzers powering up together don't broadcast in lockstep.
        delay(1500 + random(0, 1000));
    }
}

void BuzzerDiscovery::_broadcastRequest() {
    IPAddress localIp = WiFi.localIP();
    IPAddress subnetMask = WiFi.subnetMask();
    // Some AP firmware handles the subnet-directed broadcast more reliably
    // than the limited (255.255.255.255) broadcast, or vice versa - send both.
    IPAddress directedBroadcast(
        localIp[0] | (~subnetMask[0] & 0xFF),
        localIp[1] | (~subnetMask[1] & 0xFF),
        localIp[2] | (~subnetMask[2] & 0xFF),
        localIp[3] | (~subnetMask[3] & 0xFF));
    IPAddress limitedBroadcast(255, 255, 255, 255);

    Serial.println("[BuzzerDiscovery] Broadcasting discovery request...");
    _sendRequestTo(limitedBroadcast);
    _sendRequestTo(directedBroadcast);
}

void BuzzerDiscovery::_sendRequestTo(IPAddress dest) {
    _udp.beginPacket(dest, DISCOVERY_PORT);
    _udp.write((const uint8_t*)REQUEST_PAYLOAD, strlen(REQUEST_PAYLOAD));
    _udp.endPacket();
}

bool BuzzerDiscovery::_awaitResponse(uint32_t timeoutMs) {
    char buf[32];
    uint32_t start = millis();

    while (millis() - start < timeoutMs) {
        int packetSize = _udp.parsePacket();
        if (packetSize > 0) {
            int len = _udp.read(buf, sizeof(buf) - 1);
            if (len < 0) {
                len = 0;
            }
            buf[len] = '\0';

            if (strcmp(buf, RESPONSE_PAYLOAD) == 0) {
                _serverIp = _udp.remoteIP().toString();
                Serial.print("[BuzzerDiscovery] Discovered server at: ");
                Serial.println(_serverIp);
                return true;
            }
        }
        delay(20);
    }

    return false;
}
