"""Tiny logging helper shared across the app."""

import logging
import sys

_CONFIGURED = False


def setup_logger(name: str = "phial", level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(name)
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root = logging.getLogger("phial")
        root.addHandler(handler)
        root.setLevel(level)
        root.propagate = False
        _CONFIGURED = True
    return logger


def get_logger(name: str = "phial") -> logging.Logger:
    return logging.getLogger(name)
