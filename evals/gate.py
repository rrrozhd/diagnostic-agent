"""Eval gate: run the app over the eval cases; fail on any hard-rule hit (including an answered
unanswerable case), or accuracy, retrieval recall or a Jev judge score outside gate.yaml's thresholds.

CI runs it through langfuse/experiment-action against a synced dataset. `make eval` runs it
locally over evals/cases.jsonl. Needs the repo root on PYTHONPATH.
"""
import json
import re
from pathlib import Path

import yaml
from langfuse import Evaluation, RegressionError, RunnerContext, get_client
from sync_cases import load_cases, to_item
from typesafe_sdk import TypeSafeClient

from app.config import PACK_DIR

GATE = yaml.safe_load(Path(__file__).with_name("gate.yaml").read_text())
JUDGE = GATE.get("judge") or {}
BANNED_FILE = PACK_DIR / "banned_phrases.txt"
BANNED = (
    [line.strip() for line in BANNED_FILE.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if BANNED_FILE.exists()
    else []
)


def task(*, item, **kwargs):
    # item is a dict locally (item["input"]) and a Langfuse DatasetItem in CI (item.input).
    raise NotImplementedError("evals/gate.py: run the app graph on the case input and return its output")


def _text(output) -> str:
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)


def _produced(input, output):
    # What the app produced, minus input fields echoed back in its state (the user's own words).
    if isinstance(output, dict) and isinstance(input, dict):
        return {k: v for k, v in output.items() if k not in input}
    return output


def hard_rules(*, input, output, metadata, **kwargs):
    patterns = BANNED + (metadata or {}).get("must_not", [])
    hits = [p for p in patterns if re.search(p, _text(_produced(input, output)), re.IGNORECASE)]
    # Answering when the documents hold no answer is a made-up answer, so it fails like a banned phrase.
    if (metadata or {}).get("unanswerable") and not (isinstance(output, dict) and output.get("declined") is True):
        hits.append("answered an unanswerable case (output.declined is not true)")
    return Evaluation(name="hard_rules", value=0 if hits else 1, comment="; ".join(hits) or None)


def retrieval_recall(*, output, metadata, **kwargs):
    # Share of the case's expected sources among the app's top-k retrieved ids (output["sources"], best first).
    expected = (metadata or {}).get("sources")
    if not expected:
        return []
    if not isinstance(output, dict) or "sources" not in output:
        return Evaluation(name="retrieval_recall", value=0, comment="output has no `sources` list")
    top = output["sources"][: GATE["retrieval"]["k"]]
    missing = [s for s in expected if s not in top]
    return Evaluation(name="retrieval_recall", value=1 - len(missing) / len(expected), comment=", ".join(missing) or None)


def judge(*, input, output, expected_output, **kwargs):
    # TypeSafe Jev answers gate.yaml's typed questions about the case; each answer becomes a score
    # named after its question, with Jev's probabilities in the score metadata.
    if not JUDGE.get("questions"):
        return []
    with TypeSafeClient(model=JUDGE["model"]) as client:
        r = client.system_one(
            state={"input": input, "output": _produced(input, output), "expected": expected_output},
            questions=JUDGE["questions"],
        )
    return (
        [Evaluation(name=n, value=a.noul, metadata={"model": r.model}) for n, a in r.nouls.items()]
        + [
            Evaluation(name=n, value=a.score, metadata={"model": r.model, "confidence": a.confidence, "probabilities": a.probabilities})
            for n, a in r.scores.items()
        ]
        + [
            Evaluation(name=n, value=a.choice, data_type="CATEGORICAL", metadata={"model": r.model, "confidence": a.confidence, "probabilities": a.probabilities})
            for n, a in r.choices.items()
        ]
    )


def accuracy(*, output, expected_output, **kwargs):
    if not expected_output:
        return []
    wrong = [k for k, v in expected_output.items() if not isinstance(output, dict) or output.get(k) != v]
    return Evaluation(name="accuracy", value=0 if wrong else 1, comment=", ".join(wrong) or None)


def hard_failures(*, item_results, **kwargs):
    # Counts items without a passing hard_rules score. Items whose task crashed never reach
    # item_results (the SDK logs and drops them); experiment() adds those.
    failed = sum(
        1 for r in item_results if not any(e.name == "hard_rules" and e.value == 1 for e in r.evaluations)
    )
    return Evaluation(name="hard_failures", value=failed)


def _mean(item_results, name):
    scores = [e.value for r in item_results for e in r.evaluations if e.name == name]
    return Evaluation(name=f"mean_{name}", value=sum(scores) / len(scores)) if scores else []


def mean_accuracy(*, item_results, **kwargs):
    return _mean(item_results, "accuracy")


def mean_retrieval_recall(*, item_results, **kwargs):
    return _mean(item_results, "retrieval_recall")


def judge_means(*, item_results, **kwargs):
    # Mean of each numeric judge score (noul: P(true), score: level); gate.yaml judge.thresholds gate on these.
    values = {}
    for r in item_results:
        for e in r.evaluations:
            if e.name in JUDGE.get("questions", {}) and not isinstance(e.value, str):
                values.setdefault(e.name, []).append(e.value)
    return [Evaluation(name=f"mean_{n}", value=sum(v) / len(v), metadata={"cases": len(v)}) for n, v in values.items()]


def experiment(context: RunnerContext):
    if not context.data:
        raise RuntimeError("no eval cases: add some to evals/cases.jsonl")
    result = context.run_experiment(
        name="eval gate",
        task=task,
        evaluators=[hard_rules, accuracy, retrieval_recall, judge],
        run_evaluators=[hard_failures, mean_accuracy, mean_retrieval_recall, judge_means],
    )
    runs = {e.name: e for e in result.run_evaluations}
    crashed = len(context.data) - len(result.item_results)
    hard = runs["hard_failures"].value
    if hard + crashed > 0:
        raise RegressionError(
            result=result,
            metric="hard_failures",
            value=hard + crashed,
            threshold=0,
            message=f"{hard} hard-rule failures, {crashed} crashed cases",
        )
    if "mean_accuracy" in runs and runs["mean_accuracy"].value < GATE["min_accuracy"]:
        raise RegressionError(
            result=result, metric="mean_accuracy", value=runs["mean_accuracy"].value, threshold=GATE["min_accuracy"]
        )
    recall = runs.get("mean_retrieval_recall")
    if recall and recall.value < GATE["retrieval"]["min_recall"]:
        raise RegressionError(
            result=result, metric=recall.name, value=recall.value, threshold=GATE["retrieval"]["min_recall"]
        )
    for name, bound in (JUDGE.get("thresholds") or {}).items():
        mean = runs.get(f"mean_{name}")
        # The SDK logs and drops a failed evaluator call; gating on the cases that did score would weaken the gate.
        scored = mean.metadata["cases"] if mean else 0
        if scored < len(result.item_results):
            raise RegressionError(
                result=result,
                metric=f"{name} cases judged",
                value=scored,
                threshold=len(result.item_results),
                message=f"judge scored {name} on {scored} of {len(result.item_results)} cases; see the logged errors",
            )
        if not bound.get("min", mean.value) <= mean.value <= bound.get("max", mean.value):
            raise RegressionError(result=result, metric=mean.name, value=mean.value, threshold=bound.get("min", bound.get("max")))
    return result


if __name__ == "__main__":
    client = get_client()
    try:
        print(experiment(RunnerContext(client=client, data=[to_item(c) for c in load_cases()])).format(include_item_results=True))
    except RegressionError as e:
        print(e.result.format(include_item_results=True))
        raise
    finally:
        client.flush()
