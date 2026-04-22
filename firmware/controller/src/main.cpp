#include <Arduino.h>
#include <WiFi.h>
#include <QuickEspNow.h>
#include "buzzer_config.h"

#define SERIAL1_TX 17
#define SERIAL1_RX 18

uint16_t pressOrder[BUZZER_COUNT];
size_t   pressCount = 0;

volatile bool    pendingBuzz = false;
volatile int16_t pendingId   = -1;

static String rx1Buf = "";

int16_t lookupBuzzerId(const uint8_t* mac) {
    for (size_t i = 0; i < BUZZER_COUNT; i++) {
        if (memcmp(mac, BUZZER_MACS[i], 6) == 0) return BUZZER_IDS[i];
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

void pushStateToWebServer() {
    Serial1.print("STATE:");
    Serial1.print((int)pressCount);
    Serial1.print(":");
    for (size_t i = 0; i < pressCount; i++) {
        if (i > 0) Serial1.print(",");
        Serial1.print(pressOrder[i]);
    }
    Serial1.println();
}

void processSerial1() {
    while (Serial1.available()) {
        char c = (char)Serial1.read();
        if (c == '\n') {
            rx1Buf.trim();
            if (rx1Buf == "RESET") {
                pressCount = 0;
                Serial.println("[CONTROLLER] Reset via Serial1");
                pushStateToWebServer();
            }
            rx1Buf = "";
        } else if (c != '\r') {
            rx1Buf += c;
        }
    }
}

void onDataReceived(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast) {
    int16_t id = lookupBuzzerId(mac);
    if (id < 0 || pendingBuzz) return;
    pendingId   = id;
    pendingBuzz = true;
}

void setup() {
    Serial.begin(115200);
    Serial.println("\n[CONTROLLER] Starting...");

    Serial1.begin(115200, SERIAL_8N1, SERIAL1_RX, SERIAL1_TX);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    quickEspNow.onDataRcvd(onDataReceived);
    quickEspNow.begin(1);

    pushStateToWebServer();

    Serial.println("[CONTROLLER] Ready.");
}

void loop() {
    processSerial1();

    if (pendingBuzz) {
        pendingBuzz = false;
        int16_t id  = pendingId;

        if (id < 0) return;

        if (alreadyPressed((uint16_t)id)) {
            Serial.printf("[CONTROLLER] Duplicate press from ID=%d — ignored\n", id);
            return;
        }

        pressOrder[pressCount++] = (uint16_t)id;
        Serial.printf("[CONTROLLER] Buzz from ID=%d (position %d)\n", id, pressCount);
        printOrder();
        pushStateToWebServer();
    }
}
