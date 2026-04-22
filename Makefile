# Lagerbuzzer Makefile
#
# Create device_macs.mk next to this file:
#   CONTROLLER_MAC := AA:BB:CC:11:22:33
#   BUZZER_MACS    := 24:a1:60:2e:d1:47 11:22:33:44:55:66
#   BUZZER_IDS     := 101 102

.PHONY: help scan find-port lookup-buzzer-mac \
        controller-build controller-upload controller-monitor \
        buzzer-build buzzer-upload buzzer-monitor \
        clean

FIRMWARE_DIR   := firmware
CONTROLLER_DIR := $(FIRMWARE_DIR)/controller
BUZZER_DIR     := $(FIRMWARE_DIR)/buzzer
PIO_ENV        := d1_mini
BAUD_RATE      := 115200

-include device_macs.mk

CONTROLLER_MAC   ?=
BUZZER_MACS      ?=
BUZZER_IDS       ?=
BUZZER_DEVICE_ID ?=
MAC              ?=

# Use uv to run esptool - no separate install needed.
ESPTOOL := uv tool run esptool

.DEFAULT_GOAL := help

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo "Lagerbuzzer Makefile"
	@echo ""
	@echo "Diagnostic:"
	@echo "  scan                                  Print raw esptool output for every connected port"
	@echo "  find-port MAC=<mac>                   Find the serial port for a given MAC"
	@echo "  lookup-buzzer-mac BUZZER_DEVICE_ID=<> Print the MAC for a given buzzer ID"
	@echo ""
	@echo "Controller:"
	@echo "  controller-build                      Build controller firmware"
	@echo "  controller-upload                     Find controller by MAC, build + upload"
	@echo "  controller-monitor                    Find controller by MAC, open serial monitor"
	@echo ""
	@echo "Buzzer:"
	@echo "  buzzer-build  BUZZER_DEVICE_ID=<id>   Build buzzer firmware with given ID"
	@echo "  buzzer-upload BUZZER_DEVICE_ID=<id>   Find buzzer by ID->MAC, build + upload"
	@echo "  buzzer-monitor BUZZER_DEVICE_ID=<id>  Find buzzer by ID->MAC, open serial monitor"
	@echo ""
	@echo "Util:"
	@echo "  clean                                 Clean both builds"
	@echo ""
	@echo "Config (device_macs.mk):"
	@echo "  CONTROLLER_MAC : $(if $(CONTROLLER_MAC),$(CONTROLLER_MAC),<unset>)"
	@echo "  BUZZER_IDS     : $(if $(BUZZER_IDS),$(BUZZER_IDS),<unset>)"
	@echo "  BUZZER_MACS    : $(if $(BUZZER_MACS),$(BUZZER_MACS),<unset>)"
	@echo ""
	@echo "esptool: $(ESPTOOL)"

# ─── Diagnostic ──────────────────────────────────────────────────────────────

# Prints raw esptool output for every connected port.
# Use this to verify MACs and that esptool can reach devices.
scan:
	@echo "esptool: $(ESPTOOL)"
	@echo ""
	@for port in /dev/ttyUSB* /dev/ttyACM*; do \
	  [ -e "$$port" ] || continue; \
	  echo "=== $$port ==="; \
	  $(ESPTOOL) --chip esp8266 --port $$port read-mac 2>&1 | head -20 || true; \
	  echo ""; \
	done

# Finds the serial port for a given MAC.
# Prints the port path to stdout; progress messages go to stderr.
# Usage: make find-port MAC=AA:BB:CC:11:22:33
find-port:
	@[ -n "$(MAC)" ] || { echo "Usage: make find-port MAC=AA:BB:CC:11:22:33" >&2; exit 1; }
	@for port in /dev/ttyUSB* /dev/ttyACM*; do \
	  [ -e "$$port" ] || continue; \
	  printf "  $$port ... " >&2; \
	  out=$$($(ESPTOOL) --chip esp8266 --port $$port read-mac 2>&1 || true); \
	  if echo "$$out" | grep -qi "$(MAC)"; then \
	    printf "found\n" >&2; \
	    echo $$port; exit 0; \
	  fi; \
	  printf "no match\n" >&2; \
	done; \
	echo "ERROR: no device with MAC $(MAC) found" >&2; exit 1

