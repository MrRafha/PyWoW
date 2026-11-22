"""Simple logger setup."""
from __future__ import annotations

import logging
import os
from datetime import datetime


def setup_logger(name: str, log_dir: str = "./logs", level: str = "INFO", console: bool = True) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(os.path.join(log_dir, f"manawow_{datetime.now().strftime('%Y%m%d')}.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger
