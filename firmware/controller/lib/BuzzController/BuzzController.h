#pragma once

#include <Arduino.h>
#include <WiFi.h>
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

struct BuzzerInfo {
    uint16_t id;
    uint8_t mac[6];
    uint32_t lastPressTime;
    uint32_t lastRtt;
    int32_t clockOffset;
};

struct PressEvent {
    uint16_t buzzerId;
    uint32_t calculatedTime;
    uint32_t sequenceNumber;
};

using OnBuzzCallback = void (*)(uint16_t buzzerId, uint32_t calculatedTime);

class BuzzController {
public:
    BuzzController();
    
    void begin(uint32_t channel = 1, uint32_t syncIntervalMs = 2000);
    void update();
    void registerBuzzer(uint16_t id, const uint8_t* mac);
    void onBuzz(OnBuzzCallback callback);
    
    size_t getBuzzerCount() const;
    const BuzzerInfo& getBuzzer(size_t index) const;
    const PressEvent& getLastPress() const;
    size_t getPressEvents(PressEvent* events, size_t maxEvents);
    bool hasPressed(uint16_t buzzerId) const;

private:
    struct BuzzerRegistration {
        uint16_t id;
        uint8_t mac[6];
    };
    
    static const size_t MAX_BUZZERS = 16;
    static const size_t MAX_PRESS_EVENTS = 64;
    
    BuzzerRegistration _registrations[MAX_BUZZERS];
    size_t _registrationCount = 0;
    
    BuzzerInfo _buzzerInfos[MAX_BUZZERS];
    PressEvent _pressEvents[MAX_PRESS_EVENTS];
    size_t _pressEventCount = 0;
    uint16_t _pressedIds[MAX_BUZZERS * 4];
    size_t _pressedCount = 0;
    PressEvent _lastPress;
    
    uint32_t _syncIntervalMs;
    uint32_t _lastSyncTime = 0;
    uint32_t _sequenceNumber = 0;
    
    OnBuzzCallback _buzzCallback = nullptr;
    
    void _sendSync();
    void _handleBuzzMessage(const uint8_t* mac, const BuzzMessage& msg);
    uint32_t _calculatePressTime(const BuzzMessage& msg) const;
    int32_t _calculateRoundTripTime(const BuzzMessage& msg) const;
    
    static BuzzController* _instance;
    friend void _buzzControllerCallback(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast);
};
