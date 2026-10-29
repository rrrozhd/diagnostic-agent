"""LangGraph: node registration and edges only.

START -> guardrail (first message of a thread) --fail--> END (refusal, no model call)
                                               --pass--> agent (deep agent) -> END
Later turns on a passed thread go START -> agent.
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agents.copilot import agent_node, build_agent, guardrail


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    guardrail_passed: bool | None
    refusal: str | None
    response: dict | None  # CopilotResponse.model_dump() for this turn
    cost_usd: Annotated[float, operator.add]  # thread total


def build_graph(agent=None, checkpointer=None):
    graph = StateGraph(State)
    graph.add_node("guardrail", guardrail)
    graph.add_node("agent", agent_node(agent or build_agent()))
    graph.add_conditional_edges(START, lambda s: "agent" if s.get("guardrail_passed") else "guardrail")
    graph.add_conditional_edges("guardrail", lambda s: "agent" if s["guardrail_passed"] else END)
    graph.add_edge("agent", END)
    # shortcut: in-memory threads vanish on restart; switch to a Postgres checkpointer before deploying.
    return graph.compile(checkpointer=checkpointer or InMemorySaver())
