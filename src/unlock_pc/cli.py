"""CLI interface for watchlock."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from unlock_pc.config import DEFAULT_CONFIG_PATH, SETTINGS, load_config, save_device, set_setting
from unlock_pc.signal_proc import rssi_to_distance


@click.group(epilog="""
\b
Available settings for 'watchlock set <key> <value>':
  unlock-distance    Distance (m) below which the PC unlocks        [default: 5.0]
  lock-distance      Distance (m) above which the PC locks          [default: 6.0]
  grace-period       Seconds to wait before locking after signal loss [default: 10.0]
  absence-timeout    Seconds without signal before watch is gone     [default: 25.0]
  stability-readings Consecutive readings before changing state      [default: 3]
  scan-interval      Seconds between BLE scan cycles                 [default: 1.0]
  tx-power           RSSI at 1m (dBm), calibrate with 'watchlock scan' [default: -59]
  smoothing-alpha    EMA factor (0-1), lower = smoother              [default: 0.3]
  max-jump           Max RSSI jump per reading, spikes are clamped   [default: 20]
  path-loss          Environment: 2.0=open, 2.5=office, 3.0=walls   [default: 2.5]
  log-level          DEBUG, INFO, WARNING, or ERROR                  [default: INFO]

Examples:
  watchlock set grace-period 15
  watchlock set lock-distance 5
  watchlock set log-level DEBUG
""")
@click.option("--config", "-c", "config_path", type=click.Path(path_type=Path), default=None,
              help=f"Config file path (default: {DEFAULT_CONFIG_PATH})")
@click.pass_context
def main(ctx: click.Context, config_path: Path | None) -> None:
    """watchlock - Lock/unlock your PC based on your watch's BLE proximity."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


@main.command(short_help="Scan for nearby BLE devices")
@click.option("--timeout", "-t", default=10.0, help="Scan duration in seconds")
def scan(timeout: float) -> None:
    """Scan for nearby BLE devices with RSSI and estimated distance."""
    from unlock_pc.scanner import discover_devices

    click.echo(f"Scanning for BLE devices ({timeout:.0f}s)...\n")

    devices = asyncio.run(discover_devices(timeout))

    if not devices:
        click.echo("No BLE devices found.")
        return

    click.echo(f"{'ADDRESS':<20} {'RSSI':>6} {'DISTANCE':>10} {'NAME'}")
    click.echo("-" * 60)

    for dev in devices:
        dist = rssi_to_distance(dev.rssi)
        name = dev.name or "(unknown)"
        tag = " (paired)" if dev.via_connection else ""
        click.echo(f"{dev.address:<20} {dev.rssi:>4} dBm {dist:>8.1f}m  {name}{tag}")


@main.command(short_help="Select your watch and save it to config")
@click.option("--paired", "-p", is_flag=True, help="Pick from already paired devices (skip BLE scan)")
@click.pass_context
def pair(ctx: click.Context, paired: bool) -> None:
    """Select your watch from nearby BLE devices and save it to config.

    Use --paired to pick directly from devices already paired in bluetoothctl,
    useful when your watch is connected but not visible via BLE scan.
    """
    from unlock_pc.scanner import _get_paired_devices, discover_devices

    config_path = ctx.obj.get("config_path")

    if paired:
        click.echo("Fetching paired devices from bluetoothctl...\n")
        paired_devs = asyncio.run(_get_paired_devices())
        if not paired_devs:
            click.echo("No paired devices found. Pair your watch first with bluetoothctl.")
            sys.exit(1)

        click.echo(f"{'#':<4} {'ADDRESS':<20} {'NAME'}")
        click.echo("-" * 50)
        for i, (address, name) in enumerate(paired_devs, 1):
            click.echo(f"{i:<4} {address:<20} {name}")

        click.echo()
        choice = click.prompt("Select device number", type=int)
        if choice < 1 or choice > len(paired_devs):
            click.echo("Invalid selection.")
            sys.exit(1)

        selected_address, selected_name = paired_devs[choice - 1]
        save_device(selected_address, selected_name, config_path)
        click.echo(f"\nSaved: {selected_name} ({selected_address})")
        click.echo(f"Config: {config_path or DEFAULT_CONFIG_PATH}")
        return

    click.echo("Scanning for BLE devices (10s)...\n")
    click.echo("Make sure your watch is nearby and Bluetooth is active.\n")

    devices = asyncio.run(discover_devices(10.0))

    if not devices:
        click.echo("No devices found. Try 'watchlock pair --paired' to pick from paired devices.")
        sys.exit(1)

    click.echo(f"\n{'#':<4} {'ADDRESS':<20} {'RSSI':>6} {'NAME'}")
    click.echo("-" * 50)

    for i, dev in enumerate(devices, 1):
        name = dev.name or "(unknown)"
        tag = " (paired)" if dev.via_connection else ""
        click.echo(f"{i:<4} {dev.address:<20} {dev.rssi:>4} dBm  {name}{tag}")

    click.echo()
    choice = click.prompt("Select device number", type=int)

    if choice < 1 or choice > len(devices):
        click.echo("Invalid selection.")
        sys.exit(1)

    selected = devices[choice - 1]
    name = selected.name or click.prompt("Device name")

    save_device(selected.address, name, config_path)
    click.echo(f"\nSaved: {name} ({selected.address})")
    click.echo(f"Config: {config_path or DEFAULT_CONFIG_PATH}")


