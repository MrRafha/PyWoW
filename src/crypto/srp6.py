"""SRP6 implementation compatible with World of Warcraft 3.3.5a (build 12340).

The algorithm mirrors TrinityCore's ``SRP6.cpp``:

    x = H(s || H(USERNAME || ":" || PASSWORD))
    v = g^x mod N
    B = 3v + g^b mod N
    u = H(A || B)
    S = (A * v^u)^b mod N
    K = SHA1Interleave(S)                (40 bytes)
    M1 = H(H(N) xor H(g) || H(I) || s || A || B || K)
    M2 = H(A || M1 || K)

All big numbers that go on the wire are 32-byte little-endian values.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Tuple


class SRP6:
    # 894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7
    N_HEX = "894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7"
    N = int(N_HEX, 16)
    g = 7
    k = 3  # B = k*v + g^b  (Trinity writes this as v * 3)

    SALT_LENGTH = 32
    VERIFIER_LENGTH = 32
    EPHEMERAL_KEY_LENGTH = 32
    SESSION_KEY_LENGTH = 40

    N_BYTES = N.to_bytes(EPHEMERAL_KEY_LENGTH, "little")
    G_BYTES = bytes([g])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def to_le32(value: int) -> bytes:
        """Encode a big number as a fixed 32-byte little-endian value."""
        return value.to_bytes(SRP6.EPHEMERAL_KEY_LENGTH, "little")

    @staticmethod
    def from_le(value: bytes) -> int:
        return int.from_bytes(value, "little")

    @staticmethod
    def h(*parts: bytes) -> bytes:
        sha = hashlib.sha1()
        for part in parts:
            sha.update(part)
        return sha.digest()

    @staticmethod
    def _normalize_credentials(username: str, password: str) -> Tuple[str, str]:
        # WoW uppercases both account name and password before SRP6.
        return username.upper(), password.upper()

    # ------------------------------------------------------------------
    # Registration data (salt + verifier) and the client's secret
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_x(username: str, password: str, salt: bytes) -> int:
        username, password = SRP6._normalize_credentials(username, password)
        inner = SRP6.h((username + ":" + password).encode("utf-8"))
        return int.from_bytes(SRP6.h(salt, inner), "little")

    @staticmethod
    def calculate_verifier(username: str, password: str, salt: bytes) -> bytes:
        x = SRP6.calculate_x(username, password, salt)
        verifier = pow(SRP6.g, x, SRP6.N)
        return verifier.to_bytes(SRP6.VERIFIER_LENGTH, "little")

    @staticmethod
    def make_registration_data(username: str, password: str) -> Tuple[bytes, bytes]:
        """Return ``(salt, verifier)`` suitable for storing in the account table."""
        salt = os.urandom(SRP6.SALT_LENGTH)
        return salt, SRP6.calculate_verifier(username, password, salt)

    # Backwards-compatible alias used by tools/create_test_account.py
    generate_verifier_from_password = make_registration_data

    @staticmethod
    def generate_salt() -> bytes:
        return os.urandom(SRP6.SALT_LENGTH)

    # ------------------------------------------------------------------
    # Server side
    # ------------------------------------------------------------------
    @staticmethod
    def generate_challenge(verifier: bytes | int) -> Tuple[int, bytes]:
        """Return ``(b, B)`` where ``B = 3v + g^b mod N``."""
        v = verifier if isinstance(verifier, int) else SRP6.from_le(verifier)
        b = int.from_bytes(os.urandom(32), "little") % SRP6.N
        if b == 0:
            b = 1
        B = (pow(SRP6.g, b, SRP6.N) + SRP6.k * v) % SRP6.N
        return b, B.to_bytes(SRP6.EPHEMERAL_KEY_LENGTH, "little")

    @staticmethod
    def sha1_interleave(s_bytes: bytes) -> bytes:
        """Convert the shared secret ``S`` into the 40-byte WoW session key."""
        if len(s_bytes) != SRP6.EPHEMERAL_KEY_LENGTH:
            raise ValueError("S must be 32 bytes")

        even = s_bytes[0::2]
        odd = s_bytes[1::2]

        # Trinity skips leading zero bytes in S (rounded up to a pair) so that
        # the client and server hash the same parts of the buffers.
        first_nonzero = 0
        while first_nonzero < SRP6.EPHEMERAL_KEY_LENGTH and s_bytes[first_nonzero] == 0:
            first_nonzero += 1
        if first_nonzero & 1:
            first_nonzero += 1
        offset = first_nonzero // 2

        hash0 = SRP6.h(even[offset:])
        hash1 = SRP6.h(odd[offset:])

        key = bytearray(SRP6.SESSION_KEY_LENGTH)
        for i in range(20):
            key[2 * i] = hash0[i]
            key[2 * i + 1] = hash1[i]
        return bytes(key)

    @staticmethod
    def verify_proof(
        username: str,
        a_bytes: bytes,
        b_bytes: bytes,
        b: int,
        verifier: bytes | int,
        salt: bytes,
        client_m1: bytes,
    ) -> Tuple[bool, bytes, bytes]:
        """Verify the client proof.

        Returns ``(ok, M2, session_key)``. ``M2`` and ``session_key`` are empty
        on failure.
        """
        if len(a_bytes) != 32 or len(b_bytes) != 32 or len(salt) != 32:
            return False, b"", b""

        a_int = SRP6.from_le(a_bytes)
        if a_int == 0 or a_int % SRP6.N == 0:
            return False, b"", b""

        v_int = verifier if isinstance(verifier, int) else SRP6.from_le(verifier)
        u = SRP6.from_le(SRP6.h(a_bytes, b_bytes))
        if u == 0:
            return False, b"", b""

        # S = (A * v^u)^b mod N
        s_int = pow((a_int * pow(v_int, u, SRP6.N)) % SRP6.N, b, SRP6.N)
        s_bytes = s_int.to_bytes(SRP6.EPHEMERAL_KEY_LENGTH, "little")
        session_key = SRP6.sha1_interleave(s_bytes)

        # M1 = H(H(N) xor H(g) || H(I) || s || A || B || K)
        n_hash = SRP6.h(SRP6.N_BYTES)
        g_hash = SRP6.h(SRP6.G_BYTES)
        ng_hash = bytes(x ^ y for x, y in zip(n_hash, g_hash))
        i_hash = SRP6.h(username.upper().encode("utf-8"))

        expected_m1 = SRP6.h(
            ng_hash,
            i_hash,
            salt,
            a_bytes,
            b_bytes,
            session_key,
        )
        if not hmac.compare_digest(expected_m1, client_m1):
            return False, b"", b""

        # M2 = H(A || M1 || K)
        m2 = SRP6.h(a_bytes, client_m1, session_key)
        return True, m2, session_key
