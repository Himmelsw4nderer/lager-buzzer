#include "FlankButton.h"

FlankButton::FlankButton(uint8_t pin, bool pullUp)
  : _pin(pin), _pullUp(pullUp), _lastState(!pullUp), _lastDebounceTime(0) {}

void FlankButton::begin() {
  pinMode(_pin, _pullUp ? INPUT_PULLUP : INPUT);
}

bool FlankButton::isDown() {
  return digitalRead(_pin) == (_pullUp ? LOW : HIGH);
}

bool FlankButton::isPressed() {
  bool currentState = isDown();
  unsigned long now = millis();

  if ((now - _lastDebounceTime) > _debounceDelay) {
    if (currentState != _lastState) {
      _lastDebounceTime = now;
      _lastState = currentState;
      if (currentState) return true;
    }
  }
  return false;
}

bool FlankButton::isReleased() {
  bool currentState = isDown();
  unsigned long now = millis();

  if ((now - _lastDebounceTime) > _debounceDelay) {
    if (currentState != _lastState) {
      _lastDebounceTime = now;
      _lastState = currentState;
      if (!currentState) return true;
    }
  }
  return false;
}