@main.command(short_help="Show current configuration")
@click.pass_context
def show(ctx: click.Context) -> None:
    """Show current configuration and all settings."""
    config_path = ctx.obj.get("config_path")
    config = load_config(config_path)

    click.echo(f"Config: {config_path or DEFAULT_CONFIG_PATH}\n")
    click.echo(f"  Device:             {config.device_name} ({config.device_address})")
    click.echo(f"  unlock-distance:    {config.unlock_max_distance}m")
    click.echo(f"  lock-distance:      {config.lock_min_distance}m")
    click.echo(f"  grace-period:       {config.grace_period}s")
    click.echo(f"  absence-timeout:    {config.absence_timeout}s")
    click.echo(f"  stability-readings: {config.stability_readings}")
    click.echo(f"  scan-interval:      {config.scan_interval}s")
    click.echo(f"  tx-power:           {config.tx_power} dBm")
    click.echo(f"  smoothing-alpha:    {config.smoothing_alpha}")
    click.echo(f"  max-jump:           {config.max_rssi_jump} dBm")
    click.echo(f"  path-loss:          {config.path_loss_exponent}")
    click.echo(f"  log-level:          {config.log_level}")


@main.command("set", short_help="Change a setting (see keys below)", context_settings={"ignore_unknown_options": True})
@click.argument("key", type=click.Choice(sorted(SETTINGS.keys()), case_sensitive=False))
@click.argument("value")
@click.pass_context
def set_cmd(ctx: click.Context, key: str, value: str) -> None:
    """Change a setting. Restarts the daemon automatically if running.

    \b
    Settings:
      unlock-distance    Distance (m) below which the PC unlocks
      lock-distance      Distance (m) above which the PC locks
      grace-period       Seconds to wait before locking after signal loss
      absence-timeout    Seconds without signal before watch is considered gone
      stability-readings Consecutive readings required before changing state
      scan-interval      Seconds between BLE scan cycles
      tx-power           RSSI at 1m (dBm), calibrate with 'watchlock scan'
      smoothing-alpha    EMA factor (0-1), lower = smoother
      max-jump           Max RSSI jump per reading (dBm), spikes are clamped
      path-loss          Environment: 2.0=open, 2.5=office, 3.0=walls
      log-level          DEBUG, INFO, WARNING, or ERROR

    \b
    Examples:
      watchlock set grace-period 15
      watchlock set lock-distance 5
      watchlock set log-level DEBUG
    """
    config_path = ctx.obj.get("config_path")
    try:
        set_setting(key, value, config_path)
    except (ValueError, KeyError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"{key} = {value}")

    import subprocess

    result = subprocess.run(
        ["systemctl", "--user", "is-active", "watchlock"],
        capture_output=True, text=True,
    )
    if result.stdout.strip() == "active":
        subprocess.run(["systemctl", "--user", "restart", "watchlock"])
        click.echo("Daemon restarted.")


@main.command(short_help="Start daemon + auto-start at login")
def enable() -> None:
    """Start the daemon and enable auto-start at login."""
    import shutil
    import subprocess

    service_dst = Path.home() / ".config" / "systemd" / "user" / "watchlock.service"
    service_dst.parent.mkdir(parents=True, exist_ok=True)

    watchlock_bin = shutil.which("watchlock")
    if not watchlock_bin:
        venv_bin = Path(sys.executable).parent / "watchlock"
        if venv_bin.exists():
            watchlock_bin = str(venv_bin)
        else:
            click.echo("Error: 'watchlock' not found. Install with: pipx install .", err=True)
            sys.exit(1)

    service_dst.write_text(
        f"[Unit]\n"
        f"Description=watchlock BLE proximity lock/unlock daemon\n"
        f"After=bluetooth.target\n\n"
        f"[Service]\n"
        f"Type=simple\n"
        f"ExecStart={watchlock_bin} run\n"
        f"Restart=on-failure\n"
        f"RestartSec=5\n\n"
        f"[Install]\n"
        f"WantedBy=default.target\n"
    )

    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", "--now", "watchlock"])
    click.echo("Daemon enabled and started. It will auto-start at login.")


@main.command(short_help="Stop daemon + disable auto-start")
def disable() -> None:
    """Stop the daemon and disable auto-start."""
    import subprocess

    subprocess.run(["systemctl", "--user", "disable", "--now", "watchlock"])
    click.echo("Daemon stopped and disabled.")


@main.command(short_help="Show daemon status")
def status() -> None:
    """Show whether the daemon is running."""
    import subprocess

    subprocess.run(["systemctl", "--user", "status", "watchlock", "--no-pager"])


@main.command(short_help="Run daemon in foreground (debug)")
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def run(ctx: click.Context, debug: bool) -> None:
    """Start the daemon in the foreground (prefer 'watchlock enable')."""
    from unlock_pc.daemon import run_daemon

    config_path = ctx.obj.get("config_path")
    config = load_config(config_path)

    log_level = "DEBUG" if debug else config.log_level
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        config.validate()
    except ValueError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    click.echo("watchlock daemon starting")
    click.echo(f"  Target: {config.device_name} ({config.device_address})")
    click.echo(f"  Unlock distance: < {config.unlock_max_distance}m")
    click.echo(f"  Lock distance:   > {config.lock_min_distance}m")
    click.echo(f"  Grace period:    {config.grace_period}s")
    click.echo()

    try:
        asyncio.run(run_daemon(config))
    except KeyboardInterrupt:
        click.echo("\nDaemon stopped.")
