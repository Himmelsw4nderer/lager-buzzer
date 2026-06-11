# Lagerbuzzer Makefile
#
# Create device_macs.mk next to this file:
#   BUZZER_MACS    := AA:BB:CC:11:22:33 11:22:33:44:55:66
#   BUZZER_IDS     := 101 102

.PHONY: help identify find-port lookup-buzzer-mac \
        buzzer-build buzzer-upload buzzer-monitor \
        scan clean

FIRMWARE_DIR    := firmware
BUZZER_DIR      := $(FIRMWARE_DIR)/buzzer
PIO_ENV        := d1_mini
BAUD_RATE      := 115200

-include device_macs.mk

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
	@echo "  identify                              Scan ports and label each device (buzzer/unknown)"
	@echo "  scan                                  Shortcut for identify"
	@echo "  find-port MAC=<mac>                   Find the serial port for a given MAC"
	@echo "  lookup-buzzer-mac BUZZER_DEVICE_ID=<> Print the MAC for a given buzzer ID"
	@echo ""
	@echo "Buzzer:"
	@echo "  buzzer-build  BUZZER_DEVICE_ID=<id>   Build buzzer firmware with given ID"
	@echo "  buzzer-upload BUZZER_DEVICE_ID=<id>   Find buzzer by ID->MAC, build + upload"
	@echo "  buzzer-monitor BUZZER_DEVICE_ID=<id>  Find buzzer by ID->MAC, open serial monitor"
	@echo ""
	@echo "Util:"
	@echo "  clean                                 Clean build artifacts"
	@echo ""
	@echo "Config (device_macs.mk):"
	@echo "  BUZZER_IDS      : $(if $(BUZZER_IDS),$(BUZZER_IDS),<unset>)"
	@echo "  BUZZER_MACS     : $(if $(BUZZER_MACS),$(BUZZER_MACS),<unset>)"
	@echo ""
	@echo "esptool: $(ESPTOOL)"

# ─── Diagnostic ──────────────────────────────────────────────────────────────

# Scans connected ports and labels each device against device_macs.mk.
identify: scan

scan:
	@for port in /dev/ttyUSB* /dev/ttyACM*; do \
	  [ -e "$$port" ] || continue; \
	  out=$$($(ESPTOOL) --chip auto --port $$port read-mac 2>&1 || true); \
	  mac=$$(echo "$$out" | grep -i "MAC:" | head -1 | awk '{print tolower($$NF)}'); \
	  [ -n "$$mac" ] || { echo "  $$port  could not read MAC"; continue; }; \
	  label="unknown"; \
	  idx=1; \
	  for bmac in $(BUZZER_MACS); do \
	    if [ "$$(echo $$bmac | tr A-Z a-z)" = "$$mac" ]; then \
	      id=$$(echo $(BUZZER_IDS) | awk -v n=$$idx '{print $$n}'); \
	      label="buzzer  ID=$$id"; \
	      break; \
	    fi; \
	    idx=$$((idx + 1)); \
	  done; \
	  echo "  $$port  $$mac  $$label"; \
	done

# Finds the serial port for a given MAC.
# Prints the port path to stdout; progress messages go to stderr.
# Usage: make find-port MAC=AA:BB:CC:11:22:33
find-port:
	@[ -n "$(MAC)" ] || { echo "Usage: make find-port MAC=AA:BB:CC:11:22:33" >&2; exit 1; }
	@for port in /dev/ttyUSB* /dev/ttyACM*; do \
	  [ -e "$$port" ] || continue; \
	  printf "  $$port ... " >&2; \
	  out=$$($(ESPTOOL) --chip auto --port $$port read-mac 2>&1 || true); \
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
	@cd $(BUZZER_DIR) && pio run -e $(PIO_ENV) --target clean || true
	@echo "Done."
