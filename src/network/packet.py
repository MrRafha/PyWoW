"""Basic packet helpers for worldserver (size+opcode framing varies)."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional


@dataclass
class OutPacket:
    opcode: int
    data: bytes = b""

    def build(self) -> bytes:
        # Common style: for some builds size is 2 bytes (incl opcode) big-endian or varies
        # Keep simple; refine per actual 3.3.5a expectations
        size = len(self.data) + 2
        return struct.pack(">H", size) + struct.pack("<H", self.opcode) + self.data


@dataclass
class InPacket:
    opcode: int
    data: bytes
    reader_pos: int = 0

    def read_uint8(self) -> int:
        v = self.data[self.reader_pos]
        self.reader_pos += 1
        return v

    def read_uint16(self, little: bool = True) -> int:
        if little:
            v = struct.unpack("<H", self.data[self.reader_pos : self.reader_pos + 2])[0]
        else:
            v = struct.unpack(">H", self.data[self.reader_pos : self.reader_pos + 2])[0]
        self.reader_pos += 2
        return v

    def read_uint32(self, little: bool = True) -> int:
        if little:
            v = struct.unpack("<I", self.data[self.reader_pos : self.reader_pos + 4])[0]
        else:
            v = struct.unpack(">I", self.data[self.reader_pos : self.reader_pos + 4])[0]
        self.reader_pos += 4
        return v

    def read_cstring(self) -> str:
        end = self.data.find(b"\x00", self.reader_pos)
        if end == -1:
            s = self.data[self.reader_pos :]
            self.reader_pos = len(self.data)
        else:
            s = self.data[self.reader_pos : end]
            self.reader_pos = end + 1
        return s.decode("utf-8", errors="replace")
