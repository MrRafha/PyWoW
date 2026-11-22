#!/usr/bin/env python3
"""Point a 3.3.5a client at this server and turn on unit nameplates.

A fresh client install has no ``WTF/Config.wtf``, and 3.3.5a defaults to
friendly nameplates *off*: the server can answer every creature query (and the
client caches the names in ``Cache/WDB/enUS/creaturecache.wdb``), but no name
is drawn over a friendly NPC until ``nameplateShowFriends`` is enabled.  That
is why NPC names look missing on a clean install until the unit is clicked.

Usage::

    python tools/apply_client_settings.py "C:\\path\\to\\client"
    python tools/apply_client_settings.py --search

``--search`` looks for ``Wow.exe`` in the usual places (Desktop, Documents,
C:\\Games, C:\\World of Warcraft) and patches every client it finds.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

REALM_ADDRESS = "127.0.0.1"

# CVars that make every unit (NPC, pet, guardian, totem) show its nameplate
# and therefore its name, exactly like a retail 3.3.5a client with "show all
# nameplates" enabled.  Keys are matched case-insensitively.
SETTINGS = {
    "nameplateShowFriends": "1",
    "nameplateShowEnemies": "1",
    "nameplateShowFriendlyPets": "1",
    "nameplateShowFriendlyGuardians": "1",
    "nameplateShowFriendlyTotems": "1",
    "nameplateShowEnemyPets": "1",
    "nameplateShowEnemyGuardians": "1",
    "nameplateShowEnemyTotems": "1",
    "nameplateAllowOverlap": "1",
}


def _read_lines(path: str) -> list[str]:
    try:
        # ``utf-8-sig`` also eats a BOM: the 3.3.5 client ignores a Config.wtf
        # that starts with one, so never round-trip the BOM back into the file.
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            return handle.read().splitlines()
    except FileNotFoundError:
        return []


def _write_lines(path: str, lines: list[str]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write("\n".join(lines).rstrip("\n") + "\n")


def patch_config(config_path: str) -> None:
    """Insert or replace the settings in ``Config.wtf``, keeping other lines."""
    lines = _read_lines(config_path)
    remaining = dict(SETTINGS)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped[:4].upper() == "SET ":
            key = stripped[4:].split(None, 1)[0].strip('"')
            for wanted in list(remaining):
                if key.lower() == wanted.lower():
                    out.append(f'SET {wanted} "{remaining.pop(wanted)}"')
                    break
            else:
                out.append(line)
        elif stripped:
            out.append(line)
    for key, value in remaining.items():
        out.append(f'SET {key} "{value}"')
    _write_lines(config_path, out)
    print(f"  patched {config_path}")


def patch_realmlist(client_dir: str) -> None:
    """Make sure Data/<locale>/realmlist.wtf points at this server."""
    data_dir = os.path.join(client_dir, "Data")
    if not os.path.isdir(data_dir):
        return
    patched = False
    for locale in sorted(os.listdir(data_dir)):
        locale_dir = os.path.join(data_dir, locale)
        if not os.path.isdir(locale_dir):
            continue
        path = os.path.join(locale_dir, "realmlist.wtf")
        if os.path.isfile(path):
            _write_lines(path, [f"set realmlist {REALM_ADDRESS}"])
            print(f"  patched {path}")
            patched = True
    if not patched:
        # A brand-new client may not have one yet; enUS is the safe default.
        path = os.path.join(data_dir, "enUS", "realmlist.wtf")
        _write_lines(path, [f"set realmlist {REALM_ADDRESS}"])
        print(f"  created {path}")


ADDON_NAME = "ManaWoWNameplates"
ADDON_SOURCE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "client_addons", ADDON_NAME
)


def install_addon(client_dir: str) -> None:
    """Copy the bundled ManaWoWNameplates addon into the client.

    The addon re-applies the nameplate CVars on every login.  That matters
    because the client rewrites ``WTF/Config.wtf`` on exit and a stock 3.3.5a
    install defaults friendly nameplates back to off.
    """
    dest = os.path.join(client_dir, "Interface", "AddOns", ADDON_NAME)
    if not os.path.isdir(ADDON_SOURCE):
        print(f"  addon source missing, skipped: {ADDON_SOURCE}")
        return
    os.makedirs(dest, exist_ok=True)
    for name in sorted(os.listdir(ADDON_SOURCE)):
        source = os.path.join(ADDON_SOURCE, name)
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(dest, name))
    print(f"  installed {dest}")


def patch_client(client_dir: str) -> None:
    client_dir = os.path.abspath(client_dir)
    exe = os.path.join(client_dir, "Wow.exe")
    if not os.path.isfile(exe):
        raise SystemExit(f"not a 3.3.5a client folder (no Wow.exe): {client_dir}")
    print(f"client: {client_dir}")
    patch_config(os.path.join(client_dir, "WTF", "Config.wtf"))
    patch_realmlist(client_dir)
    install_addon(client_dir)


def find_clients() -> list[str]:
    roots = [
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "Documents"),
        r"C:\Games",
        r"C:\World of Warcraft",
    ]
    found: list[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {"Cache", "WTF", "Logs", "Interface", "Data"}]
            if "Wow.exe" in files:
                found.append(current)
                dirs[:] = []
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", nargs="?", help="client folder containing Wow.exe")
    parser.add_argument("--search", action="store_true",
                        help="find clients under Desktop/Documents/C:\\Games")
    args = parser.parse_args(argv)

    if args.search:
        clients = find_clients()
        if not clients:
            print("No Wow.exe found. Pass the client folder explicitly.")
            return 1
    elif args.client:
        clients = [args.client]
    else:
        parser.print_help()
        return 2

    for client in clients:
        try:
            patch_client(client)
        except SystemExit as exc:
            print(exc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
