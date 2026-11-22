#!/usr/bin/env python3
"""Start the authserver and worldserver together in one terminal.

Equivalent to running ``run_auth.py`` and ``run_world.py`` in two separate
windows. Press Ctrl+C to stop both.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.common.config import Config
from src.common.utils import ensure_dirs, pause_if_interactive
from src.auth.server import AuthServer
from src.world.server import WorldServer


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "config", "config.yaml")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(os.path.dirname(__file__), "config", "config.example.yaml")
        print(f"config.yaml not found; using {cfg_path}")
    cfg = Config.load(cfg_path)
    ensure_dirs(
        os.path.dirname(cfg.database.auth_path),
        os.path.dirname(cfg.database.world_path),
        cfg.logging.log_dir,
    )
    auth = AuthServer(cfg)
    world = WorldServer(cfg)
    await asyncio.gather(auth.start(), world.start())
    # Keep the event loop running
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit:
        pause_if_interactive()
        raise
    except KeyboardInterrupt:
        pass
