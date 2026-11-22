"""Client movement information for WoW 3.3.5a (build 12340).

The client is authoritative about its own position: it predicts movement
locally and streams ``MSG_MOVE_*`` packets (plus periodic ``MSG_MOVE_HEARTBEAT``
packets) to the server, which only has to accept them, keep the last known
position and relay it to other players.  This module implements the wire
format of ``MovementInfo`` exactly as TrinityCore/CMaNGOS 3.3.5 read and write
it:

    uint32 flags
    uint16 flags2
    uint32 time
    float  x, y, z, o
    -- only when flags & MOVEMENTFLAG_ONTRANSPORT --
    packed guid transport guid
    float  transport x, y, z, o
    uint32 transport time
    uint32 transport time2   (only when flags2 & INTERPOLATED_MOVEMENT)
    uint8  transport seat
    uint32 transport time3   (only when flags2 & INTERPOLATED_TURNING)
    -- only when flags & (SWIMMING | FLYING) or flags2 & ALWAYS_ALLOW_PITCHING --
    float  pitch
    uint32 fall time
    -- only when flags & MOVEMENTFLAG_FALLING --
    float  jump z speed, cos angle, sin angle, xy speed

Note that 3.3.5 uses a ``uint16`` for the second movement-flag word; it only
became a ``uint32`` in Cataclysm.  Getting that wrong shifts every following
field by two bytes.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional, Tuple

# --- Movement flags (uint32) ---------------------------------------------
MOVEMENTFLAG_NONE = 0x00000000
MOVEMENTFLAG_FORWARD = 0x00000001
MOVEMENTFLAG_BACKWARD = 0x00000002
MOVEMENTFLAG_STRAFE_LEFT = 0x00000004
MOVEMENTFLAG_STRAFE_RIGHT = 0x00000008
MOVEMENTFLAG_TURN_LEFT = 0x00000010
MOVEMENTFLAG_TURN_RIGHT = 0x00000020
MOVEMENTFLAG_PITCH_UP = 0x00000040
MOVEMENTFLAG_PITCH_DOWN = 0x00000080
MOVEMENTFLAG_WALKING = 0x00000100
MOVEMENTFLAG_ONTRANSPORT = 0x00000200
MOVEMENTFLAG_DISABLE_GRAVITY = 0x00000400
MOVEMENTFLAG_ROOT = 0x00000800
MOVEMENTFLAG_FALLING = 0x00001000
MOVEMENTFLAG_FALLING_FAR = 0x00002000
MOVEMENTFLAG_PENDING_STOP = 0x00004000
MOVEMENTFLAG_PENDING_STRAFE_STOP = 0x00008000
MOVEMENTFLAG_PENDING_FORWARD = 0x00010000
MOVEMENTFLAG_PENDING_BACKWARD = 0x00020000
MOVEMENTFLAG_PENDING_STRAFE_LEFT = 0x00040000
MOVEMENTFLAG_PENDING_STRAFE_RIGHT = 0x00080000
MOVEMENTFLAG_PENDING_ROOT = 0x00100000
MOVEMENTFLAG_SWIMMING = 0x00200000
MOVEMENTFLAG_ASCENDING = 0x00400000
MOVEMENTFLAG_DESCENDING = 0x00800000
MOVEMENTFLAG_CAN_FLY = 0x01000000
MOVEMENTFLAG_FLYING = 0x02000000
MOVEMENTFLAG_SPLINE_ELEVATION = 0x04000000
MOVEMENTFLAG_SPLINE_ENABLED = 0x08000000
MOVEMENTFLAG_WATERWALKING = 0x10000000
MOVEMENTFLAG_SAFE_FALL = 0x20000000
MOVEMENTFLAG_HOVER = 0x40000000
MOVEMENTFLAG_STATUS_APPLIED = 0x80000000

MOVEMENTFLAG_MASK_MOVING = (
    MOVEMENTFLAG_FORWARD | MOVEMENTFLAG_BACKWARD
    | MOVEMENTFLAG_STRAFE_LEFT | MOVEMENTFLAG_STRAFE_RIGHT
)
MOVEMENTFLAG_MASK_TURNING = MOVEMENTFLAG_TURN_LEFT | MOVEMENTFLAG_TURN_RIGHT
MOVEMENTFLAG_MASK_MOVING_OR_TURNING = MOVEMENTFLAG_MASK_MOVING | MOVEMENTFLAG_MASK_TURNING

# --- Movement flags 2 (uint16 on the wire in 3.3.5) ----------------------
MOVEMENTFLAG2_NONE = 0x0000
MOVEMENTFLAG2_NO_STRAFE = 0x0001
MOVEMENTFLAG2_NO_JUMPING = 0x0002
MOVEMENTFLAG2_DISABLE_GRAVITY = 0x0004
MOVEMENTFLAG2_FULL_SPEED_TURNING = 0x0008
MOVEMENTFLAG2_FULL_SPEED_PITCHING = 0x0010
MOVEMENTFLAG2_ALWAYS_ALLOW_PITCHING = 0x0020
MOVEMENTFLAG2_VEHICLE_EXIT_VOLUNTARY = 0x0040
MOVEMENTFLAG2_JUMP_SPLINE_IN_AIR = 0x0080
MOVEMENTFLAG2_ANIM_TIER_IN_TRANS = 0x0100
MOVEMENTFLAG2_UNK_0200 = 0x0200
MOVEMENTFLAG2_INTERPOLATED_MOVEMENT = 0x0400
MOVEMENTFLAG2_INTERPOLATED_TURNING = 0x0800
MOVEMENTFLAG2_INTERPOLATED_PITCHING = 0x1000
MOVEMENTFLAG2_UNK_2000 = 0x2000
MOVEMENTFLAG2_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY = 0x4000
MOVEMENTFLAG2_UNK_8000 = 0x8000

_FLAG_NAMES = {
    MOVEMENTFLAG_FORWARD: "FORWARD",
    MOVEMENTFLAG_BACKWARD: "BACKWARD",
    MOVEMENTFLAG_STRAFE_LEFT: "STRAFE_LEFT",
    MOVEMENTFLAG_STRAFE_RIGHT: "STRAFE_RIGHT",
    MOVEMENTFLAG_TURN_LEFT: "TURN_LEFT",
    MOVEMENTFLAG_TURN_RIGHT: "TURN_RIGHT",
    MOVEMENTFLAG_PITCH_UP: "PITCH_UP",
    MOVEMENTFLAG_PITCH_DOWN: "PITCH_DOWN",
    MOVEMENTFLAG_WALKING: "WALKING",
    MOVEMENTFLAG_ONTRANSPORT: "ONTRANSPORT",
    MOVEMENTFLAG_DISABLE_GRAVITY: "DISABLE_GRAVITY",
    MOVEMENTFLAG_ROOT: "ROOT",
    MOVEMENTFLAG_FALLING: "FALLING",
    MOVEMENTFLAG_FALLING_FAR: "FALLING_FAR",
    MOVEMENTFLAG_PENDING_STOP: "PENDING_STOP",
    MOVEMENTFLAG_PENDING_STRAFE_STOP: "PENDING_STRAFE_STOP",
    MOVEMENTFLAG_PENDING_FORWARD: "PENDING_FORWARD",
    MOVEMENTFLAG_PENDING_BACKWARD: "PENDING_BACKWARD",
    MOVEMENTFLAG_PENDING_STRAFE_LEFT: "PENDING_STRAFE_LEFT",
    MOVEMENTFLAG_PENDING_STRAFE_RIGHT: "PENDING_STRAFE_RIGHT",
    MOVEMENTFLAG_PENDING_ROOT: "PENDING_ROOT",
    MOVEMENTFLAG_SWIMMING: "SWIMMING",
    MOVEMENTFLAG_ASCENDING: "ASCENDING",
    MOVEMENTFLAG_DESCENDING: "DESCENDING",
    MOVEMENTFLAG_CAN_FLY: "CAN_FLY",
    MOVEMENTFLAG_FLYING: "FLYING",
    MOVEMENTFLAG_SPLINE_ELEVATION: "SPLINE_ELEVATION",
    MOVEMENTFLAG_SPLINE_ENABLED: "SPLINE_ENABLED",
    MOVEMENTFLAG_WATERWALKING: "WATERWALKING",
    MOVEMENTFLAG_SAFE_FALL: "SAFE_FALL",
    MOVEMENTFLAG_HOVER: "HOVER",
    MOVEMENTFLAG_STATUS_APPLIED: "STATUS_APPLIED",
}

_FLAG2_NAMES = {
    MOVEMENTFLAG2_NO_STRAFE: "NO_STRAFE",
    MOVEMENTFLAG2_NO_JUMPING: "NO_JUMPING",
    MOVEMENTFLAG2_DISABLE_GRAVITY: "DISABLE_GRAVITY",
    MOVEMENTFLAG2_FULL_SPEED_TURNING: "FULL_SPEED_TURNING",
    MOVEMENTFLAG2_FULL_SPEED_PITCHING: "FULL_SPEED_PITCHING",
    MOVEMENTFLAG2_ALWAYS_ALLOW_PITCHING: "ALWAYS_ALLOW_PITCHING",
    MOVEMENTFLAG2_VEHICLE_EXIT_VOLUNTARY: "VEHICLE_EXIT_VOLUNTARY",
    MOVEMENTFLAG2_JUMP_SPLINE_IN_AIR: "JUMP_SPLINE_IN_AIR",
    MOVEMENTFLAG2_ANIM_TIER_IN_TRANS: "ANIM_TIER_IN_TRANS",
    MOVEMENTFLAG2_UNK_0200: "UNK_0200",
    MOVEMENTFLAG2_INTERPOLATED_MOVEMENT: "INTERPOLATED_MOVEMENT",
    MOVEMENTFLAG2_INTERPOLATED_TURNING: "INTERPOLATED_TURNING",
    MOVEMENTFLAG2_INTERPOLATED_PITCHING: "INTERPOLATED_PITCHING",
    MOVEMENTFLAG2_UNK_2000: "UNK_2000",
    MOVEMENTFLAG2_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY: "CAN_TRANSITION_BETWEEN_SWIM_AND_FLY",
    MOVEMENTFLAG2_UNK_8000: "UNK_8000",
}

_KNOWN_FLAGS = 0
for _flag in _FLAG_NAMES:
    _KNOWN_FLAGS |= _flag
_KNOWN_FLAGS2 = 0
for _flag in _FLAG2_NAMES:
    _KNOWN_FLAGS2 |= _flag

# TrinityCore ``IsValidMapCoord``: anything outside these bounds is rejected
# instead of being written to the character row.
MAX_COORD_X = 17066.0
MAX_COORD_Y = 17066.0
MIN_COORD_Z = -500.0
MAX_COORD_Z = 10000.0


class MovementParseError(ValueError):
    """Raised when a movement packet is truncated or otherwise malformed."""


@dataclass
class MovementInfo:
    flags: int = 0
    flags2: int = 0
    time: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    o: float = 0.0

    # present only with MOVEMENTFLAG_ONTRANSPORT
    transport_guid: int = 0
    transport_x: float = 0.0
    transport_y: float = 0.0
    transport_z: float = 0.0
    transport_o: float = 0.0
    transport_time: int = 0
    transport_time2: int = 0
    transport_seat: int = 0
    transport_time3: int = 0
    pitch: Optional[float] = None

    fall_time: int = 0

    # present only with MOVEMENTFLAG_FALLING
    jump_zspeed: float = 0.0
    jump_cos_angle: float = 0.0
    jump_sin_angle: float = 0.0
    jump_xyspeed: float = 0.0

    # bookkeeping (never serialized)
    parsed_bytes: int = field(default=0, compare=False)

    # -- convenience ---------------------------------------------------
    def has_flag(self, flag: int) -> bool:
        return (self.flags & flag) != 0

    def is_moving(self) -> bool:
        return (self.flags & MOVEMENTFLAG_MASK_MOVING) != 0

    def is_turning(self) -> bool:
        return (self.flags & MOVEMENTFLAG_MASK_TURNING) != 0

    def is_valid(self) -> bool:
        if not (-MAX_COORD_X <= self.x <= MAX_COORD_X):
            return False
        if not (-MAX_COORD_Y <= self.y <= MAX_COORD_Y):
            return False
        if not (MIN_COORD_Z <= self.z <= MAX_COORD_Z):
            return False
        return True

    def position(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.z, self.o)

    def describe(self) -> str:
        names = [name for flag, name in _FLAG_NAMES.items() if self.flags & flag]
        names2 = [name for flag, name in _FLAG2_NAMES.items() if self.flags2 & flag]
        if self.flags & ~_KNOWN_FLAGS:
            names.append(f"0x{self.flags & ~_KNOWN_FLAGS:08X}")
        if self.flags2 & ~_KNOWN_FLAGS2:
            names2.append(f"0x{self.flags2 & ~_KNOWN_FLAGS2:04X}")
        return (
            f"flags={'|'.join(names) if names else 'NONE'}"
            + (f" flags2={'|'.join(names2)}" if names2 else "")
            + f" pos=({self.x:.2f}, {self.y:.2f}, {self.z:.2f}) o={self.o:.2f}"
        )


def parse_packed_guid(data: bytes, pos: int = 0) -> Tuple[int, int]:
    """``ObjectGuid::ReadAsPacked``: mask byte, then only the non-zero bytes."""
    if pos >= len(data):
        raise MovementParseError("truncated packed guid")
    mask = data[pos]
    pos += 1
    guid = 0
    for index in range(8):
        if mask & (1 << index):
            if pos >= len(data):
                raise MovementParseError("truncated packed guid body")
            guid |= data[pos] << (8 * index)
            pos += 1
    return guid, pos


def pack_guid(guid: int) -> bytes:
    """``ObjectGuid::WriteAsPacked``: mask byte + the non-zero bytes."""
    mask = 0
    body = bytearray()
    for index in range(8):
        byte = (guid >> (8 * index)) & 0xFF
        if byte:
            mask |= 1 << index
            body.append(byte)
    return bytes([mask]) + bytes(body)


def parse_movement_info(data: bytes, pos: int = 0) -> Tuple[MovementInfo, int]:
    """Read one ``MovementInfo`` starting at ``pos`` and return ``(info, end)``."""
    start = pos

    def take(fmt: str):
        nonlocal pos
        size = struct.calcsize(fmt)
        if pos + size > len(data):
            raise MovementParseError(
                f"truncated movement info at offset {pos} (need {size} bytes, "
                f"have {len(data) - pos})"
            )
        values = struct.unpack_from(fmt, data, pos)
        pos += size
        return values

    info = MovementInfo()
    info.flags, info.flags2, info.time = take("<IHI")
    info.x, info.y, info.z, info.o = take("<ffff")

    if info.flags & MOVEMENTFLAG_ONTRANSPORT:
        info.transport_guid, pos = parse_packed_guid(data, pos)
        (info.transport_x, info.transport_y,
         info.transport_z, info.transport_o) = take("<ffff")
        (info.transport_time,) = take("<I")
        if info.flags2 & MOVEMENTFLAG2_INTERPOLATED_MOVEMENT:
            (info.transport_time2,) = take("<I")
        (info.transport_seat,) = take("<B")
        if info.flags2 & MOVEMENTFLAG2_INTERPOLATED_TURNING:
            (info.transport_time3,) = take("<I")

    if (info.flags & (MOVEMENTFLAG_SWIMMING | MOVEMENTFLAG_FLYING)) or (
        info.flags2 & MOVEMENTFLAG2_ALWAYS_ALLOW_PITCHING
    ):
        (info.pitch,) = take("<f")

    (info.fall_time,) = take("<I")

    if info.flags & MOVEMENTFLAG_FALLING:
        (info.jump_zspeed, info.jump_cos_angle,
         info.jump_sin_angle, info.jump_xyspeed) = take("<ffff")

    info.parsed_bytes = pos - start
    return info, pos


def build_movement_info(info: MovementInfo) -> bytes:
    """Serialize ``info`` using the 3.3.5 layout."""
    out = bytearray()
    out += struct.pack("<IHIffff", info.flags, info.flags2, info.time,
                       info.x, info.y, info.z, info.o)

    if info.flags & MOVEMENTFLAG_ONTRANSPORT:
        out += pack_guid(info.transport_guid)
        out += struct.pack("<ffff", info.transport_x, info.transport_y,
                           info.transport_z, info.transport_o)
        out += struct.pack("<I", info.transport_time)
        if info.flags2 & MOVEMENTFLAG2_INTERPOLATED_MOVEMENT:
            out += struct.pack("<I", info.transport_time2)
        out += struct.pack("<B", info.transport_seat & 0xFF)
        if info.flags2 & MOVEMENTFLAG2_INTERPOLATED_TURNING:
            out += struct.pack("<I", info.transport_time3)

    if (info.flags & (MOVEMENTFLAG_SWIMMING | MOVEMENTFLAG_FLYING)) or (
        info.flags2 & MOVEMENTFLAG2_ALWAYS_ALLOW_PITCHING
    ):
        out += struct.pack("<f", info.pitch or 0.0)

    out += struct.pack("<I", info.fall_time)

    if info.flags & MOVEMENTFLAG_FALLING:
        out += struct.pack("<ffff", info.jump_zspeed, info.jump_cos_angle,
                           info.jump_sin_angle, info.jump_xyspeed)

    return bytes(out)


def parse_movement_packet(data: bytes) -> Tuple[int, MovementInfo]:
    """Parse a ``MSG_MOVE_*`` payload: packed guid followed by movement info."""
    guid, pos = parse_packed_guid(data, 0)
    info, _ = parse_movement_info(data, pos)
    return guid, info


def parse_movement_packet_leniently(data: bytes) -> Tuple[Optional[int], Optional[MovementInfo], str]:
    """Best-effort parse used by the world handler.

    Different ``MSG_MOVE_*``/``CMSG_MOVE_*`` opcodes are shaped differently
    (some carry a guid, some do not, some append acknowledgement data), so try
    the common shapes and report which one matched instead of rejecting the
    packet outright.  Returns ``(guid, info, shape)``.
    """
    try:
        guid, info = parse_movement_packet(data)
        return guid, info, "guid+movement"
    except MovementParseError:
        pass

    try:
        info, _ = parse_movement_info(data, 0)
        return None, info, "movement"
    except MovementParseError as exc:
        return None, None, str(exc)


def build_movement_packet(guid: int, info: MovementInfo) -> bytes:
    """Payload for a relayed ``MSG_MOVE_*`` packet."""
    return pack_guid(guid) + build_movement_info(info)


def build_client_control_update(guid: int, allow_move: bool) -> bytes:
    """``SMSG_CLIENT_CONTROL_UPDATE``: packed guid + uint8 allow-move."""
    return pack_guid(guid) + bytes([1 if allow_move else 0])
