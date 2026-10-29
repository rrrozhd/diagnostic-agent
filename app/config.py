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

# Models (OpenRouter id uses a dot: anthropic/claude-sonnet-5.5). Never set temperature/top_p:
# Sonnet 5.5 rejects them. Structured output must use method="json_schema" (no forced tool_choice).
MODEL = os.environ.get("MODEL", "anthropic/claude-sonnet-5.5")
MODEL_TIMEOUT_MS = int(os.environ.get("MODEL_TIMEOUT_MS", "300000"))  # ChatOpenRouter timeout is in ms
MODEL_MAX_TOKENS = int(os.environ.get("MODEL_MAX_TOKENS", "16000"))
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")

# Guardrail: Jev noul probabilities; a question fails when P(yes) crosses its threshold.
GUARDRAIL_FILE = PACK_DIR / "guardrail.yaml"
REFUSAL_FILE = PACK_DIR / "refusal.md"
BANNED_PHRASES_FILE = PACK_DIR / "banned_phrases.txt"

# External sources (free tiers; E-utilities allows ~3 req/s without an API key).
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
HTTP_TIMEOUT_S = 20.0
PUBMED_MAX_RESULTS = 8
ABSTRACT_MAX_CHARS = 3000
