#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <QuickEspNow.h>

void onDataReceived(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast) {
    Serial.printf("[CONTROLLER] Received %d bytes from " MACSTR " (RSSI: %d)\n",
                  len, MAC2STR(mac), rssi);
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
