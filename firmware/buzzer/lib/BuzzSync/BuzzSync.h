#pragma once

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <QuickEspNow.h>

// Message types
#define MSG_TYPE_SYNC 0
#define MSG_TYPE_BUZZ 1

// Message structures (packed to avoid padding)
struct __attribute__((packed)) SyncMessage {
    uint8_t type = MSG_TYPE_SYNC;
    uint32_t controllerSendTime;
    uint32_t sequenceNumber;
};

struct __attribute__((packed)) BuzzMessage {
    uint8_t type = MSG_TYPE_BUZZ;
    uint32_t buttonPressTime;
    uint32_t lastSyncReceiveTime;
    uint32_t syncWasSentAt;
    uint32_t buzzSendTime;
    uint32_t buzzSequenceNumber;
};

class BuzzSync {
public:
    BuzzSync();
    
    void begin(uint32_t channel = 1, uint32_t syncIntervalMs = 2000);
    
    void update();
    
    bool sendBuzz(uint32_t buttonPressTime);
    
    bool isSynced() const;

private:
    struct SyncState {
        uint32_t controllerSendTime = 0;
        uint32_t localReceiveTime = 0;
        uint32_t sequenceNumber = 0;
        bool valid = false;
    };
    
    SyncState _lastSync;
    uint32_t _syncIntervalMs;
    uint32_t _lastSyncTime = 0;
    uint32_t _lastSyncReceivedTime = 0;
    
    static BuzzSync* _instance;
    friend void _buzzSyncEspNowCallback(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast);
    
    void _handleIncoming(uint8_t* mac, uint8_t* data, uint8_t len);
};
