#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <QuickEspNow.h>
#include "buzzer_config.h"

uint16_t pressOrder[BUZZER_COUNT];
size_t   pressCount = 0;

int16_t lookupBuzzerId(const uint8_t* mac) {
    for (size_t i = 0; i < BUZZER_COUNT; i++) {
        if (memcmp(mac, BUZZER_MACS[i], 6) == 0) {
            return BUZZER_IDS[i];
        }
    }
    return -1;
}

bool alreadyPressed(uint16_t id) {
    for (size_t i = 0; i < pressCount; i++) {
        if (pressOrder[i] == id) return true;
    }
    return false;
}

void printOrder() {
    Serial.print("[CONTROLLER] Order: ");
    for (size_t i = 0; i < pressCount; i++) {
        Serial.printf("%d. ID=%d  ", i + 1, pressOrder[i]);
    }
    Serial.println();
}

void onDataReceived(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast) {
    int16_t id = lookupBuzzerId(mac);
    if (id < 0) {
        Serial.printf("[CONTROLLER] Received from unknown device " MACSTR "\n", MAC2STR(mac));
        return;
    }
    if (alreadyPressed(id)) {
        Serial.printf("[CONTROLLER] Duplicate press from ID=%d — ignored\n", id);
        return;
    }
    pressOrder[pressCount++] = id;
    Serial.printf("[CONTROLLER] Buzz from ID=%d (position %d)\n", id, pressCount);
    printOrder();
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
