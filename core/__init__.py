"""
Root core alias forwarding to fileflow.core.
"""

from fileflow.core import *
import fileflow.core as _core
import sys

# Ensure submodule lookups like 'core.scanner' resolve to 'fileflow.core.scanner'
for attr in [
    "models",
    "logger",
    "classifier",
    "safety",
    "rules",
    "scanner",
    "planner",
    "organizer",
    "undo",
]:
    try:
        mod = getattr(_core, attr, None)
        if mod:
            sys.modules[f"core.{attr}"] = mod
    except Exception:
        pass
