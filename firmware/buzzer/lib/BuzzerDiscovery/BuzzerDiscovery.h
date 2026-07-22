#pragma once

#include <Arduino.h>
#include <WiFiUdp.h>

// Finds the LagerBuzzer MQTT broker on the local network via UDP broadcast,
// instead of relying on a hardcoded IP. A small always-on responder on the
// server (server/discovery/discovery.py) answers broadcast requests; the
// source address of its reply is taken as the broker address, so the server
// never needs to know or report its own IP.
//
// Note: this protocol is unauthenticated (same trust model as the
// unauthenticated MQTT broker it points buzzers at), and it silently fails
// on networks with Wi-Fi client/AP isolation enabled - broadcasts between
// stations never arrive at L2 in that case.
class BuzzerDiscovery {
  public:
    BuzzerDiscovery();

    // Blocks until a discovery reply is received, retrying indefinitely.
    // Returns the discovered broker IP as a String owned by this object, so
    // callers can safely keep using its c_str() for as long as this
    // (typically global) instance lives.
    const String& discoverBlocking(uint32_t perAttemptTimeoutMs = 2000);

  private:
    static const uint16_t DISCOVERY_PORT = 42424;

    WiFiUDP _udp;
    String _serverIp;

    void _broadcastRequest();
    void _sendRequestTo(IPAddress dest);
    bool _awaitResponse(uint32_t timeoutMs);
};
