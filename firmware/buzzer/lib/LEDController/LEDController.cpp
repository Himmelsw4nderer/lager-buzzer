#include "LEDController.h"

LEDController::LEDController(uint8_t pin, unsigned long durationMs)
  : _pin(pin), _durationMs(durationMs), _triggerTime(0), _isTriggered(false) {}

void LEDController::begin() {
  pinMode(_pin, OUTPUT);
  digitalWrite(_pin, LOW);
}

void LEDController::trigger() {
  _triggerTime = millis();
  _isTriggered = true;
  digitalWrite(_pin, HIGH);
}

void LEDController::stop() {
  digitalWrite(_pin, LOW);
  _isTriggered = false;
}

void LEDController::update() {
  if (_isTriggered && (millis() - _triggerTime >= _durationMs)) {
    digitalWrite(_pin, LOW);
    _isTriggered = false;
  }
}

bool LEDController::isActive() {
  if (!_isTriggered) return false;
  return (millis() - _triggerTime < _durationMs);
}
