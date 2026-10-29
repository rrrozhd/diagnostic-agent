"""Mirror evals/cases.jsonl into a Langfuse dataset: upsert every case, archive items no longer in the file.

One JSON object per line:
  {"id": "dup-charge-1", "input": {...}, "expected": {"category": "duplicate"}, "must_not": ["<regex>"]}
`expected` lists output fields that must match exactly; `must_not` adds regexes to the pack's
banned_phrases.txt for this case only. RAG cases add `"sources": ["<doc id>", ...]` (what retrieval must
find), or `"unanswerable": true` when the documents hold no answer and the app must decline.

Usage: python evals/sync_cases.py <dataset-name>
"""
import json
import sys
from pathlib import Path

from langfuse import get_client

CASES = Path(__file__).with_name("cases.jsonl")


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]


def to_item(case: dict) -> dict:
    return {
        "input": case["input"],
        "expected_output": case.get("expected"),
        "metadata": {
            "case_id": case["id"],
            "must_not": case.get("must_not", []),
            "sources": case.get("sources", []),
            "unanswerable": case.get("unanswerable", False),
        },
    }


def sync(dataset: str) -> None:
    client = get_client()
    client.create_dataset(name=dataset)
    ids = set()
    for case in load_cases():
        item_id = f"{dataset}:{case['id']}"  # item ids are unique per project, not per dataset
        if item_id in ids:
            sys.exit(f"duplicate case id: {case['id']}")
        ids.add(item_id)
        client.create_dataset_item(dataset_name=dataset, id=item_id, status="ACTIVE", **to_item(case))
    for item in client.get_dataset(dataset).items:
        if item.id not in ids:
            client.create_dataset_item(dataset_name=dataset, id=item.id, status="ARCHIVED")
    client.flush()
    print(f"synced {len(ids)} cases to {dataset}")


if __name__ == "__main__":
    sync(sys.argv[1])
