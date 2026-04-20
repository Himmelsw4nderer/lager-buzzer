#include <Arduino.h>
#include <FlankButton.h>

FlankButton myFlankButton(D2, true);

void setup() {
  Serial.begin(115200);
  myFlankButton.begin();
}

void loop() {
  if (myFlankButton.isPressed()) {
    Serial.println("Knopf wurde gedrückt (Rising Edge)!");
  }
}
