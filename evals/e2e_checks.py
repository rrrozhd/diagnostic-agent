"""Pure checks for the end-to-end run (docs/plans/e2e-mvp.md, acceptance 3-7).

Each check returns a list of problem strings; an empty list means the check passed. A resolver
is any callable Source dict -> bool; `make_resolver` builds the cached, throttled one a run uses.
"""

import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx

from app.config import (
    BANNED_PHRASES_FILE,
    EUTILS_BASE,
    NCBI_API_KEY,
    OPENFDA_LABEL_URL,
    REFERENCE_DB,
)

_PMID = re.compile(r"\d{1,9}")
_SET_ID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_EUTILS_INTERVAL_S = (
    0.12 if NCBI_API_KEY else 0.35
)  # E-utilities: 10 req/s with a key, 3 without


def _get(http: httpx.Client, url: str, params: dict) -> httpx.Response:
    r = http.get(url, params=params)
    if r.status_code == 429 or r.status_code >= 500:
        time.sleep(1.0)
        r = http.get(url, params=params)
    return r


def _row_exists(ref: str, db: Path) -> bool:
    left, sep, value = ref.partition("=")
    table, dot, column = left.partition(".")
    if not (sep and dot and value) or not db.exists():
        return False
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tables = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if table not in tables:
            return False
        if column not in {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}:
            return False
        # Identifiers are allow-listed above; only the value is model-written and it is bound.
        return (
            con.execute(
                f'SELECT 1 FROM "{table}" WHERE "{column}" = ? LIMIT 1', (value,)
            ).fetchone()
            is not None
        )
    finally:
        con.close()


def resolve_source(source: dict, http: httpx.Client, db: Path = REFERENCE_DB) -> bool:
    """True when the source's id names a real record. Raises httpx.HTTPError if an API is unreachable."""
    kind, sid = source.get("kind"), str(source.get("id", "")).strip()
    if kind == "pubmed":
        if not _PMID.fullmatch(sid):
            return False
        params = {"db": "pubmed", "id": sid, "retmode": "json"} | (
            {"api_key": NCBI_API_KEY} if NCBI_API_KEY else {}
        )
        r = _get(http, f"{EUTILS_BASE}/esummary.fcgi", params)
        r.raise_for_status()
        result = r.json().get("result", {})
        return sid in result.get("uids", []) and "error" not in result.get(
            sid, {"error": "missing"}
        )
    if kind == "drug_label":
        if not _SET_ID.fullmatch(sid):
            return False
        r = _get(http, OPENFDA_LABEL_URL, {"search": f'set_id:"{sid}"', "limit": 1})
        if r.status_code == 404:  # openFDA answers "no matches" with 404
            return False
        r.raise_for_status()
        return r.json().get("meta", {}).get("results", {}).get("total", 0) >= 1
    if kind == "reference_db":
        return _row_exists(sid, db)
    return False


def make_resolver(http: httpx.Client, db: Path = REFERENCE_DB):
    """Cached resolver for one run, and the list it appends API failures to.

    A failed lookup resolves False and is not cached, so a later turn retries it.
    """
    cache: dict[tuple, bool] = {}
    errors: list[str] = []
    last_eutils = [0.0]

    def resolve(source: dict) -> bool:
        key = (source.get("kind"), str(source.get("id", "")).strip())
        if key not in cache:
            if key[0] == "pubmed":
                time.sleep(
                    max(0.0, last_eutils[0] + _EUTILS_INTERVAL_S - time.monotonic())
                )
                last_eutils[0] = time.monotonic()
            try:
                cache[key] = resolve_source(source, http, db)
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"source {key[0]}:{key[1]} not checked: {e}")
                print(errors[-1], file=sys.stderr)
                return False
        return cache[key]

    return resolve, errors


def _resolves(claims: list[dict], resolver) -> bool:
    return any(resolver(s) for c in claims for s in c.get("sources", []))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def check_differential(resp: dict | None, resolver) -> list[str]:
    if not resp:
        return ["no response"]
    if resp.get("kind") != "differential" or not resp.get("differential"):
        return [
            f"kind is {resp.get('kind')!r}, expected 'differential' with a differential"
        ]
    candidates = resp["differential"].get("candidates", [])
    problems = (
        [f"{len(candidates)} candidates, expected >= 3"] if len(candidates) < 3 else []
    )
    for c in candidates:
        name = c.get("name", "?")
        claims = (
            c.get("findings_for", [])
            + c.get("findings_against", [])
            + c.get("discriminating_tests", [])
        )
        if not _resolves(claims, resolver):
            problems.append(f"candidate {name!r}: no source resolves")
        if not c.get("discriminating_tests"):
            problems.append(f"candidate {name!r}: no discriminating test")
    return problems


def check_treatment(
    resp: dict | None, selection: str, allergen_drugs: list[str], resolver
) -> list[str]:
    if not resp:
        return ["no response"]
    if resp.get("kind") != "treatment" or not resp.get("treatment"):
        return [
            f"kind is {resp.get('kind')!r}, expected 'treatment' with a treatment plan"
        ]
    plan = resp["treatment"]
    problems = []
    diagnosis = plan.get("diagnosis", "")
    d, sel = _norm(diagnosis), _norm(selection)
    if not d or (sel not in d and d not in sel):
        problems.append(
            f"treatment diagnosis {diagnosis!r} does not match selection {selection!r}"
        )
    options = plan.get("options", [])
    if len(options) < 2:
        problems.append(f"{len(options)} treatment options, expected >= 2")
    for o in options:
        name = o.get("name", "?")
        if not _resolves(o.get("rationale", []) + o.get("warnings", []), resolver):
            problems.append(f"option {name!r}: no source resolves")
        hits = [d for d in allergen_drugs if d.lower() in name.lower()]
        if hits and not o.get("warnings"):
            problems.append(
                f"option {name!r}: contains allergen drug {hits[0]!r} but has no warning"
            )
    return problems


def load_patterns(path: Path = BANNED_PHRASES_FILE) -> list[str]:
    # Same loader as evals/gate.py.
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def banned_hits(resp: dict | None, patterns: list[str]) -> list[str]:
    """Banned-phrase matches in app-produced text. Skips `sources` (titles, excerpts, urls, ids are quotes)."""
    hits = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k != "sources":
                    walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            for p in patterns:
                if m := re.search(p, node, re.IGNORECASE):
                    hits.append(f"banned phrase {m.group(0)!r} at {path}")

    walk(resp, "")
    return hits


def check_refusal(result: dict, refusal_text: str) -> list[str]:
    problems = []
    if result.get("refused") is not True:
        problems.append("not refused")
    # Outer whitespace is ignored: the file ends with a newline the API may strip.
    if (result.get("refusal") or "").strip() != refusal_text.strip():
        problems.append("refusal text differs from refusal.md")
    if result.get("model_calls") != 0:
        problems.append(f"model_calls is {result.get('model_calls')!r}, expected 0")
    if result.get("response") is not None:
        problems.append("response is not null")
    return problems
