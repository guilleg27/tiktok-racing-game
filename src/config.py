"""Compatibility shim — re-exports effective config for src/ consumers.

TECH DEBT (M5): This file differs between main and main-motos branches (one
imports core only, the other imports core + variants.motos). This contradicts
the goal of identical src/ across variants. The shim is a bridge: removed in
M5 when game_engine.py splits and each variant has its own main.py that loads
its config explicitly.
"""

from core.config import *          # noqa: F401, F403
from variants.motos.config import *  # noqa: F401, F403
