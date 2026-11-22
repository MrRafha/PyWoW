"""Packet header handling for WoW 3.3.5a."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional, Tuple

CLIENT_HEADER_SIZE = 6
CLIENT_OPCODE_SIZE = 4


class ServerPacketHeader:
    """Server -> client header.

    ``size`` is the payload length plus the 2-byte opcode.  Packets larger
    than 0x7FFF use an extra high byte instead of the usual 2-byte size.
    """

    def __init__(self, size: int, opcode: int):
        self.size = size
        self.opcode = opcode
        self.header_bytes = bytearray()
        header_index = 0
        if self.is_large_packet():
            self.header_bytes.append(0x80 | (0xFF & (size >> 16)))
            header_index += 1
        self.header_bytes.append(0xFF & (size >> 8))
        self.header_bytes.append(0xFF & size)
        # opcode little endian
        self.header_bytes.append(0xFF & opcode)
        self.header_bytes.append(0xFF & (opcode >> 8))

    def is_large_packet(self) -> bool:
        return self.size > 0x7FFF

    def get_header_length(self) -> int:
        return 2 + (3 if self.is_large_packet() else 2)

    def build(self) -> bytes:
        return bytes(self.header_bytes)


@dataclass
class ClientPacketHeader:
    """Client -> server header (always 6 bytes in 3.3.5a).

    ``size`` is big-endian and includes the 4-byte opcode.  The opcode itself
    is little-endian.  The whole 6-byte header is RC4-encrypted once the world
    session has been authenticated.
    """

    size: int
    opcode: int

    @property
    def payload_size(self) -> int:
        return self.size - CLIENT_OPCODE_SIZE

    def is_valid(self) -> bool:
        return CLIENT_OPCODE_SIZE <= self.size <= 0x8000

    def build(self) -> bytes:
        return struct.pack(">H", self.size) + struct.pack("<I", self.opcode)

    @classmethod
    def parse(cls, data: bytes) -> Optional[Tuple["ClientPacketHeader", int]]:
        """Parse a plaintext 6-byte client header."""
        if len(data) < CLIENT_HEADER_SIZE:
            return None
        size = struct.unpack(">H", data[0:2])[0]
        opcode = struct.unpack("<I", data[2:6])[0]
        return cls(size=size, opcode=opcode), CLIENT_HEADER_SIZE


def parse_server_header(data: bytes) -> Optional[Tuple[int, int, int]]:
    """Parse a server header.

    Returns ``(header_length, size, opcode)`` or ``None`` if incomplete.
    """
    if len(data) == 0:
        return None

    pos = 0
    if data[0] & 0x80:
        if len(data) < 5:
            return None
        size = ((data[0] & 0x7F) << 16) | (data[1] << 8) | data[2]
        pos = 3
    else:
        if len(data) < 4:
            return None
        size = (data[0] << 8) | data[1]
        pos = 2

    opcode = data[pos] | (data[pos + 1] << 8)
    header_len = pos + 2
    return header_len, size, opcode