# Prints the MAC address for a given buzzer ID.
# Prints the MAC to stdout; errors go to stderr.
# Usage: make lookup-buzzer-mac BUZZER_DEVICE_ID=101
lookup-buzzer-mac:
	@[ -n "$(BUZZER_DEVICE_ID)" ] || { echo "Usage: make lookup-buzzer-mac BUZZER_DEVICE_ID=101" >&2; exit 1; }
	@[ -n "$(BUZZER_IDS)"       ] || { echo "ERROR: BUZZER_IDS not set in device_macs.mk" >&2; exit 1; }
	@[ -n "$(BUZZER_MACS)"      ] || { echo "ERROR: BUZZER_MACS not set in device_macs.mk" >&2; exit 1; }
	@idx=1; \
	for id in $(BUZZER_IDS); do \
	  if [ "$$id" = "$(BUZZER_DEVICE_ID)" ]; then \
	    echo $(BUZZER_MACS) | awk -v n=$$idx '{print $$n}'; exit 0; \
	  fi; \
	  idx=$$((idx + 1)); \
	done; \
	echo "ERROR: ID $(BUZZER_DEVICE_ID) not found in BUZZER_IDS ($(BUZZER_IDS))" >&2; exit 1

# ─── Controller ──────────────────────────────────────────────────────────────

controller-build:
	@cd $(CONTROLLER_DIR) && pio run -e $(PIO_ENV)

controller-upload:
	@[ -n "$(CONTROLLER_MAC)" ] || { echo "ERROR: CONTROLLER_MAC not set in device_macs.mk"; exit 1; }
	@port=$$($(MAKE) -s --no-print-directory find-port MAC=$(CONTROLLER_MAC)) || exit 1; \
	echo "controller -> $$port  building and uploading..."; \
	cd $(CONTROLLER_DIR) && pio run -e $(PIO_ENV) --target upload --upload-port $$port

controller-monitor:
	@[ -n "$(CONTROLLER_MAC)" ] || { echo "ERROR: CONTROLLER_MAC not set in device_macs.mk"; exit 1; }
	@port=$$($(MAKE) -s --no-print-directory find-port MAC=$(CONTROLLER_MAC)) || exit 1; \
	echo "controller -> $$port  opening monitor (Ctrl+C to exit)"; \
	cd $(CONTROLLER_DIR) && pio device monitor --port $$port --baud $(BAUD_RATE)

# ─── Buzzer ──────────────────────────────────────────────────────────────────

buzzer-build:
	@[ -n "$(BUZZER_DEVICE_ID)" ] || { echo "ERROR: BUZZER_DEVICE_ID required. e.g. make buzzer-build BUZZER_DEVICE_ID=101"; exit 1; }
	@cd $(BUZZER_DIR) && PLATFORMIO_BUILD_FLAGS="-DDEVICE_ID=$(BUZZER_DEVICE_ID)" pio run -e $(PIO_ENV)

buzzer-upload:
	@[ -n "$(BUZZER_DEVICE_ID)" ] || { echo "ERROR: BUZZER_DEVICE_ID required. e.g. make buzzer-upload BUZZER_DEVICE_ID=101"; exit 1; }
	@mac=$$($(MAKE) -s --no-print-directory lookup-buzzer-mac BUZZER_DEVICE_ID=$(BUZZER_DEVICE_ID)) || exit 1; \
	echo "buzzer ID=$(BUZZER_DEVICE_ID) -> MAC $$mac"; \
	port=$$($(MAKE) -s --no-print-directory find-port MAC=$$mac) || exit 1; \
	echo "buzzer -> $$port  building and uploading..."; \
	cd $(BUZZER_DIR) && PLATFORMIO_BUILD_FLAGS="-DDEVICE_ID=$(BUZZER_DEVICE_ID)" pio run -e $(PIO_ENV) --target upload --upload-port $$port

buzzer-monitor:
	@[ -n "$(BUZZER_DEVICE_ID)" ] || { echo "ERROR: BUZZER_DEVICE_ID required. e.g. make buzzer-monitor BUZZER_DEVICE_ID=101"; exit 1; }
	@mac=$$($(MAKE) -s --no-print-directory lookup-buzzer-mac BUZZER_DEVICE_ID=$(BUZZER_DEVICE_ID)) || exit 1; \
	echo "buzzer ID=$(BUZZER_DEVICE_ID) -> MAC $$mac"; \
	port=$$($(MAKE) -s --no-print-directory find-port MAC=$$mac) || exit 1; \
	echo "buzzer -> $$port  opening monitor (Ctrl+C to exit)"; \
	cd $(BUZZER_DIR) && pio device monitor --port $$port --baud $(BAUD_RATE)

# ─── Util ────────────────────────────────────────────────────────────────────

clean:
	@cd $(CONTROLLER_DIR) && pio run -e $(PIO_ENV) --target clean || true
	@cd $(BUZZER_DIR)     && pio run -e $(PIO_ENV) --target clean || true
	@echo "Done."
