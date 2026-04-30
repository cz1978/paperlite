from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
PAPERLITE_ROOT = ROOT / "paperlite"
if str(PAPERLITE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAPERLITE_ROOT))

from paperlite.api import create_app  # noqa: E402


app = create_app()


__all__ = ["app", "create_app"]
