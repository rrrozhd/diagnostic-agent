import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = os.environ.get("PACK", "default")
PACK_DIR = ROOT / "packs" / PACK

# Read-only SQL tool over the reference datasets (data/seed.py builds the file).
REFERENCE_DB = ROOT / "data" / "reference.db"
SQL_MAX_ROWS = 50
SQL_TIMEOUT_S = 5.0
SQL_MAX_VALUE_BYTES = 100_000
SQL_MAX_OUTPUT_CHARS = 20_000  # keeps one tool result from flooding the model context
