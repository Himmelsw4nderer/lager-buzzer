#pragma once
#include <Arduino.h>

class LEDController {
  public:
    // Konstruktor: Pin
    explicit LEDController(uint8_t pin);

    // Initialisierung (im setup() aufrufen)
    void begin();

    // Schaltet die LED ein. durationMs == 0 -> bleibt an bis stop() aufgerufen wird,
    // durationMs > 0 -> schaltet sich nach dieser Zeit automatisch aus.
    void turnOn(unsigned long durationMs);

    // Schaltet die LED sofort aus
    void stop();

    // Wird jeden Loop aufgerufen, um den Zustand zu aktualisieren
    void update();

    // Gibt zurück, ob die LED gerade aktiv ist
    bool isActive();

  private:
    uint8_t _pin;
    unsigned long _durationMs = 0;
    unsigned long _triggerTime = 0;
    bool _isOn = false;
    bool _indefinite = false;
};
