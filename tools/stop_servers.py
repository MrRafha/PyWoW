#!/usr/bin/env python3
"""Stop leftover ManaWoW auth/world server processes.

Finds the PIDs listening on the configured authserver/worldserver ports and
terminates them if they belong to this project's run scripts. This is handy
when ``run_auth.py`` reports "Port 3724 is already in use" because a server
from an earlier terminal (or an old background process) is still running.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.common.config import Config  # noqa: E402


def _load_config() -> Config:
    cfg_path = os.path.join(ROOT, "config", "config.yaml")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(ROOT, "config", "config.example.yaml")
    return Config.load(cfg_path)


def _listening_pids(port: int) -> set[int]:
    try:
        output = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"], text=True, errors="replace", timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    pids: set[int] = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
            continue
        if parts[1].endswith(f":{port}"):
            try:
                pids.add(int(parts[4]))
            except ValueError:
                pass
    return pids


def _command_line(pid: int) -> str:
    try:
        output = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
            ],
            text=True,
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return output.strip()


def _is_our_server(pid: int) -> bool:
    cmdline = _command_line(pid).lower()
    if not cmdline:
        return False
    return "run_auth.py" in cmdline or "run_world.py" in cmdline or "run_servers.py" in cmdline


def main() -> int:
    force = "--force" in sys.argv[1:]
    cfg = _load_config()
    ports = [cfg.authserver.port, cfg.worldserver.port]

    targets: dict[int, set[int]] = {}
    for port in ports:
        for pid in _listening_pids(port):
            targets.setdefault(pid, set()).add(port)

    if not targets:
        print(f"Ports {', '.join(str(p) for p in ports)}: free; nothing to stop.")
        return 0

    stopped = 0
    for pid, held_ports in sorted(targets.items()):
        held = ", ".join(str(p) for p in sorted(held_ports))
        if not force and not _is_our_server(pid):
            print(
                f"PID {pid} on port(s) {held} does not look like a ManaWoW server; "
                "leaving it alone (use --force to kill it anyway)"
            )
            continue
        print(f"Stopping PID {pid} (port(s) {held})")
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            errors="replace",
        )
        stopped += 1

    if stopped:
        print(f"Stopped {stopped} process(es). You can start the servers again.")
    else:
        print("Nothing was stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
