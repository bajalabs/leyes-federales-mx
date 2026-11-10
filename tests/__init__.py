"""Tests run with `python3 -m unittest` from the repository root (stdlib only)."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
