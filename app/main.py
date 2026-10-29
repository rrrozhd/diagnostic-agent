import os
from functools import cache

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.agents.copilot import CostTracker
from app.config import ROOT

app = FastAPI()


@cache
def get_graph():
    # Built on first request, not at import, so tests and CI run without model keys.
    from app.graph import build_graph

    return build_graph()


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    tracker = CostTracker()
    callbacks: list = [tracker]
    langfuse = None
    if os.environ.get("LANGFUSE_PUBLIC_KEY"):
        from langfuse.langchain import CallbackHandler

        langfuse = CallbackHandler()
        callbacks.append(langfuse)
    state = get_graph().invoke(
        # refusal/response are per turn; reset them so a checkpointed value never leaks into this turn.
        {"messages": [HumanMessage(req.message)], "refusal": None, "response": None},
        {"configurable": {"thread_id": req.thread_id}, "callbacks": callbacks},
    )
    return {
        "thread_id": req.thread_id,
        "refused": not state["guardrail_passed"],
        "refusal": state["refusal"],
        "response": state["response"],
        "cost_usd": tracker.cost_usd,
        "model_calls": tracker.model_calls,
        "trace_id": langfuse.last_trace_id if langfuse else None,
    }


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
