#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <QuickEspNow.h>
#include "buzzer_config.h"

int16_t lookupBuzzerId(const uint8_t* mac) {
    for (size_t i = 0; i < BUZZER_COUNT; i++) {
        if (memcmp(mac, BUZZER_MACS[i], 6) == 0) {
            return BUZZER_IDS[i];
        }
    }
    return -1;
}

void onDataReceived(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast) {
    int16_t id = lookupBuzzerId(mac);
    if (id < 0) {
        Serial.printf("[CONTROLLER] Received from unknown device " MACSTR "\n", MAC2STR(mac));
    } else {
        Serial.printf("[CONTROLLER] Received from buzzer ID=%d\n", id);
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("\n[CONTROLLER] Starting...");

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    quickEspNow.onDataRcvd(onDataReceived);
    quickEspNow.begin(1);

    Serial.println("[CONTROLLER] Ready.");
}

void loop() {}
