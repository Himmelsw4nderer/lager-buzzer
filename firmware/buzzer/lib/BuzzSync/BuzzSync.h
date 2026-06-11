#pragma once

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// MQTT topics
#define MQTT_TIME_SYNC_TOPIC "lagerbuzzer/time_sync"
#define MQTT_BUZZ_TOPIC "lagerbuzzer/buzz"

// JSON buffer sizes
#define JSON_TIME_SYNC_BUFFER_SIZE 128
#define JSON_BUZZ_BUFFER_SIZE 512  // Increased to accommodate client_id and IP address

class BuzzSync {
public:
    BuzzSync();

    void begin(const char* mqttServer, uint16_t mqttPort = 1883,
               const char* mqttUser = nullptr, const char* mqttPassword = nullptr,
               const char* clientId = nullptr, uint32_t syncTimeoutMs = 5000);

    void update();

    bool sendBuzz(uint32_t buttonPressTime);

    bool isSynced() const;

    void reconnect();

    static BuzzSync* _instance;

private:
    struct SyncState {
        uint32_t timeStamp = 0;  // Unix timestamp from controller
        uint32_t localReceiveTime = 0;  // Local millis() when sync was received
        bool valid = false;
    };

    SyncState _lastSync;
    uint32_t _syncTimeoutMs;
    uint32_t _lastSyncReceivedTime = 0;

    // Store the client ID for this buzzer
    String _clientId;

    WiFiClient _wifiClient;
    PubSubClient _mqttClient;

    const char* _mqttServer;
    uint16_t _mqttPort;
    const char* _mqttUser;
    const char* _mqttPassword;

    friend void _mqttTimeSyncCallback(char* topic, uint8_t* payload, unsigned int length);
    friend void _mqttCallback(char* topic, uint8_t* payload, unsigned int length);

    void _handleTimeSyncMessage(const char* payload, uint16_t length);
    void _setupMqttCallbacks();
};
