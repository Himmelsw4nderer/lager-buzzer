#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <FlankButton.h>
#include <LEDController.h>
#include <BuzzSync.h>
#include <BuzzerDiscovery.h>

// MQTT Configuration - update these for your environment.
// The broker's IP is not hardcoded: it's found at runtime via UDP broadcast
// discovery (see BuzzerDiscovery), since the server's address depends on
// whichever network it's running on and can change between events.
const uint16_t MQTT_PORT = 1883;
const char* MQTT_USER = nullptr;
const char* MQTT_PASSWORD = nullptr;
#ifdef DEVICE_ID
#define STRINGIFY_(x) #x
#define STRINGIFY(x) STRINGIFY_(x)
const char* MQTT_CLIENT_ID = "buzzer-" STRINGIFY(DEVICE_ID);
#else
const char* MQTT_CLIENT_ID = nullptr;
#endif

LEDController led(D7);
FlankButton btn(D2, true);
BuzzSync buzzSync;
BuzzerDiscovery discovery;

// How long MQTT may stay disconnected before re-running discovery, in case
// the broker's address changed (server moved networks, Pi restarted its
// hotspot on a different subnet, etc.) rather than just a transient drop.
const uint32_t MQTT_RECONNECT_DISCOVERY_MS = 45000;
uint32_t disconnectedSince = 0;

void handleLedCommand(long durationMs) {
    if (durationMs < 0) {
        led.stop();
        Serial.println("[BUZZER] LED off");
    } else {
        led.turnOn((unsigned long)durationMs);
        Serial.print("[BUZZER] LED on, duration_ms=");
        Serial.println(durationMs);
    }
}

void setup() {
    led.begin();
    Serial.begin(115200);
    WiFi.begin("lagerbuzzer", "lagerbuzzer");
    Serial.println("[BUZZER] Connecting to WiFi...");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    Serial.print("[BUZZER] WiFi connected, IP: ");
    Serial.println(WiFi.localIP());

    btn.begin();

    Serial.println("[BUZZER] Discovering MQTT broker...");
    const String& serverIp = discovery.discoverBlocking();

    // Must stay well above the timesync service's INTERVAL_MS (server/docker-compose.yml,
    // 5000 by default) - a timeout equal to the publish interval leaves no margin for
    // MQTT/WiFi delivery jitter and causes sync to expire between messages.
    const uint32_t SYNC_TIMEOUT_MS = 15000;
    buzzSync.begin(serverIp.c_str(), MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_CLIENT_ID, SYNC_TIMEOUT_MS);

    buzzSync.onLedCommand(handleLedCommand);

    Serial.println("[BUZZER] Ready.");
}

void loop() {
    buzzSync.update();
    led.update();

    if (buzzSync.isMqttConnected()) {
        disconnectedSince = 0;
    } else if (disconnectedSince == 0) {
        disconnectedSince = millis();
    } else if (millis() - disconnectedSince > MQTT_RECONNECT_DISCOVERY_MS) {
        Serial.println("[BUZZER] MQTT disconnected too long, rediscovering broker...");
        const String& serverIp = discovery.discoverBlocking();
        buzzSync.setServer(serverIp.c_str());
        disconnectedSince = 0;
    }

    if (btn.isPressed()) {
        uint32_t pressTime = millis();
        bool sent = buzzSync.sendBuzz(pressTime);

        if (sent) {
            Serial.print("[BUZZER] Sent BUZZ at ");
            Serial.println(pressTime);
        } else {
            Serial.println("[BUZZER] Sync not ready or MQTT not connected, BUZZ not sent");
        }
    }
}
