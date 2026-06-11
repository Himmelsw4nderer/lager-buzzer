#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <FlankButton.h>
#include <BuzzSync.h>

// MQTT Configuration - update these for your environment
const char* MQTT_SERVER = "192.168.4.1";
const uint16_t MQTT_PORT = 1883;
const char* MQTT_USER = nullptr;
const char* MQTT_PASSWORD = nullptr;
const char* MQTT_CLIENT_ID = nullptr;

FlankButton btn(D2, true);
BuzzSync buzzSync;


// Empty callback - you can implement LED/speaker logic here later
void onWinnerNotification(bool isWinner) {
    // TODO: Implement your LED and speaker logic here
    // isWinner = true when this buzzer is the winner
    // isWinner = false when someone else won or round was reset
    if (isWinner) {
        Serial.println("[BUZZER] I AM THE WINNER!");
    } else {
        Serial.println("[BUZZER] Not the winner.");
    }
}

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

    buzzSync.onWinner(onWinnerNotification);

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
