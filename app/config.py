import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = os.environ.get("PACK", "default")
PACK_DIR = ROOT / "packs" / PACK
