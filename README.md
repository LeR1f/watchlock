# BLuELock

Lock and unlock your Linux PC automatically based on Bluetooth device proximity.

When your device is nearby, your PC stays unlocked. Walk away and it locks. Come back and it unlocks. Like Apple Watch unlock for Mac, but for Linux with any Bluetooth device — watch, phone, earbuds, fitness tracker, etc.

## How it works

bluelock continuously scans for your Bluetooth device's signal. It estimates distance from RSSI and:

- **Unlocks** when the device is closer than 5m (configurable)
- **Locks** when the device is farther than 6m (configurable)
- Uses hysteresis, EMA smoothing, and spike rejection to avoid false triggers

If you unlock your PC manually (password) without the device nearby, it stays unlocked until the device is detected at least once.

## Requirements

- Linux with BlueZ (most distros)
- Python 3.11+
- A Bluetooth device (tested with Galaxy Watch 5, works with phones, earbuds, etc.)
- Your device must be paired via `bluetoothctl` (one-time setup)

## Install

```bash
git clone https://github.com/LeR1f/BLuELock.git
cd BLuELock
pipx install .
```

## Quick start

```bash
# 1. Find your watch
bluelock scan

# 2. Select and save it (use --paired if your watch doesn't show in scan)
bluelock pair
bluelock pair --paired

# 3. Start the daemon (auto-starts at login)
bluelock enable
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
| `bluelock scan` | Scan for nearby devices (BLE + paired via connection) |
| `bluelock pair` | Select your watch from scan results and save to config |
| `bluelock pair --paired` | Pick directly from already paired devices (skip scan) |
| `bluelock show` | Show current configuration |
| `bluelock set <key> <value>` | Change a setting (auto-restarts daemon) |
| `bluelock enable` | Start daemon + auto-start at login |
| `bluelock disable` | Stop daemon + disable auto-start |
| `bluelock status` | Show daemon status |
| `bluelock run` | Run daemon in foreground (for debugging) |

Every command supports `--help` for details.

## Settings

Adjust any setting with `bluelock set <key> <value>`:

### `unlock-distance` (default: 5.0m, min: 0.1, max: 15.0)

Distance below which the PC unlocks. At 5m this covers a typical room — your PC unlocks as soon as you walk in. Lower it if you want to be closer before it unlocks.

### `lock-distance` (default: 6.0m, min: 0.1, max: 15.0)

Distance above which the PC locks. The gap between `unlock-distance` and `lock-distance` creates a buffer zone (hysteresis) to prevent rapid lock/unlock toggling when you're near the boundary. Between 5m and 6m, nothing happens — the PC keeps its current state.

### `grace-period` (default: 10.0s, min: 0.0, max: 300.0)

How long to wait before locking once the watch is detected as far away. Protects against brief Bluetooth dropouts. If your PC locks too quickly when you just stand up to grab something, increase this value.

### `absence-timeout` (default: 25.0s, min: 1.0, max: 300.0)

How long without any BLE signal before the watch is considered gone. BLE can occasionally miss a scan. Too low = false positives. Too high = slow to lock when you actually leave.

### `stability-readings` (default: 3, min: 1, max: 20)

Number of consecutive readings confirming the same state (near/far) before triggering a change. Prevents a single bad reading from causing a lock/unlock. 3 means 3 scans in a row must agree.

### `scan-interval` (default: 1.0s, min: 0.1, max: 60.0)

Time between BLE scans. 1s = one scan per second. Lower = more responsive but uses more battery (PC and watch). Higher = slower to react.

### `tx-power` (default: -59 dBm, min: -100, max: 0)

The RSSI measured when the watch is exactly 1 meter away. This is the reference point for distance calculation. Every watch transmits differently — calibrate by holding your watch 1m from the PC, running `bluelock scan`, and noting the RSSI value.

### `smoothing-alpha` (default: 0.3, min: 0.01, max: 1.0)

EMA (Exponential Moving Average) smoothing factor. 0.3 = 30% weight on the new reading, 70% on history. Lower (0.1) = very smooth but slow to react. Higher (0.8) = responsive but jittery.

### `max-jump` (default: 20 dBm, min: 1, max: 100)

Maximum RSSI change allowed between two readings. If RSSI jumps more than 20 dBm at once, it's treated as a spike and clamped. Protects against sudden interference.

### `path-loss` (default: 2.5, min: 1.0, max: 5.0)

Models the environment for RSSI-to-distance conversion. 2.0 = open space with no obstacles. 2.5 = typical office. 3.0 = walls/obstacles between you and the PC. Directly affects distance estimates.

### `log-level` (default: INFO, values: DEBUG, INFO, WARNING, ERROR)

Log verbosity. Use DEBUG to diagnose issues, INFO for normal use, WARNING or ERROR for quiet operation.

### Examples

```bash
bluelock set grace-period 15        # more time before locking
bluelock set lock-distance 8        # lock at 8m instead of 6m
bluelock set log-level DEBUG        # verbose logging
```

## How locking works

```
Watch nearby (< 5m)  →  PC unlocked
Watch far (> 6m)     →  grace period (10s)  →  PC locked
Watch returns (< 5m) →  PC unlocked (grace cancelled)
No signal (25s)      →  grace period (10s)  →  PC locked
```

The gap between 5m and 6m is intentional (hysteresis) to prevent the PC from rapidly locking/unlocking when you're at the boundary.

## Troubleshooting

**Watch not detected by `bluelock scan`:**
- Make sure Bluetooth is on: `bluetoothctl show | grep Powered`
- Pair your watch first: `bluetoothctl pair XX:XX:XX:XX:XX:XX`
- Some watches don't advertise via BLE once paired — use `bluelock pair --paired` to pick from already paired devices

**PC locks when I'm at my desk:**
- Increase grace period: `bluelock set grace-period 20`
- Increase absence timeout: `bluelock set absence-timeout 35`
- Increase stability readings: `bluelock set stability-readings 5`

**Distance estimates are off:**
- Calibrate tx-power: hold your watch 1m from the PC, run `bluelock scan`, note the RSSI, then `bluelock set tx-power <value>`
- Adjust path-loss for your environment

**Check daemon logs:**
```bash
journalctl --user -u bluelock -f
```

## License

MIT
