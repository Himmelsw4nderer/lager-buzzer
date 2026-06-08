#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <QuickEspNow.h>
#include <FlankButton.h>
#include <BuzzSync.h>

FlankButton btn(D2, true);
BuzzSync buzzSync;

void setup() {
    Serial.begin(115200);
    
    btn.begin();
    buzzSync.begin(1); // Use channel 1
    
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
            Serial.println("[BUZZER] Sync not ready, BUZZ not sent");
        }
    }
}
