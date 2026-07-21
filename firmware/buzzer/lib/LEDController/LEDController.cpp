#include "LEDController.h"

LEDController::LEDController(uint8_t pin) : _pin(pin) {}

void LEDController::begin() {
  pinMode(_pin, OUTPUT);
  digitalWrite(_pin, LOW);
}

void LEDController::turnOn(unsigned long durationMs) {
  _triggerTime = millis();
  _durationMs = durationMs;
  _indefinite = (durationMs == 0);
  _isOn = true;
  digitalWrite(_pin, HIGH);
}

void LEDController::stop() {
  digitalWrite(_pin, LOW);
  _isOn = false;
}

void LEDController::update() {
  if (_isOn && !_indefinite && (millis() - _triggerTime >= _durationMs)) {
    digitalWrite(_pin, LOW);
    _isOn = false;
  }
}

bool LEDController::isActive() {
  if (!_isOn) return false;
  if (_indefinite) return true;
  return (millis() - _triggerTime < _durationMs);
}
