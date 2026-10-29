"""Drive the running service through evals/e2e_cases.jsonl over HTTP and check every turn.

Writes evals/e2e_runs/<UTC timestamp>/<case id>.json per case, prints a summary, exits 1 on any problem.
Usage: uv run python scripts/e2e.py [--case ID] [--base-url URL]
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent)
)  # repo root, so `app` and `evals` import

import httpx

from app.config import BANNED_PHRASES_FILE, HTTP_TIMEOUT_S, REFUSAL_FILE, ROOT
from evals.e2e_checks import (
    banned_hits,
    check_differential,
    check_refusal,
    check_treatment,
    load_patterns,
    make_resolver,
)

CASES = ROOT / "evals" / "e2e_cases.jsonl"
RUNS = ROOT / "evals" / "e2e_runs"
CHAT_TIMEOUT_S = float(
    os.environ.get("E2E_TIMEOUT_S", "900")
)  # one turn can take minutes
TURN2 = (
    "I'd like to consider {selection}. What are the treatment options for this patient?"
)


def post(
    api: httpx.Client, base_url: str, thread_id: str, message: str
) -> tuple[dict, float, str | None]:
    start = time.monotonic()
    try:
        r = api.post(
            f"{base_url}/api/chat", json={"thread_id": thread_id, "message": message}
        )
        r.raise_for_status()
        return r.json(), time.monotonic() - start, None
    except httpx.HTTPStatusError as e:
        body = {"status_code": e.response.status_code, "body": e.response.text[:4000]}
        return body, time.monotonic() - start, f"HTTP {e.response.status_code}"
    except (httpx.HTTPError, ValueError) as e:
        return {}, time.monotonic() - start, f"request failed: {type(e).__name__}: {e}"


def run_case(
    case: dict, api, base_url: str, resolver, errors: list[str], patterns: list[str]
) -> list[dict]:
    thread_id = str(uuid.uuid4())
    messages = [case["turn1"]]
    if not case.get("expect_refusal"):
        messages.append(TURN2.format(selection=case["selection"]))
    turns = []
    for n, message in enumerate(messages, 1):
        result, elapsed, error = post(api, base_url, thread_id, message)
        resp = result.get("response")
        seen = len(errors)
        if error:
            problems = [error]
        elif case.get("expect_refusal"):
            problems = check_refusal(result, REFUSAL_FILE.read_text())
        else:
            problems = (
                [f"refused: {result.get('refusal')!r}"] if result.get("refused") else []
            )
            if n == 1:
                problems += check_differential(resp, resolver)
            else:
                problems += check_treatment(
                    resp, case["selection"], case.get("allergen_drugs", []), resolver
                )
            problems += banned_hits(resp, patterns)
            # An unreachable source API is a run problem, not proof the id is fake.
            problems += errors[seen:]
        turns.append(
            {
                "turn": n,
                "thread_id": thread_id,
                "message": message,
                "result": result or None,
                "cost_usd": result.get("cost_usd"),
                "model_calls": result.get("model_calls"),
                "trace_id": result.get("trace_id"),
                "elapsed_s": round(elapsed, 1),
                "problems": problems,
            }
        )
        if n == 1 and not (resp or {}).get("differential"):
            break  # turn 2 would only spend paid calls on a thread with no differential
    return turns


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the two-turn e2e cases against the running service."
    )
    ap.add_argument("--case", help="run only this case id")
    ap.add_argument(
        "--base-url", default=os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000")
    )
    args = ap.parse_args()

    cases = [
        json.loads(line) for line in CASES.read_text().splitlines() if line.strip()
    ]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            sys.exit(f"no case {args.case!r} in {CASES}")
    patterns = load_patterns(BANNED_PHRASES_FILE)
    out_dir = RUNS / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True)

    rows, total = [], 0.0
    with (
        httpx.Client(timeout=HTTP_TIMEOUT_S) as http,
        httpx.Client(timeout=CHAT_TIMEOUT_S) as api,
    ):
        resolver, errors = make_resolver(http)
        for case in cases:
            base_url = args.base_url.rstrip("/")
            turns = run_case(case, api, base_url, resolver, errors, patterns)
            cost = sum(t["cost_usd"] or 0.0 for t in turns)
            total += cost
            (out_dir / f"{case['id']}.json").write_text(
                json.dumps(
                    {
                        "case": case,
                        "base_url": args.base_url,
                        "cost_usd": cost,
                        "turns": turns,
                    },
                    indent=2,
                )
            )
            rows += [
                (case["id"], t["turn"], not t["problems"], t["problems"], t["cost_usd"])
                for t in turns
            ]

    print(f"{'case':<22} {'turn':>4} {'ok':<4} {'cost $':>8}  problems")
    for cid, turn, ok, problems, cost in rows:
        print(
            f"{cid:<22} {turn:>4} {'ok' if ok else 'FAIL':<4} {cost or 0:>8.4f}  {'; '.join(problems)}"
        )
    print(f"total cost ${total:.4f}; transcripts in {out_dir}")
    return 0 if all(ok for _, _, ok, _, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
