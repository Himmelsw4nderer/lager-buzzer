#include "BuzzSync.h"

BuzzSync* BuzzSync::_instance = nullptr;

void _buzzSyncEspNowCallback(uint8_t* mac, uint8_t* data, uint8_t len, signed int rssi, bool broadcast) {
    if (BuzzSync::_instance) {
        BuzzSync::_instance->_handleIncoming(mac, data, len);
    }
}

BuzzSync::BuzzSync() {}

void BuzzSync::begin(uint32_t channel, uint32_t syncIntervalMs) {
    _syncIntervalMs = syncIntervalMs;
    
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    quickEspNow.begin(channel);  // Use specified channel
    quickEspNow.onDataRcvd(_buzzSyncEspNowCallback);
    
    _instance = this;
    _lastSyncTime = millis();
    
    Serial.print("[BuzzSync] Initialized on channel ");
    Serial.println(channel);
}

void BuzzSync::update() {
    const uint32_t SYNC_TIMEOUT_MS = 5000;
    if (_lastSync.valid && millis() - _lastSyncReceivedTime > SYNC_TIMEOUT_MS) {
        _lastSync.valid = false;
        Serial.println("[BuzzSync] Sync expired");
    }
}

bool BuzzSync::sendBuzz(uint32_t buttonPressTime) {
    if (!_lastSync.valid) {
        Serial.println("[BuzzSync] Not sending - no sync");
        return false;
    }
    
    BuzzMessage msg;
    msg.buttonPressTime = buttonPressTime;
    msg.lastSyncReceiveTime = _lastSync.localReceiveTime;
    msg.syncWasSentAt = _lastSync.controllerSendTime;
    msg.buzzSendTime = millis();
    msg.buzzSequenceNumber = _lastSync.sequenceNumber;
    
    bool sent = quickEspNow.send(ESPNOW_BROADCAST_ADDRESS, (uint8_t*)&msg, sizeof(BuzzMessage));
    
    if (sent) {
        Serial.print("[BuzzSync] Sent BUZZ: press=");
        Serial.print(buttonPressTime);
        Serial.print(", syncRcv=");
        Serial.print(msg.lastSyncReceiveTime);
        Serial.print(", syncSent=");
        Serial.print(msg.syncWasSentAt);
        Serial.print(", buzzSent=");
        Serial.println(msg.buzzSendTime);
    } else {
        Serial.println("[BuzzSync] Failed to send BUZZ");
    }
    
    return sent;
}

bool BuzzSync::isSynced() const {
    return _lastSync.valid;
}

void BuzzSync::_handleIncoming(uint8_t* mac, uint8_t* data, uint8_t len) {
    if (len < 1) return;
    
    uint8_t type = data[0];
    
    if (type == MSG_TYPE_SYNC && len >= sizeof(SyncMessage)) {
        const SyncMessage* syncMsg = reinterpret_cast<const SyncMessage*>(data);
        _lastSync.controllerSendTime = syncMsg->controllerSendTime;
        _lastSync.localReceiveTime = millis();
        _lastSync.sequenceNumber = syncMsg->sequenceNumber;
        _lastSync.valid = true;
        _lastSyncReceivedTime = millis();
        
        Serial.print("[BuzzSync] Sync received: controllerTime=");
        Serial.print(syncMsg->controllerSendTime);
        Serial.print(", localTime=");
        Serial.print(_lastSync.localReceiveTime);
        Serial.print(", seq=");
        Serial.println(syncMsg->sequenceNumber);
    }
}
