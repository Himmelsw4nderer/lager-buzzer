#include "BuzzSync.h"

BuzzSync* BuzzSync::_instance = nullptr;

// MQTT callback for time sync messages
void _mqttTimeSyncCallback(char* topic, uint8_t* payload, unsigned int length) {
    if (BuzzSync::_instance) {
        BuzzSync::_instance->_handleTimeSyncMessage((const char*)payload, length);
    }
}

// MQTT callback for winner notification
void _mqttWinnerCallback(char* topic, uint8_t* payload, unsigned int length) {
    if (BuzzSync::_instance) {
        BuzzSync::_instance->_handleWinnerMessage((const char*)payload, length);
    }
}

BuzzSync::BuzzSync() : _mqttClient(_wifiClient) {}

void BuzzSync::begin(const char* mqttServer, uint16_t mqttPort,
                     const char* mqttUser, const char* mqttPassword,
                     const char* clientId, uint32_t syncTimeoutMs) {
    _mqttServer = mqttServer;
    _mqttPort = mqttPort;
    _mqttUser = mqttUser;
    _mqttPassword = mqttPassword;
    _clientId = clientId ? String(clientId) : String("buzzer-") + String(ESP.getChipId(), HEX);
    _syncTimeoutMs = syncTimeoutMs;

    // Setup MQTT client
    _mqttClient.setServer(_mqttServer, _mqttPort);
    _instance = this;

    _setupMqttCallbacks();

    Serial.print("[BuzzSync] Initialized for MQTT server: ");
    Serial.print(_mqttServer);
    Serial.print(":");
    Serial.println(_mqttPort);
    Serial.print("[BuzzSync] Client ID: ");
    Serial.println(_clientId);

    // First connection attempt
    reconnect();
}

// Static MQTT callback wrapper
void _mqttCallback(char* topic, uint8_t* payload, unsigned int length) {
    if (strcmp(topic, MQTT_TIME_SYNC_TOPIC) == 0) {
        _mqttTimeSyncCallback(topic, payload, length);
    } else if (strcmp(topic, MQTT_WINNER_TOPIC) == 0) {
        _mqttWinnerCallback(topic, payload, length);
    }
}

void BuzzSync::_setupMqttCallbacks() {
    _mqttClient.setCallback(_mqttCallback);
}

void BuzzSync::reconnect() {
    if (_mqttClient.connected()) {
        return;
    }

    Serial.println("[BuzzSync] Attempting MQTT connection...");

    // Build client ID if not provided
    String actualClientId = _clientId ? String(_clientId) : String("buzzer-") + String(ESP.getChipId(), HEX);

    if (_mqttUser && _mqttPassword) {
        if (_mqttClient.connect(actualClientId.c_str(), _mqttUser, _mqttPassword)) {
            Serial.println("[BuzzSync] Connected to MQTT broker with auth");
        } else {
            Serial.print("[BuzzSync] MQTT connection failed with auth, rc=");
            Serial.println(_mqttClient.state());
            return;
        }
    } else {
        if (_mqttClient.connect(actualClientId.c_str())) {
            Serial.println("[BuzzSync] Connected to MQTT broker");
        } else {
            Serial.print("[BuzzSync] MQTT connection failed, rc=");
            Serial.println(_mqttClient.state());
            return;
        }
    }

    // Subscribe to time sync topic
    if (_mqttClient.subscribe(MQTT_TIME_SYNC_TOPIC)) {
        Serial.print("[BuzzSync] Subscribed to ");
        Serial.println(MQTT_TIME_SYNC_TOPIC);
    } else {
        Serial.print("[BuzzSync] Failed to subscribe to ");
        Serial.println(MQTT_TIME_SYNC_TOPIC);
    }

    // Subscribe to winner topic
    if (_mqttClient.subscribe(MQTT_WINNER_TOPIC)) {
        Serial.print("[BuzzSync] Subscribed to ");
        Serial.println(MQTT_WINNER_TOPIC);
    } else {
        Serial.print("[BuzzSync] Failed to subscribe to ");
        Serial.println(MQTT_WINNER_TOPIC);
    }
}

void BuzzSync::update() {
    // Handle MQTT client loop
    _mqttClient.loop();

    // Check if reconnection is needed
    if (!_mqttClient.connected()) {
        reconnect();
    }

    // Check sync timeout
    if (_lastSync.valid && millis() - _lastSyncReceivedTime > _syncTimeoutMs) {
        _lastSync.valid = false;
        Serial.println("[BuzzSync] Sync expired");
    }
}

