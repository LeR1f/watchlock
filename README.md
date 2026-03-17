# watchlock

Lock and unlock your Linux PC automatically based on your Bluetooth watch's proximity.

When your watch is nearby, your PC stays unlocked. Walk away and it locks. Come back and it unlocks. Like Apple Watch unlock for Mac, but for Linux with any BLE watch.

## How it works

watchlock continuously scans for your watch's BLE signal. It estimates distance from RSSI and:

- **Unlocks** when the watch is closer than 2m (configurable)
- **Locks** when the watch is farther than 4m (configurable)
- Uses hysteresis, EMA smoothing, and spike rejection to avoid false triggers

If you unlock your PC manually (password) without the watch nearby, it stays unlocked until the watch is detected at least once.

## Requirements

- Linux with BlueZ (most distros)
- Python 3.11+
- A Bluetooth LE watch (tested with Galaxy Watch 5)
- Your watch must be paired via `bluetoothctl` (one-time setup)

## Install

```bash
git clone https://github.com/youruser/watchlock.git
cd watchlock
pip install .
```

## Quick start

```bash
# 1. Find your watch
watchlock scan

# 2. Select and save it
watchlock pair

# 3. Start the daemon (auto-starts at login)
watchlock enable
```

That's it. Your PC now locks when you walk away and unlocks when you come back.

## Bluetooth pairing

Your watch needs to be paired in BlueZ for reliable detection. This is a one-time setup:

```bash
bluetoothctl scan on          # wait for your watch to appear
bluetoothctl pair XX:XX:XX:XX:XX:XX   # replace with your watch's MAC
```

On Samsung Galaxy Watch, you may need to initiate the connection from the watch: Settings > Connections > Bluetooth > pair with your PC.

## Commands

| Command | Description |
|---|---|
| `watchlock scan` | Scan for nearby BLE devices with RSSI and distance |
| `watchlock pair` | Select your watch and save it to config |
| `watchlock show` | Show current configuration |
| `watchlock set <key> <value>` | Change a setting (auto-restarts daemon) |
| `watchlock enable` | Start daemon + auto-start at login |
| `watchlock disable` | Stop daemon + disable auto-start |
| `watchlock status` | Show daemon status |
| `watchlock run` | Run daemon in foreground (for debugging) |

Every command supports `--help` for details.

## Settings

Adjust any setting with `watchlock set <key> <value>`:

| Setting | Default | Description |
|---|---|---|
| `unlock-distance` | 2.0 | Distance (m) below which the PC unlocks |
| `lock-distance` | 4.0 | Distance (m) above which the PC locks |
| `grace-period` | 10.0 | Seconds to wait before locking after signal loss |
| `absence-timeout` | 25.0 | Seconds without signal before watch is gone |
| `stability-readings` | 3 | Consecutive readings before changing state |
| `scan-interval` | 1.0 | Seconds between BLE scans |
| `tx-power` | -59 | RSSI at 1m (dBm), calibrate with `watchlock scan` |
| `smoothing-alpha` | 0.3 | EMA factor (0-1), lower = smoother |
| `max-jump` | 20 | Max RSSI jump per reading, spikes are clamped |
| `path-loss` | 2.5 | Environment: 2.0=open, 2.5=office, 3.0=walls |
| `log-level` | INFO | DEBUG, INFO, WARNING, or ERROR |

Examples:

```bash
watchlock set grace-period 15        # more time before locking
watchlock set lock-distance 5        # lock at 5m instead of 4m
watchlock set log-level DEBUG        # verbose logging
```

## How locking works

```
Watch nearby (< 2m)  →  PC unlocked
Watch far (> 4m)     →  grace period (10s)  →  PC locked
Watch returns (< 2m) →  PC unlocked (grace cancelled)
No signal (25s)      →  grace period (10s)  →  PC locked
```

The gap between 2m and 4m is intentional (hysteresis) to prevent the PC from rapidly locking/unlocking when you're at the boundary.

## Troubleshooting

**Watch not detected by `watchlock scan`:**
- Make sure Bluetooth is on: `bluetoothctl show | grep Powered`
- Pair your watch first: `bluetoothctl pair XX:XX:XX:XX:XX:XX`

**PC locks when I'm at my desk:**
- Increase grace period: `watchlock set grace-period 20`
- Increase absence timeout: `watchlock set absence-timeout 35`
- Increase stability readings: `watchlock set stability-readings 5`

**Distance estimates are off:**
- Calibrate tx-power: hold your watch 1m from the PC, run `watchlock scan`, note the RSSI, then `watchlock set tx-power <value>`
- Adjust path-loss for your environment

**Check daemon logs:**
```bash
journalctl --user -u watchlock -f
```

## License

MIT
