#include "BuzzController.h"

BuzzController* BuzzController::_instance = nullptr;

void _buzzControllerCallback(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast) {
    if (BuzzController::_instance) {
        if (len >= sizeof(BuzzMessage)) {
            const BuzzMessage* buzzMsg = reinterpret_cast<const BuzzMessage*>(data);
            if (buzzMsg->type == MSG_TYPE_BUZZ) {
                BuzzController::_instance->_handleBuzzMessage(mac, *buzzMsg);
            }
        }
    }
}

BuzzController::BuzzController() {}

void BuzzController::begin(uint32_t channel, uint32_t syncIntervalMs) {
    _syncIntervalMs = syncIntervalMs;
    
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    
    quickEspNow.begin(channel);
    quickEspNow.onDataRcvd(_buzzControllerCallback);
    
    _instance = this;
    _lastSyncTime = millis();
    
    Serial.print("[BuzzController] Initialized on channel ");
    Serial.println(channel);
    _sendSync();
}

void BuzzController::update() {
    if (millis() - _lastSyncTime >= _syncIntervalMs) {
        _sendSync();
    }
}

void BuzzController::registerBuzzer(uint16_t id, const uint8_t* mac) {
    if (_registrationCount >= MAX_BUZZERS) return;
    
    _registrations[_registrationCount].id = id;
    memcpy(_registrations[_registrationCount].mac, mac, 6);
    _registrationCount++;
    
    _buzzerInfos[_registrationCount - 1].id = id;
    _buzzerInfos[_registrationCount - 1].lastPressTime = 0;
    _buzzerInfos[_registrationCount - 1].lastRtt = 0;
    _buzzerInfos[_registrationCount - 1].clockOffset = 0;
    memcpy(_buzzerInfos[_registrationCount - 1].mac, mac, 6);
    
    Serial.printf("[BuzzController] Registered buzzer ID=%d\n", id);
}

void BuzzController::onBuzz(OnBuzzCallback callback) {
    _buzzCallback = callback;
}

size_t BuzzController::getBuzzerCount() const {
    return _registrationCount;
}

const BuzzerInfo& BuzzController::getBuzzer(size_t index) const {
    static BuzzerInfo nullInfo = {0, {0}, 0, 0, 0};
    if (index < MAX_BUZZERS && index < _registrationCount) {
        return _buzzerInfos[index];
    }
    return nullInfo;
}

const PressEvent& BuzzController::getLastPress() const {
    return _lastPress;
}

size_t BuzzController::getPressEvents(PressEvent* events, size_t maxEvents) {
    size_t copyCount = (_pressEventCount < maxEvents) ? _pressEventCount : maxEvents;
    if (copyCount > 0) {
        memcpy(events, _pressEvents, copyCount * sizeof(PressEvent));
        _pressEventCount = 0;
    }
    return copyCount;
}

bool BuzzController::hasPressed(uint16_t buzzerId) const {
    for (size_t i = 0; i < _pressedCount; i++) {
        if (_pressedIds[i] == buzzerId) return true;
    }
    return false;
}

void BuzzController::_sendSync() {
    SyncMessage msg;
    msg.controllerSendTime = millis();
    msg.sequenceNumber = _sequenceNumber++;
    
    quickEspNow.send(ESPNOW_BROADCAST_ADDRESS, (uint8_t*)&msg, sizeof(SyncMessage));
    
    _lastSyncTime = millis();
    
    Serial.printf("[BuzzController] Sent SYNC: time=%lu, seq=%lu\n", msg.controllerSendTime, msg.sequenceNumber);
}

void BuzzController::_handleBuzzMessage(const uint8_t* mac, const BuzzMessage& msg) {
    uint16_t buzzerId = 0;
    size_t buzzerIndex = 0;
    bool found = false;
    
    for (size_t i = 0; i < _registrationCount; i++) {
        if (memcmp(_registrations[i].mac, mac, 6) == 0) {
            buzzerId = _registrations[i].id;
            buzzerIndex = i;
            found = true;
            break;
        }
    }
    
    if (!found) {
        Serial.println("[BuzzController] BUZZ from unknown buzzer");
        return;
    }
    
    static uint32_t lastSeqPerBuzzer[MAX_BUZZERS] = {0};
    if (msg.buzzSequenceNumber == lastSeqPerBuzzer[buzzerIndex]) {
        return;
    }
    lastSeqPerBuzzer[buzzerIndex] = msg.buzzSequenceNumber;
    
    uint32_t pressTime = _calculatePressTime(msg);
    int32_t rtt = _calculateRoundTripTime(msg);
    
    _buzzerInfos[buzzerIndex].lastPressTime = pressTime;
    _buzzerInfos[buzzerIndex].lastRtt = rtt;
    
    PressEvent event;
    event.buzzerId = buzzerId;
    event.calculatedTime = pressTime + (rtt / 2000);
    event.sequenceNumber = msg.buzzSequenceNumber;
    
    if (_pressEventCount < MAX_PRESS_EVENTS) {
        _pressEvents[_pressEventCount++] = event;
    }
    
    _lastPress = event;
    
    bool alreadyPressed = false;
    for (size_t i = 0; i < _pressedCount; i++) {
        if (_pressedIds[i] == buzzerId) {
            alreadyPressed = true;
            break;
        }
    }
    if (!alreadyPressed && _pressedCount < MAX_BUZZERS * 4) {
        _pressedIds[_pressedCount++] = buzzerId;
    }
    
    Serial.printf("[BuzzController] BUZZ from ID=%d: time=%lu, rtt=%d\n", buzzerId, pressTime, rtt);
    
    if (_buzzCallback) {
        _buzzCallback(buzzerId, event.calculatedTime);
    }
}

uint32_t BuzzController::_calculatePressTime(const BuzzMessage& msg) const {
    uint32_t c1 = msg.syncWasSentAt;
    uint32_t b1 = msg.lastSyncReceiveTime;
    uint32_t bp = msg.buttonPressTime;
    
    int32_t offset = (int32_t)b1 - (int32_t)c1;
    int32_t delta = (int32_t)bp - (int32_t)b1;
    
    return (uint32_t)((int32_t)c1 + offset + delta);
}

int32_t BuzzController::_calculateRoundTripTime(const BuzzMessage& msg) const {
    uint32_t now = millis();
    uint32_t c1 = msg.syncWasSentAt;
    uint32_t b1 = msg.lastSyncReceiveTime;
    uint32_t b2 = msg.buzzSendTime;
    
    return (int32_t)(now - b2) + (int32_t)(b1 - c1);
}
