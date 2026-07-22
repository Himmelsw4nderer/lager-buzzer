# LagerBuzzer

A wireless buzzer system for quiz nights and bar games. Buzzers connect via MQTT to a central server running on a computer.

## Hardware

- **Buzzers** — N× Wemos D1 Mini (each has a physical button, identified by a unique ID)
- **Server** — Any computer running the Python MQTT server (Raspberry Pi, laptop, etc.)

## Project Structure

```
firmware/
  buzzer/       PlatformIO project for the buzzer devices
server/        Python web server and MQTT broker interface
Makefile        Build, upload, and monitor automation
device_macs.mk  Local machine config (MACs + IDs) — not committed
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — used to run `esptool` without a manual install
- [PlatformIO CLI](https://docs.platformio.org/en/latest/core/) (`pio`) — for building and uploading firmware
- [Mosquitto MQTT Broker](https://mosquitto.org/) or any MQTT broker
- Python 3.10+ for the server
- Linux: add your user to the `dialout` group for serial port access

```sh
sudo usermod -aG dialout $USER
# log out and back in, or run:
newgrp dialout
```

## Configuration

### 1. device_macs.mk

Create a `device_macs.mk` file in the project root (it is gitignored — never commit device MACs):

```make
BUZZER_MACS    := aa:bb:cc:11:22:33 11:22:33:44:55:66
BUZZER_IDS     := 101 102
```

`BUZZER_MACS` and `BUZZER_IDS` are parallel lists — element N of `BUZZER_IDS` maps to element N of `BUZZER_MACS`.

### 2. Server Configuration

The server can be configured via environment variables:

```sh
# MQTT Broker settings (default: localhost:1883)
export MQTT_BROKER=localhost
export MQTT_PORT=1883

# Web server port (default: 5000)
export WEB_PORT=5000
```

### Finding device MACs

Plug in a device and run:

```sh
make scan
```

This prints the raw `esptool read_mac` output for every connected serial port.

You can also target a specific MAC:

```sh
make find-port MAC=24:a1:60:2e:d1:47
```

## Usage

### Buzzer Firmware

```sh
# Build
make buzzer-build BUZZER_DEVICE_ID=101

# Upload (automatically finds the right port by MAC)
make buzzer-upload BUZZER_DEVICE_ID=101

# Serial monitor
make buzzer-monitor BUZZER_DEVICE_ID=101

# Clean build artifacts
make clean
```

### Running the Server

```sh
# Install dependencies
cd server
pip install -r requirements.txt

# Start the web server (automatically connects to MQTT)
python webserver/app.py

# Or with custom MQTT broker
MQTT_BROKER=192.168.1.100 python webserver/app.py
```

The web interface will be available at `http://localhost:5000`

#### Via Docker

`server/docker-compose.yml` uses [Compose profiles](https://docs.docker.com/compose/how-tos/profiles/)
to keep the webserver and soundboard independent — `mosquitto` and `timesync` always
start, but `webserver` and `soundboard` only start when their profile is active:

```sh
make docker-webserver
# equivalent to: cd server && docker compose --profile webserver up
```

Run both profiles at once with `docker compose --profile webserver --profile soundboard up`
(from `server/`). Stop everything with `make docker-down`.

### Server Discovery

Buzzers don't have the server's IP hardcoded — at boot (and after ~45s of continuous MQTT
disconnection) they broadcast a UDP discovery request on port `42424` and use whichever
address replies as the broker. The `discovery` service in `server/docker-compose.yml`
answers these requests; it always runs regardless of profile (like `mosquitto`/`timesync`)
and needs `network_mode: host` to see broadcast traffic at all, since Docker's default
bridge networking doesn't forward broadcasts into a container.

This means the server's address can change (different network, Pi hotspot on a new
subnet, DHCP lease renewal) without reflashing any buzzer. One caveat: if a Wi-Fi network
has client/AP isolation enabled, broadcasts between stations never arrive and discovery
will fail silently — if buzzers can't find the server, check that setting first.

### Soundboard Service

The `soundboard` service plays a sound file on the server's speakers when a buzzer assigned to the
currently active "mode" is pressed — independent of the quiz/winner-selection flow.

```sh
# Drop your mp3 files into server/soundboard/sounds/ (gitignored)
cp applause.mp3 fail.mp3 server/soundboard/sounds/

make docker-soundboard
# equivalent to: cd server && docker compose --profile soundboard up
```

`make docker-soundboard` auto-creates `server/soundboard/modes.json` from
`modes.json.example` if it doesn't already exist, so the manual copy step is optional —
though you'll still want to edit it (it's gitignored, event-specific) to point at your
own buzzer IDs and sound files before or after first boot.

`modes.json` defines named modes, each with a list of buzzer IDs and a sound file:

```json
{
  "modes": [
    {"name": "applause", "buzzer_ids": ["buzzer-101", "buzzer-102"], "sound_file": "applause.mp3"},
    {"name": "fail", "buzzer_ids": ["buzzer-103"], "sound_file": "fail.mp3"}
  ]
}
```

Switch the active mode via REST (only one mode is active at a time; buzzes are ignored while none
is active):

```sh
curl localhost:5001/api/modes
curl -X POST localhost:5001/api/mode/active \
  -H 'Content-Type: application/json' -d '{"name": "applause"}'
```

## How it works

1. `buzzer-upload BUZZER_DEVICE_ID=101`
   - Looks up the MAC for ID `101` from `device_macs.mk`
   - Scans connected serial ports using `uvx esptool read_mac` to find the matching device
   - Builds the firmware with `-DDEVICE_ID=101` injected as a compile-time flag
   - Uploads to the matched port

2. Buzzers connect to the MQTT broker and publish to the `lagerbuzzer/buzz` topic

3. The server subscribes to the MQTT topic, tracks buzzes, and displays them on the web interface

4. The web interface allows you to:
   - See all connected buzzers
   - View the current winner
   - See runner-ups in order
   - Enable/disable buzzers
   - Rename teams
   - Set team colors
   - Reset rounds
   - Lock buzzers

## License

MIT — see [LICENSE](LICENSE).
