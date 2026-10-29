"""Input screening and output checks."""

import logging
from dataclasses import dataclass

import yaml
from typesafe_sdk import Noul, TypeSafeClient

from app.config import GUARDRAIL_FILE, JEV_MODEL, REFUSAL_FILE

log = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    passed: bool
    answers: dict[str, float]
    failed: list[str]
    model: str | None


def load_questions() -> list[dict]:
    questions = yaml.safe_load(GUARDRAIL_FILE.read_text())
    for q in questions:
        # A typo here would silently flip the direction and fail open.
        if q["fail_when"] not in ("yes", "no") or not 0 <= q["threshold"] <= 1:
            raise ValueError(f"bad guardrail question: {q['name']}")
    return questions


def fails(q: dict, p: float) -> bool:
    return p >= q["threshold"] if q["fail_when"] == "yes" else p < q["threshold"]


def check(prompt: str, client=None) -> GuardrailResult:
    """Screen the first message with one Jev call; any error fails closed."""
    questions = load_questions()
    try:
        client = client or TypeSafeClient(model=JEV_MODEL)
        res = client.system_one(prompt, {q["name"]: Noul(instructions=q["instructions"]) for q in questions})
        answers = {q["name"]: res.nouls[q["name"]].noul for q in questions}
    except Exception as e:  # noqa: BLE001 - any Jev failure fails closed (refusal); never log the prompt: it may carry PHI
        log.warning("Jev guardrail call failed: %r", e)
        return GuardrailResult(passed=False, answers={}, failed=["jev_error"], model=None)
    failed = [q["name"] for q in questions if fails(q, answers[q["name"]])]
    return GuardrailResult(passed=not failed, answers=answers, failed=failed, model=res.model)


def refusal_text() -> str:
    return REFUSAL_FILE.read_text()
