"""Build the 3.3.5a AUTH_REALM_LIST response."""
from __future__ import annotations

import struct
from typing import Dict, Iterable, List, Optional


class Realm:
    def __init__(
        self,
        name: str,
        address: str,
        port: int,
        realm_type: int = 0,
        flags: int = 0,
        population: float = 0.0,
        timezone: int = 1,
        build: int = 12340,
        realm_id: int = 1,
        characters: int = 0,
        locked: int = 0,
    ):
        self.name = name
        self.address = address
        self.port = port
        self.realm_type = realm_type
        self.flags = flags
        self.population = population
        self.timezone = timezone
        self.build = build
        self.realm_id = realm_id
        self.characters = characters
        self.locked = locked


def build_realm_list(
    realms: Iterable[Realm],
    character_counts: Optional[Dict[int, int]] = None,
) -> bytes:
    """Return the complete authserver realm-list packet.

    Wire format (3.3.5a)::

        uint8   cmd (0x10)
        uint16  size            (everything after this field)
        uint32  unknown (0)
        uint16  realm count
        repeated:
            uint8   type
            uint8   locked
            uint8   flags
            cstring name
            cstring "address:port"
            float   population
            uint8   character count
            uint8   timezone
            uint8   realm id
        uint8   0x10
        uint8   0x00
    """
    realms = list(realms)
    counts = character_counts or {}

    body = bytearray()
    body += struct.pack("<I", 0)
    body += struct.pack("<H", len(realms))

    for realm in realms:
        chars = counts.get(realm.realm_id, realm.characters)
        body.append(realm.realm_type & 0xFF)
        body.append(realm.locked & 0xFF)
        body.append(realm.flags & 0xFF)
        body += realm.name.encode("utf-8") + b"\x00"
        body += f"{realm.address}:{realm.port}".encode("utf-8") + b"\x00"
        body += struct.pack("<f", float(realm.population))
        body.append(chars & 0xFF)
        body.append(realm.timezone & 0xFF)
        body.append(realm.realm_id & 0xFF)

        # Only present when REALM_FLAG_SPECIFYBUILD (0x08) is set.
        if realm.flags & 0x08:
            major, minor, patch = 3, 3, 5
            body += bytes([major, minor, patch])
            body += struct.pack("<H", realm.build)

    body += b"\x10\x00"

    return bytes([0x10]) + struct.pack("<H", len(body)) + bytes(body)
