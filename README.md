# Lager Buzzer

A wireless buzzer system for quiz nights and bar games built on ESP8266 (D1 Mini) using ESP-NOW for low-latency peer-to-peer communication.

## Hardware

- **Controller** — 1× Wemos D1 Mini (manages game state, receives buzzer presses)
- **Buzzers** — N× Wemos D1 Mini (each has a physical button, identified by a unique ID)

## Project Structure

```
firmware/
  controller/   PlatformIO project for the controller device
  buzzer/       PlatformIO project for the buzzer devices
Makefile        Build, upload, and monitor automation
device_macs.mk  Local machine config (MACs + IDs) — not committed
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — used to run `esptool` without a manual install
- [PlatformIO CLI](https://docs.platformio.org/en/latest/core/) (`pio`) — for building and uploading firmware
- Linux: add your user to the `dialout` group for serial port access

```sh
sudo usermod -aG dialout $USER
# log out and back in, or run:
newgrp dialout
```

## Configuration

Create a `device_macs.mk` file in the project root (it is gitignored — never commit device MACs):

```make
CONTROLLER_MAC := aa:bb:cc:11:22:33
BUZZER_MACS    := 24:a1:60:2e:d1:47 84:cc:a8:82:99:9b 8c:ce:4e:d4:51:f9
BUZZER_IDS     := 101 102 103
```

`BUZZER_MACS` and `BUZZER_IDS` are parallel lists — element N of `BUZZER_IDS` maps to element N of `BUZZER_MACS`.

### Finding device MACs

Plug in a device and run:

```sh
make scan
```

This prints the raw `esptool read_mac` output for every connected serial port.

You can also target a specific MAC or ID:

```sh
make find-port MAC=24:a1:60:2e:d1:47
make lookup-buzzer-mac BUZZER_DEVICE_ID=101
```

## Usage

```sh
# Build
make controller-build
make buzzer-build BUZZER_DEVICE_ID=101

# Upload (automatically finds the right port by MAC)
make controller-upload
make buzzer-upload BUZZER_DEVICE_ID=101

# Serial monitor
make controller-monitor
make buzzer-monitor BUZZER_DEVICE_ID=101

# Clean build artifacts
make clean
```

## How it works

1. `buzzer-upload BUZZER_DEVICE_ID=101`
   - Looks up the MAC for ID `101` from `device_macs.mk`
   - Scans connected serial ports using `uvx esptool read_mac` to find the matching device
   - Builds the firmware with `-DDEVICE_ID=101` injected as a compile-time flag
   - Uploads to the matched port

2. The controller is uploaded the same way, matched by `CONTROLLER_MAC`.

## License

MIT — see [LICENSE](LICENSE).
