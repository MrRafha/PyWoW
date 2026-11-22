"""RC4 header encryption used by the WoW 3.3.5a world protocol.

Only packet headers are encrypted.  Both directions use
``HMAC-SHA1(key, session_key)`` as the RC4 key and then drop the first 1024
bytes of keystream (ARC4-drop1024), exactly like TrinityCore's
``WorldPacketCrypt``.
"""
from __future__ import annotations

import hashlib
import hmac

SERVER_ENCRYPT_KEY = bytes.fromhex("CC98AE04E897EACA12DDC09342915357")
SERVER_DECRYPT_KEY = bytes.fromhex("C2B3723CC6AED9B5343C53EE2F4367CE")

_ARC4_DROP = 1024


class ARC4:
    """Small pure-Python RC4 stream cipher."""

    def __init__(self, key: bytes):
        if not key:
            raise ValueError("RC4 key must not be empty")
        state = list(range(256))
        j = 0
        for i in range(256):
            j = (j + state[i] + key[i % len(key)]) & 0xFF
            state[i], state[j] = state[j], state[i]
        self._state = state
        self._i = 0
        self._j = 0

    def process(self, data: bytes) -> bytes:
        state = self._state
        i = self._i
        j = self._j
        out = bytearray(len(data))
        for pos, byte in enumerate(data):
            i = (i + 1) & 0xFF
            j = (j + state[i]) & 0xFF
            state[i], state[j] = state[j], state[i]
            out[pos] = byte ^ state[(state[i] + state[j]) & 0xFF]
        self._i = i
        self._j = j
        return bytes(out)

    def drop(self, count: int) -> None:
        self.process(b"\x00" * count)


class WorldCrypt:
    """Header crypt for one side of a world connection.

    ``client_side=False`` is the server (what realmsocket.py uses).
    ``client_side=True`` is the game client (used by the protocol self-test).
    """

    def __init__(self, session_key: bytes, client_side: bool = False):
        if len(session_key) != 40:
            raise ValueError("session key must be 40 bytes")

        if client_side:
            send_key = SERVER_DECRYPT_KEY
            recv_key = SERVER_ENCRYPT_KEY
        else:
            send_key = SERVER_ENCRYPT_KEY
            recv_key = SERVER_DECRYPT_KEY

        self._encrypt = ARC4(hmac.new(send_key, session_key, hashlib.sha1).digest())
        self._decrypt = ARC4(hmac.new(recv_key, session_key, hashlib.sha1).digest())

        self._encrypt.drop(_ARC4_DROP)
        self._decrypt.drop(_ARC4_DROP)

    def encrypt(self, data: bytes) -> bytes:
        return self._encrypt.process(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._decrypt.process(data)