bool BuzzSync::sendBuzz(uint32_t buttonPressTime) {
    if (!_lastSync.valid) {
        Serial.println("[BuzzSync] Not sending - no sync");
        return false;
    }

    if (!_mqttClient.connected()) {
        Serial.println("[BuzzSync] MQTT not connected");
        return false;
    }

    // Get current send timestamp (this is when the MQTT message is sent)
    uint32_t sendTimestamp = millis();

    // Create JSON payload for buzz message
    StaticJsonDocument<JSON_BUZZ_BUFFER_SIZE> jsonDoc;
    jsonDoc["time_sync"] = _lastSync.timeStamp;
    jsonDoc["time_sync_received"] = _lastSync.localReceiveTime;
    jsonDoc["button_press"] = buttonPressTime;
    jsonDoc["send_timestamp"] = sendTimestamp;

    // Add client ID to identify this buzzer
    jsonDoc["client_id"] = _clientId;

    // Also add WiFi local IP if available
    if (WiFi.status() == WL_CONNECTED) {
        jsonDoc["ip"] = WiFi.localIP().toString();
    }

    // Serialize to JSON string
    char jsonBuffer[JSON_BUZZ_BUFFER_SIZE];
    size_t jsonLength = serializeJson(jsonDoc, jsonBuffer, sizeof(jsonBuffer));

    // Publish to MQTT
    bool sent = _mqttClient.publish(MQTT_BUZZ_TOPIC, jsonBuffer, jsonLength);

    if (sent) {
        Serial.print("[BuzzSync] Sent BUZZ to ");
        Serial.print(MQTT_BUZZ_TOPIC);
        Serial.print(": time_sync=");
        Serial.print(_lastSync.timeStamp);
        Serial.print(", time_sync_received=");
        Serial.print(_lastSync.localReceiveTime);
        Serial.print(", button_press=");
        Serial.print(buttonPressTime);
        Serial.print(", send_timestamp=");
        Serial.println(sendTimestamp);
    } else {
        Serial.println("[BuzzSync] Failed to send BUZZ via MQTT");
    }

    return sent;
}

bool BuzzSync::isSynced() const {
    return _lastSync.valid;
}

void BuzzSync::onWinner(OnWinnerCallback callback) {
    _winnerCallback = callback;
}

void BuzzSync::_handleTimeSyncMessage(const char* payload, uint16_t length) {
    // Parse JSON payload: {"time_stamp": unixtimestamp}
    StaticJsonDocument<JSON_TIME_SYNC_BUFFER_SIZE> jsonDoc;
    DeserializationError error = deserializeJson(jsonDoc, payload, length);

    if (error) {
        Serial.print("[BuzzSync] Failed to parse time sync JSON: ");
        Serial.println(error.c_str());
        return;
    }

    if (jsonDoc.containsKey("time_stamp")) {
        _lastSync.timeStamp = jsonDoc["time_stamp"];
        _lastSync.localReceiveTime = millis();
        _lastSync.valid = true;
        _lastSyncReceivedTime = millis();

        Serial.print("[BuzzSync] Sync received: time_stamp=");
        Serial.print(_lastSync.timeStamp);
        Serial.print(", localReceiveTime=");
        Serial.println(_lastSync.localReceiveTime);
    } else {
        Serial.println("[BuzzSync] Time sync message missing time_stamp field");
    }
}

void BuzzSync::_handleWinnerMessage(const char* payload, uint16_t length) {
    // Parse JSON payload: {"winner": "client_id"}
    StaticJsonDocument<JSON_TIME_SYNC_BUFFER_SIZE> jsonDoc;
    DeserializationError error = deserializeJson(jsonDoc, payload, length);

    if (error) {
        Serial.print("[BuzzSync] Failed to parse winner JSON: ");
        Serial.println(error.c_str());
        return;
    }

    if (jsonDoc.containsKey("winner")) {
        String winnerId = jsonDoc["winner"];
        bool isWinner = (winnerId == _clientId);

        // Handle reset/clear case (empty winner string)
        if (winnerId.length() == 0) {
            isWinner = false;
        }

        Serial.print("[BuzzSync] Winner message received: ");
        Serial.print("winner=");
        Serial.print(winnerId);
        Serial.print(", isMe=");
        Serial.println(isWinner ? "YES" : "NO");

        if (_winnerCallback) {
            _winnerCallback(isWinner);
        }
    } else {
        Serial.println("[BuzzSync] Winner message missing winner field");
    }
}
