#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <FlankButton.h>
#include <LEDController.h>
#include <BuzzSync.h>

// MQTT Configuration - update these for your environment
const char* MQTT_SERVER = "192.168.4.1";
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
    // Must stay well above the timesync service's INTERVAL_MS (server/docker-compose.yml,
    // 5000 by default) - a timeout equal to the publish interval leaves no margin for
    // MQTT/WiFi delivery jitter and causes sync to expire between messages.
    const uint32_t SYNC_TIMEOUT_MS = 15000;
    buzzSync.begin(MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_CLIENT_ID, SYNC_TIMEOUT_MS);

    buzzSync.onLedCommand(handleLedCommand);

    Serial.println("[BUZZER] Ready.");
}

void loop() {
    buzzSync.update();
    led.update();

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
