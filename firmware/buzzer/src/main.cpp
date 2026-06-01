#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <QuickEspNow.h>
#include <FlankButton.h>

FlankButton btn(D2, true);  // active LOW, internal pull-up

void setup() {
    Serial.begin(115200);

    btn.begin();

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    quickEspNow.begin(1);

    Serial.println("[BUZZER] Ready.");
}

void loop() {
    if (btn.isPressed()) {
        const char* msg = "BUZZ";
        quickEspNow.send(ESPNOW_BROADCAST_ADDRESS, (uint8_t*)msg, strlen(msg));
        Serial.println("[BUZZER] Sent BUZZ");
    }
}
