"""Addon signature exchange for WoW 3.3.5a (build 12340).

Right after ``CMSG_AUTH_SESSION`` the server answers with ``SMSG_ADDON_INFO``.
The two packets are tied together: the client appends a zlib-compressed list
of its *secure* addons (the ``Blizzard_*`` ones, plus any third-party addon
with ``## Secure: 1``) to the auth packet, and expects exactly one answer
record per entry, in the same order:

    -- CMSG_AUTH_SESSION tail --
    uint32 uncompressedSize           (0 when the client has no addons)
    uint8  compressed[...]            (zlib stream of the block below)

    uint32 count
    repeat count times:
        cstring name
        uint8   hasPublicKey
        uint32  publicKeyCrc          (SCrcCompute over the 256-byte key)
        uint32  urlCrc
    uint32 latestBannedAddonTimestamp (0x4B44953B is what 3.3.5 sends)

    -- SMSG_ADDON_INFO --
    repeat count times:
        uint8  state                  (0 banned, 1 normal, 2 Blizzard-signed)
        uint8  hasPublicKey
        if hasPublicKey:
            uint8  hasKeyData
            if hasKeyData:
                uint8 publicKey[256]  (RSA modulus followed by exponent)
            uint32 revision
        uint8  hasUrl
        if hasUrl:
            cstring url
    uint32 bannedCount
    repeat bannedCount times:
        uint32 id
        uint8  nameMd5[16]
        uint8  versionMd5[16]
        uint32 lastModified
        uint32 flags

Getting the count wrong is fatal in a subtle way: the client reads one record
per secure addon regardless, so too few bytes make it read zeroes and mark the
addons as *banned* (``UIADDON::m_status == 2``), which shows a
``Couldn't load <addon>: Banned`` popup that swallows all keyboard input.

``state = 2`` on its own is not enough either.  The client then calls
``FrameXML_CheckSignature(toc, bindings, hasPublicKey ? publicKey : nullptr)``
and only clears the addon's untrusted flag when the reply also supplies the
Blizzard public key (``m_status = 0``).  Untrusted ``Blizzard_*`` addons taint
the whole UI, which is what makes a character refuse to move.
"""
from __future__ import annotations

import struct
import zlib
from typing import List

# ``UIADDON::m_status`` values the client derives from ``state``.
ADDON_STATE_BANNED = 0
ADDON_STATE_NORMAL = 1
ADDON_STATE_BLIZZARD = 2

BLIZZARD_PREFIX = "blizzard_"

# Blizzard's public add-on signing key (256-byte RSA modulus, exponent 65537).
# Every 3.3.5a client ships it as ``Interface\AddOns\Blizzard_<name>\<name>.pub``
# and uses it to verify the ``<addon>.toc.sig`` stored in the MPQs.
BLIZZARD_PUBLIC_KEY = bytes.fromhex(
    "c35b5084b93e32428cd0c748fa0e5d545aa30e14ba9e0db95d8beeb684934575"
    "ff31fe2f643f3d6d07d9449b408559344e10e1e74369ef7c16fcb4ed1b9528a8"
    "2376513157302b790850101c4a1a2cc88b8f052d223ddb5a247a0f1350378f5a"
    "cc9e04440e8701d4a315941634c6c2c3fb49fee1f9da8c503cbe2cbb57ed46b9"
    "ad8bc6df0ed60fbe80b38b1e77cfad22cfb74bcffbf06b11452d7a8118f2927e"
    "98565d5e69720a0d030a85a2859ccbfb566e8f44bb8f0222686397bc85baa8f7"
    "b540683c77866f4bd788ca8ad7ce36f0456ed564790f17fc64dd106ff3f5e0a6"
    "c3fb1b8c29ef8ee534cbd12ace79c39a0d36ea01e0aa912054f072d81ec789d2"
)


class AddonInfoError(ValueError):
    """Raised when the client's addon block cannot be decoded."""


def parse_client_addon_info(data: bytes, pos: int = 0) -> List[str]:
    """Return the secure-addon names appended to ``CMSG_AUTH_SESSION``.

    The block is optional: clients that only run the Blizzard UI still send
    it, but a hand written test client may send nothing at all.
    """
    if pos >= len(data):
        return []

    if pos + 4 > len(data):
        raise AddonInfoError("truncated addon block size")

    uncompressed_size = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    if uncompressed_size == 0:
        return []

    try:
        body = zlib.decompress(data[pos:])
    except zlib.error as exc:
        raise AddonInfoError(f"could not inflate addon block: {exc}") from exc

    if len(body) < 4:
        raise AddonInfoError("addon block has no addon count")

    count = struct.unpack_from("<I", body, 0)[0]
    cursor = 4
    names: List[str] = []
    for _ in range(count):
        end = body.find(b"\x00", cursor)
        if end < 0:
            raise AddonInfoError("truncated addon name")
        names.append(body[cursor:end].decode("utf-8", errors="replace"))
        cursor = end + 1
        # hasPublicKey + publicKeyCrc + urlCrc
        if cursor + 9 > len(body):
            raise AddonInfoError("truncated addon record")
        cursor += 9

    return names


def build_addon_info(names: List[str]) -> bytes:
    """Build ``SMSG_ADDON_INFO`` for the addons ``names``, none banned.

    Blizzard addons get ``state = 2`` *and* a public key.  The key is what makes
    the client trust them: after parsing the reply it calls
    ``FrameXML_CheckSignature`` with the key and, when the ``.toc.sig`` stored in
    the MPQs verifies, sets ``UIADDON::m_status = 0``.  Without the key the
    signature cannot be checked, the addons stay ``m_status = 1`` (untrusted),
    their Lua taints every global it touches, and ``CGGameUI::CanPerformAction``
    starts refusing movement, key bindings and UI clicks - the client looks
    completely dead even though it renders and answers pings.
    """
    out = bytearray()
    for name in names:
        if name.lower().startswith(BLIZZARD_PREFIX):
            out.append(ADDON_STATE_BLIZZARD)
            out.append(1)  # hasPublicKey
            out.append(1)  # hasKeyData - send the modulus, do not rely on .pub
            out += BLIZZARD_PUBLIC_KEY
            out += struct.pack("<I", 0)  # revision
        else:
            out.append(ADDON_STATE_NORMAL)
            out.append(0)  # hasPublicKey
        out.append(0)  # hasUrl

    out += struct.pack("<I", 0)  # bannedAddOnCount
    return bytes(out)
