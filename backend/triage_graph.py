from langgraph.graph import StateGraph, START, END

from state import TicketState
from graph_nodes import (
    classify_node, billing_node, tech_node, escalation_node, route_ticket, route_billing, route_tech,
)


graph = StateGraph(TicketState)
graph.add_node("classify", classify_node)
graph.add_node("billing", billing_node)
graph.add_node("tech", tech_node)
graph.add_node("escalate", escalation_node)

graph.add_edge(START, "classify")
graph.add_conditional_edges("classify", route_ticket, {
    "billing": "billing",
    "tech": "tech",
    "low_conf": "escalate",
})
graph.add_conditional_edges("billing", route_billing, {
    "escalate": "escalate",
    "done": END,
})
graph.add_conditional_edges("tech", route_tech, {
    "escalate": "escalate",
    "done": END,
})
graph.add_edge("escalate", END)

workflow = graph.compile()
