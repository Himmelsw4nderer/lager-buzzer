#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

#define SERIAL1_TX   17
#define SERIAL1_RX   18
#define MAX_BUZZERS  8

static uint8_t  stateCount = 0;
static uint16_t stateOrder[MAX_BUZZERS];
static String   serial1Buf = "";

void parseState(const String& line) {
    if (!line.startsWith("STATE:")) return;

    int c1 = line.indexOf(':');
    int c2 = line.indexOf(':', c1 + 1);
    if (c1 < 0 || c2 < 0) return;

    uint8_t count = (uint8_t)line.substring(c1 + 1, c2).toInt();
    if (count > MAX_BUZZERS) return;

    stateCount = count;

    if (count == 0) {
        Serial.println("[WEB-SERVER] State cleared");
        return;
    }

    String ids = line.substring(c2 + 1);
    int pos = 0;
    for (uint8_t i = 0; i < count; i++) {
        int comma = ids.indexOf(',', pos);
        String idStr = (comma < 0) ? ids.substring(pos) : ids.substring(pos, comma);
        stateOrder[i] = (uint16_t)idStr.toInt();
        if (comma < 0) break;
        pos = comma + 1;
    }

    Serial.printf("[WEB-SERVER] State updated: %d buzzer(s)\n", count);
}

void processSerial1() {
    while (Serial1.available()) {
        char c = (char)Serial1.read();
        if (c == '\n') {
            serial1Buf.trim();
            if (serial1Buf.length() > 0) parseState(serial1Buf);
            serial1Buf = "";
        } else if (c != '\r') {
            serial1Buf += c;
        }
    }
}

WebServer server(80);

void handleRoot() {
    String html = F("<!DOCTYPE html><html><head>"
                    "<meta charset='utf-8'>"
                    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                    "<title>Lagerbuzzer</title>"
                    "<style>"
                    "body{font-family:sans-serif;max-width:480px;margin:2rem auto;padding:0 1rem}"
                    "h1{font-size:1.8rem}ol{font-size:1.4rem;line-height:2}"
                    "button{margin-top:1.5rem;padding:.6rem 1.4rem;font-size:1rem;cursor:pointer}"
                    "</style></head><body>"
                    "<h1>&#x1F514; Lagerbuzzer</h1>");

    if (stateCount == 0) {
        html += F("<p>Noch kein Buzzer gedr&uuml;ckt.</p>");
    } else {
        html += F("<ol>");
        for (uint8_t i = 0; i < stateCount; i++) {
            html += "<li>ID " + String(stateOrder[i]) + "</li>";
        }
        html += F("</ol>");
    }

    html += F("<form method='post' action='/reset'>"
              "<button type='submit'>Reset</button>"
              "</form></body></html>");

    server.send(200, "text/html", html);
}

void handleReset() {
    stateCount = 0;
    Serial1.println("RESET");
    server.sendHeader("Location", "/");
    server.send(303);
}

void setup() {
    Serial.begin(115200);
    Serial.println("\n[WEB-SERVER] Starting...");

    Serial1.begin(115200, SERIAL_8N1, SERIAL1_RX, SERIAL1_TX);

    WiFi.mode(WIFI_AP);
    delay(100);

    WiFi.softAPConfig(
        IPAddress(10, 0, 0, 1),
        IPAddress(10, 0, 0, 1),
        IPAddress(255, 255, 255, 0)
    );

    WiFi.softAP("Lagerbuzzer", "buzzer123", 1, 0, 4);

    Serial.printf("[WEB-SERVER] AP ready  SSID=Lagerbuzzer  IP=%s\n",
                  WiFi.softAPIP().toString().c_str());

    server.on("/",      HTTP_GET,  handleRoot);
    server.on("/reset", HTTP_POST, handleReset);
    server.begin();
    Serial.println("[WEB-SERVER] HTTP server ready.");
}

void loop() {
    server.handleClient();
    processSerial1();
}
