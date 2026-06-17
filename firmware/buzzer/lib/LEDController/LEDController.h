#pragma once
#include <Arduino.h>

class LEDController {
  public:
    // Konstruktor: Pin und Dauer in ms
    LEDController(uint8_t pin, unsigned long durationMs);

    // Initialisierung (im setup() aufrufen)
    void begin();

    // Aktiviert die LED für die festgelegte Dauer
    void trigger();

    // Schaltet die LED sofort aus
    void stop();

    // Wird jeden Loop aufgerufen, um den Zustand zu aktualisieren
    void update();

    // Gibt zurück, ob die LED gerade aktiv ist
    bool isActive();

  private:
    uint8_t _pin;
    unsigned long _durationMs;
    unsigned long _triggerTime;
    bool _isTriggered;
};
