from types import SimpleNamespace

import pytest

from app import guardrails
from app.config import REFUSAL_FILE

QUESTIONS = guardrails.load_questions()


class FakeClient:
    def __init__(self, probs=None, error=None):
        self.probs, self.error, self.calls = probs or {}, error, []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        return SimpleNamespace(
            nouls={n: SimpleNamespace(noul=self.probs[n]) for n in questions}, model="jev-fake"
        )


def safe_probs():
    """P(yes) on the passing side of every threshold."""
    return {q["name"]: 1.0 if q["fail_when"] == "no" else 0.0 for q in QUESTIONS}


def test_pass_uses_one_call_with_all_questions():
    client = FakeClient(safe_probs())
    r = guardrails.check("58-year-old man with fever", client)
    assert r.passed and r.failed == [] and r.model == "jev-fake"
    assert r.answers == safe_probs()
    assert len(client.calls) == 1
    assert client.calls[0][0] == "58-year-old man with fever"
    assert set(client.calls[0][1]) == {q["name"] for q in QUESTIONS}


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["name"])
def test_each_question_fails_in_its_direction(q):
    probs = safe_probs() | {q["name"]: 0.0 if q["fail_when"] == "no" else 1.0}
    r = guardrails.check("x", FakeClient(probs))
    assert not r.passed and r.failed == [q["name"]]


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["name"])
def test_threshold_edge(q):
    t = q["threshold"]
    at = guardrails.check("x", FakeClient(safe_probs() | {q["name"]: t}))
    # At exactly the threshold a yes-question fails and a no-question passes.
    assert at.passed == (q["fail_when"] == "no")
    just_below = guardrails.check("x", FakeClient(safe_probs() | {q["name"]: t - 1e-6}))
    assert just_below.passed == (q["fail_when"] == "yes")


def test_jev_error_fails_closed():
    r = guardrails.check("x", FakeClient(error=RuntimeError("boom")))
    assert r == guardrails.GuardrailResult(passed=False, answers={}, failed=["jev_error"], model=None)


def test_missing_answer_fails_closed():
    client = FakeClient(safe_probs())
    client.system_one = lambda state, questions: SimpleNamespace(nouls={}, model="m")
    assert guardrails.check("x", client).failed == ["jev_error"]


def test_bad_fail_when_rejected(tmp_path, monkeypatch):
    f = tmp_path / "g.yaml"
    f.write_text("- {name: a, instructions: q, fail_when: 'Yes', threshold: 0.5}\n")
    monkeypatch.setattr(guardrails, "GUARDRAIL_FILE", f)
    with pytest.raises(ValueError):
        guardrails.load_questions()


def test_refusal_text_is_the_file_verbatim():
    assert guardrails.refusal_text() == REFUSAL_FILE.read_text()
    assert "chest pain" in guardrails.refusal_text()
