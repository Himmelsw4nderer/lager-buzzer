#include <Arduino.h>
#include <WiFi.h>
#include <QuickEspNow.h>
#include "buzzer_config.h"
#include <BuzzController.h>

#define SERIAL1_TX 17
#define SERIAL1_RX 18

BuzzController controller;

uint16_t pressOrder[BUZZER_COUNT];
size_t pressCount = 0;
String rx1Buf = "";

void printOrder();
void pushStateToWebServer();

void onBuzz(uint16_t buzzerId, uint32_t calculatedTime) {
    for (size_t i = 0; i < pressCount; i++) {
        if (pressOrder[i] == buzzerId) {
            Serial.printf("[CONTROLLER] Duplicate press from ID=%d\n", buzzerId);
            return;
        }
    }
    
    pressOrder[pressCount++] = buzzerId;
    
    Serial.printf("[CONTROLLER] Buzz from ID=%d (position %d), time=%lu\n", 
        buzzerId, pressCount, calculatedTime);
    
    printOrder();
    pushStateToWebServer();
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

void setup() {
    Serial.begin(115200);
    Serial.println("\n[CONTROLLER] Starting...");

    Serial1.begin(115200, SERIAL_8N1, SERIAL1_RX, SERIAL1_TX);

    controller.begin(1, 2000); // Use channel 1
    controller.onBuzz(onBuzz);

    for (size_t i = 0; i < BUZZER_COUNT; i++) {
        controller.registerBuzzer(BUZZER_IDS[i], BUZZER_MACS[i]);
    }

    pushStateToWebServer();

    Serial.println("[CONTROLLER] Ready.");
}

void loop() {
    controller.update();
    processSerial1();
}
