#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <FlankButton.h>
#include <BuzzSync.h>

// MQTT Configuration - update these for your environment
const char* MQTT_SERVER = "192.168.1.100";  // Your MQTT broker IP or hostname
const uint16_t MQTT_PORT = 1883;
const char* MQTT_USER = nullptr;           // Set if your broker requires authentication
const char* MQTT_PASSWORD = nullptr;       // Set if your broker requires authentication
const char* MQTT_CLIENT_ID = nullptr;      // Optional: custom client ID, or auto-generated

FlankButton btn(D2, true);
BuzzSync buzzSync;

void setup() {
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
    buzzSync.begin(MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_CLIENT_ID);

    Serial.println("[BUZZER] Ready.");
}

void loop() {
    buzzSync.update();

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
