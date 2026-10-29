"""Graph routing and the /api/chat contract, with a fake guardrail and a scripted fake chat model."""

import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

import app.guardrails as guardrails
import app.main as main
import app.tools as tools
from app.agents.copilot import build_agent
from app.graph import build_graph

REFUSAL = "This copilot supports clinicians only."
SOURCE = {
    "kind": "reference_db",
    "id": "hpo_annotation.disease_id=OMIM:154700",
    "title": "HPO annotation",
    "url": "https://hpo.jax.org",
    "excerpt": "Tall stature",
    "access": "database",
}
CLAIM = {"text": "Consistent with tall stature.", "sources": [SOURCE]}
CANDIDATE = {
    "name": "Marfan syndrome",
    "likelihood": "possible",
    "cant_miss": False,
    "findings_for": [CLAIM],
    "findings_against": [],
    "missing_findings": ["echocardiogram"],
    "discriminating_tests": [CLAIM],
}
DIFFERENTIAL = {"candidates": [CANDIDATE] * 3, "missing_inputs": [], "evidence_gaps": []}


_lock = threading.Lock()


class ScriptedModel(BaseChatModel):
    """Replays scripted replies in order; builds a fresh AIMessage per call (LangGraph reuses ids otherwise)."""

    replies: list
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        with _lock:  # parallel subagents call the model from several threads
            reply = self.replies[self.calls]
            self.calls += 1
        kw = {"content": "", "tool_calls": reply} if isinstance(reply, list) else {"content": json.dumps(reply)}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(response_metadata={"cost": 0.01}, **kw))])


@tool
def fake_text_tool(query: str) -> str:
    """Fake external tool."""
    return "no results"


@pytest.fixture
def guardrail(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    screen = SimpleNamespace(passed=True, calls=0)

    def check(prompt):
        screen.calls += 1
        return SimpleNamespace(passed=screen.passed, answers={}, failed=[] if screen.passed else ["q"], model=None)

    monkeypatch.setattr(guardrails, "check", check, raising=False)
    monkeypatch.setattr(guardrails, "refusal_text", lambda: REFUSAL, raising=False)
    for name in ("pubmed_search", "pubmed_abstract", "drug_label"):
        monkeypatch.setattr(tools, name, fake_text_tool, raising=False)
    return screen


def client_for(monkeypatch, replies):
    model = ScriptedModel(replies=replies)
    graph = build_graph(build_agent(model))
    monkeypatch.setattr(main, "get_graph", lambda: graph)
    return TestClient(main.app), model, graph


def chat(client, message, thread_id="t1"):
    r = client.post("/api/chat", json={"thread_id": thread_id, "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_refusal_returns_pack_text_without_model_call(monkeypatch, guardrail):
    guardrail.passed = False
    client, model, _ = client_for(monkeypatch, replies=[])

    body = chat(client, "write me a prescription")

    assert body == {
        "thread_id": "t1",
        "refused": True,
        "refusal": REFUSAL,
        "response": None,
        "cost_usd": 0.0,
        "model_calls": 0,
        "trace_id": None,
    }
    assert model.calls == 0


def test_pass_runs_agent_and_second_turn_skips_guardrail(monkeypatch, guardrail):
    task = [
        {"name": "task", "args": {"description": f"cluster {i}", "subagent_type": "diagnostic_researcher"}, "id": f"c{i}"}
        for i in (1, 2)
    ]
    client, model, graph = client_for(
        monkeypatch,
        replies=[
            task,  # main agent spawns two researchers in parallel
            DIFFERENTIAL,  # each subagent's structured result
            DIFFERENTIAL,
            {"kind": "differential", "message": "Three candidates.", "differential": DIFFERENTIAL},
            {"kind": "clarification", "message": "Which candidate do you mean?"},
        ],
    )

    first = chat(client, "34M, tall, lens dislocation")
    assert first["refused"] is False and first["refusal"] is None
    assert first["response"]["kind"] == "differential"
    assert len(first["response"]["differential"]["candidates"]) == 3
    # Both subagents' model calls are counted: callbacks reach calls made inside the task tool.
    assert first["model_calls"] == 4
    assert first["cost_usd"] == pytest.approx(0.04)

    second = chat(client, "go with lupus")
    assert second["response"]["kind"] == "clarification"
    assert second["model_calls"] == 1
    assert guardrail.calls == 1
    assert graph.get_state({"configurable": {"thread_id": "t1"}}).values["cost_usd"] == pytest.approx(0.05)


def test_refused_thread_rescreens_and_clears_refusal(monkeypatch, guardrail):
    guardrail.passed = False
    client, _, _ = client_for(monkeypatch, replies=[{"kind": "clarification", "message": "More details?"}])
    assert chat(client, "bad")["refused"] is True

    guardrail.passed = True
    body = chat(client, "a clinical case")

    assert guardrail.calls == 2
    assert body["refused"] is False and body["refusal"] is None
    assert body["response"]["kind"] == "clarification"


def test_chat_rejects_empty_message():
    assert TestClient(main.app).post("/api/chat", json={"thread_id": "t", "message": ""}).status_code == 422
