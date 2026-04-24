#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

#define SERIAL1_TX   17
#define SERIAL1_RX   18
#define MAX_BUZZERS  8

static uint8_t  stateCount = 0;
static uint16_t stateOrder[MAX_BUZZERS];
static String   serial1Buf = "";

struct BuzzerConfig {
    uint16_t id;
    String nickname;
};
#define MAX_CONFIGS 20
BuzzerConfig configs[MAX_CONFIGS];
uint8_t configCount = 0;

String getNickname(uint16_t id) {
    for(uint8_t i=0; i<configCount; i++) {
        if(configs[i].id == id && configs[i].nickname.length() > 0) return configs[i].nickname;
    }
    return "ID " + String(id);
}

void setNickname(uint16_t id, String nickname) {
    for(uint8_t i=0; i<configCount; i++) {
        if(configs[i].id == id) {
            configs[i].nickname = nickname;
            return;
        }
    }
    if(configCount < MAX_CONFIGS) {
        configs[configCount].id = id;
        configs[configCount].nickname = nickname;
        configCount++;
    }
}


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
                    "<meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='refresh' content='1'>"
                    "<title>Lagerbuzzer</title>"
                    "<style>"
                    ":root { --bg: #121212; --fg: #f5f5f5; --orange: #ff7b00; --panel: #1e1e1e; }"
                    "body{background-color:var(--bg);color:var(--fg);font-family:'Segoe UI',sans-serif;max-width:500px;margin:2rem auto;padding:1rem;text-align:center;}"
                    "h1{color:var(--orange);border-bottom:2px solid var(--orange);padding-bottom:10px;margin-bottom:20px;font-size:2rem;}"
                    "ol{list-style:none;padding:0;}"
                    "li{background:var(--panel);margin:10px 0;padding:15px;border-radius:8px;font-size:1.5rem;font-weight:bold;border-left:5px solid var(--orange);}"
                    "button{background-color:var(--orange);color:#000;border:none;padding:14px 24px;font-size:1.1rem;font-weight:bold;border-radius:5px;cursor:pointer;width:100%;margin-top:20px;}"
                    "button:hover{filter:brightness(1.2);}"
                    "a{color:var(--orange);text-decoration:none;font-weight:bold;}"
                    "a:hover{text-decoration:underline;}"
                    "hr{border:1px solid #333;margin:30px 0;}"
                    "</style></head><body>"
                    "<h1>Lagerbuzzer</h1>");

    
    if (stateCount == 0) {
        html += F("<p>Noch kein Buzzer gedr&uuml;ckt.</p>");
    } else {
        html += F("<ol>");
        for (uint8_t i = 0; i < stateCount; i++) {
            html += "<li>" + getNickname(stateOrder[i]) + "</li>";
        }
        html += F("</ol>");
    }

    html += F("<form method='post' action='/reset'>"
              "<button type='submit'>Reset</button>"
              "</form>");
    
    html += F("<hr><p><a href='/names'>Nicknames konfigurieren</a></p></body></html>");


    server.send(200, "text/html", html);
}

void handleNames() {
    String html = F("<!DOCTYPE html><html><head>"
                    "<meta charset='utf-8'>"
                    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                    "<title>Nicknames</title>"
                    "<style>"
                    ":root { --bg: #121212; --fg: #f5f5f5; --orange: #ff7b00; --panel: #1e1e1e; }"
                    "body{background-color:var(--bg);color:var(--fg);font-family:'Segoe UI',sans-serif;max-width:500px;margin:2rem auto;padding:1rem;}"
                    "h1,h2{color:var(--orange);text-align:center;}"
                    "h1{border-bottom:2px solid var(--orange);padding-bottom:10px;margin-bottom:20px;}"
                    "form{background:var(--panel);padding:20px;border-radius:8px;}"
                    "input{background:#222;border:1px solid #444;color:var(--fg);padding:10px;border-radius:4px;width:calc(100% - 22px);margin-top:5px;margin-bottom:15px;font-size:1rem;}"
                    "label{font-weight:bold;display:block;margin-top:10px;}"
                    "button{background-color:var(--orange);color:#000;border:none;padding:14px 24px;font-size:1.1rem;font-weight:bold;border-radius:5px;cursor:pointer;width:100%;margin-top:10px;}"
                    "button:hover{filter:brightness(1.2);}"
                    "ul{list-style:none;padding:0;}"
                    "li{background:var(--panel);margin:10px 0;padding:12px;border-radius:8px;border-left:4px solid #555;}"
                    "a{color:var(--orange);text-decoration:none;font-weight:bold;display:block;text-align:center;margin-top:20px;}"
                    "a:hover{text-decoration:underline;}"
                    "</style></head><body>"
                    "<h1>Nicknames</h1>");

    html += F("<form method='post' action='/updatename'>");
    html += F("<label>Buzzer ID:</label><input type='number' name='id' required>");
    html += F("<label>Nickname:</label><input type='text' name='name'>");
    html += F("<button type='submit'>Speichern</button>");
    html += F("</form>");

    if(configCount > 0) {
        html += F("<br><h2>Aktuelle Nicknames</h2><ul>");
        for(uint8_t i=0; i<configCount; i++) {
            html += "<li>ID " + String(configs[i].id) + " : " + configs[i].nickname + "</li>";
        }
        html += F("</ul>");
    }

    html += F("<p><a href='/'>&larr; Zur&uuml;ck</a></p></body></html>");
    server.send(200, "text/html", html);
}

void handleUpdateName() {
    if (server.hasArg("id") && server.hasArg("name")) {
        uint16_t id = server.arg("id").toInt();
        String name = server.arg("name");
        setNickname(id, name);
    }
    server.sendHeader("Location", "/names");
    server.send(303);
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

    WiFi.setTxPower(WIFI_POWER_8_5dBm);
    WiFi.softAP("Lagerbuzzer", "buzzer123");

    Serial.printf("[WEB-SERVER] AP ready  SSID=Lagerbuzzer  IP=%s\n",
                  WiFi.softAPIP().toString().c_str());

    
    server.on("/",      HTTP_GET,  handleRoot);
    server.on("/names", HTTP_GET,  handleNames);
    server.on("/updatename", HTTP_POST, handleUpdateName);
    server.on("/reset", HTTP_POST, handleReset);

    server.begin();
    Serial.println("[WEB-SERVER] HTTP server ready.");
}

void loop() {
    server.handleClient();
    processSerial1();
}
