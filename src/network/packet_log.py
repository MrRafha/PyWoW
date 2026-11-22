"""Packet logging for debugging"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from enum import IntEnum
from typing import Optional

from src.protocol.opcodes import Opcodes


class Direction(IntEnum):
    CLIENT_TO_SERVER = 0
    SERVER_TO_CLIENT = 1


class PacketLog:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._file = None
        self.path = None
        self._log_lock = threading.Lock()
        self._initialize_flag = threading.Event()

    def Initialize(self, log_dir: str = "./logs"):
        """Open the session's packet log once.

        ``run_servers.py`` constructs the auth server and the world server in
        one process and both call this, so a second call must be a no-op.  It
        used to open a second file, which left the first one empty (the file
        the *other* server had been writing to) and made a crashed client
        session impossible to diagnose.  The timestamp carries microseconds so
        two servers started inside the same second cannot collide on a name and
        truncate each other.
        """
        with self._log_lock:
            if self._file is not None:
                return
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filepath = os.path.join(log_dir, f"packets_{timestamp}.log")
            try:
                self._file = open(filepath, "w", encoding="utf-8")
                self.path = filepath
                self._initialize_flag.set()
            except Exception as e:
                print(f"Failed to initialize packet log: {e}")

    def CanLogPacket(self) -> bool:
        return self._file is not None

    def LogPacket(self, packet_data: bytes, opcode: int, direction: Direction, addr: str = "127.0.0.1", port: int = 0):
        if not self.CanLogPacket():
            return
        with self._log_lock:
            try:
                opcode_name = self._get_opcode_name(opcode)
                dir_str = "C->S" if direction == Direction.CLIENT_TO_SERVER else "S->C"
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self._file.write(f"[{timestamp}] {dir_str} {addr}:{port} {opcode_name} (0x{opcode:04X}) [{len(packet_data)} bytes]\n")
                if packet_data:
                    hex_str = ' '.join(f'{b:02X}' for b in packet_data)
                    self._file.write(f"  {hex_str}\n")
                self._file.write("\n")
                self._file.flush()
            except Exception:
                pass

    def _get_opcode_name(self, opcode: int) -> str:
        try:
            return Opcodes(opcode).name
        except ValueError:
            return "UNKNOWN"


def get_packet_log() -> PacketLog:
    return PacketLog()


# Convenience alias
sPacketLog = get_packet_log()
