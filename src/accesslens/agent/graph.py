"""Wire the nodes into the audit graph (TRD §4).

    validate -> parse -> rule_checks -+-> select_llm_items -> llm_checks -+-> merge -> build_report
                                      +---------- rules_only ------------+

Node names differ from state keys on purpose; LangGraph forbids the two sharing a name.
"""

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from accesslens.agent.nodes import Deps, make_nodes
from accesslens.agent.state import AuditState


def route_after_rules(state: AuditState) -> Literal["llm", "skip"]:
    return "llm" if state["mode"] == "full" else "skip"


def build_graph(deps: Deps) -> Any:
    nodes = make_nodes(deps)
    graph = StateGraph(AuditState)
    for name, fn in nodes.items():
        node: Any = fn  # LangGraph's overloads do not accept a plain Callable alias
        graph.add_node(name, node)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "parse")
    graph.add_edge("parse", "rule_checks")
    graph.add_conditional_edges(
        "rule_checks", route_after_rules, {"llm": "select_llm_items", "skip": "merge"}
    )
    graph.add_edge("select_llm_items", "llm_checks")
    graph.add_edge("llm_checks", "merge")
    graph.add_edge("merge", "build_report")
    graph.add_edge("build_report", END)
    return graph.compile()
