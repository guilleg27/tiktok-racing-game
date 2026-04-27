"""Compatibility shim — re-exports effective config for src/ consumers.

TECH DEBT (M6): Removed when game_engine.py splits and each variant has its
own main.py that loads its config explicitly.
"""

from core.config import *          # noqa: F401, F403
from variants.motos.config import *  # noqa: F401, F403
