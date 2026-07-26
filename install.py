"""Forge Neo extension installer.

The MVP intentionally has no third-party dependencies beyond packages bundled
with Forge Neo.
"""

from __future__ import annotations

import importlib.util


required = ("gradio", "PIL", "requests")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(f"[AI WDYWFM] Missing Forge runtime packages: {', '.join(missing)}")
else:
    print("[AI WDYWFM] Runtime dependencies are available.")
