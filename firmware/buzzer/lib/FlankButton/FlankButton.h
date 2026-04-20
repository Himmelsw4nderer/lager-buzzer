#pragma once
#include <Arduino.h>

class FlankButton {
  public:
    // Konstruktor: Pin und Pull-Up (standardmäßig true)
    FlankButton(uint8_t pin, bool pullUp = true);

    // Initialisierung (im setup() aufrufen)
    void begin();

    // Flankenerkennung: Gibt true zurück, wenn der Knopf gerade gedrückt wurde (Rising Edge)
    bool isPressed();

    // Flankenerkennung: Gibt true zurück, wenn der Knopf gerade losgelassen wurde (Falling Edge)
    bool isReleased();

    // Aktueller Zustand (LOW = gedrückt bei Pull-Up)
    bool isDown();

  private:
    uint8_t _pin;
    bool _pullUp;
    bool _lastState;
    unsigned long _lastDebounceTime;
    static const unsigned long _debounceDelay = 50;  // Entprellzeit in ms
};
