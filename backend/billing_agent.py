import json
from typing import TypedDict, Annotated

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from billing_tools import billing_tools


# 1. State
class BillingState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    customer_id: str
    ticket_id: str
    model_calls: int
    last_order: dict | None
    tool_outcomes: list[dict]
    response: str
    status: str
    escalation_reason: str


# 2. Final state update
def finalize_billing_response(response, status, reason, outcomes, model_calls):
    return {
        "messages": [AIMessage(content=response)],
        "response": response,
        "status": status,
        "escalation_reason": reason,
        "tool_outcomes": outcomes,
        "model_calls": model_calls,
    }


# 3. Nodes
def billing_agent_node(state: BillingState, config: RunnableConfig):
    messages = state["messages"]
    customer_id = state.get("customer_id")
    ticket_id = state.get("ticket_id")
    outcomes = state.get("tool_outcomes", [])
    last_order = state.get("last_order")
    model_calls = state["model_calls"]
    review_response = "This billing request needs human review."

    if customer_id not in ["C-001", "C-002"] or not isinstance(ticket_id, str) or not ticket_id.strip():
        return finalize_billing_response(review_response, "NEEDS_REVIEW", "missing_customer_context", outcomes, model_calls)

    last_message = messages[-1]
    if isinstance(last_message, ToolMessage):
        result = json.loads(last_message.content)
        outcomes = outcomes + [{"tool": last_message.name, "result": result}]
        if result["status"] == "REVIEW_REQUIRED":
            return finalize_billing_response(review_response, "NEEDS_REVIEW", result["reason"], outcomes, model_calls)
        if result["status"] in ["REFUNDED", "ALREADY_REFUNDED"]:
            label = "recorded" if result["status"] == "REFUNDED" else "already recorded"
            response = (
                f"Simulated refund of ₹{result['amount_paise'] / 100:,.2f} for "
                f"order {result['order_id']} {label}."
            )
            return finalize_billing_response(response, "ANSWERED", "", outcomes, model_calls)
        last_order = result

    if model_calls >= 3:
        return finalize_billing_response(review_response, "NEEDS_REVIEW", "billing_tool_limit", outcomes, model_calls)

    billing_model = config.get("configurable", {}).get("billing_model")
    if billing_model is None:
        from model import model as billing_model
    billing_model_with_tools = billing_model.bind_tools(billing_tools)
    reply = billing_model_with_tools.invoke(messages)
    model_calls += 1

    if reply.invalid_tool_calls:
        return finalize_billing_response(review_response, "NEEDS_REVIEW", "invalid_billing_tool_call", outcomes, model_calls)
    if not reply.tool_calls:
        if last_order is None:
            return finalize_billing_response(review_response, "NEEDS_REVIEW", "billing_details_required", outcomes, model_calls)
        response = (
            f"Order {last_order['order_id']}: paid ₹{last_order['paid_paise'] / 100:,.2f}; "
            f"previously refunded ₹{last_order['refunded_paise'] / 100:,.2f}. "
            f"Refund eligible: {last_order['eligible']}. "
            "No refund was issued during this request. "
            "For a refund, provide the order ID and requested amount. "
            "Other billing actions need human review."
        )
        return finalize_billing_response(response, "ANSWERED", "", outcomes, model_calls)
    if len(reply.tool_calls) != 1:
        return finalize_billing_response(review_response, "NEEDS_REVIEW", "one_tool_at_a_time", outcomes, model_calls)

    call = reply.tool_calls[0]
    if call["name"] not in [item.name for item in billing_tools]:
        return finalize_billing_response(review_response, "NEEDS_REVIEW", "unknown_billing_tool", outcomes, model_calls)
    if call["name"] == "issue_refund" and (
        last_order is None or last_order["order_id"] != call["args"].get("order_id")
    ):
        return finalize_billing_response(review_response, "NEEDS_REVIEW", "order_lookup_required", outcomes, model_calls)

    args = dict(call["args"])
    args["customer_id"] = customer_id
    if call["name"] == "issue_refund":
        args["ticket_id"] = ticket_id
    call["args"] = args

    return {
        "messages": [reply],
        "model_calls": model_calls,
        "last_order": last_order,
        "tool_outcomes": outcomes,
    }


billing_tools_node = ToolNode(billing_tools, handle_tool_errors=False)


# 4. Graph
billing_graph = StateGraph(BillingState)
billing_graph.add_node("billing_agent_node", billing_agent_node)
billing_graph.add_node("billing_tools", billing_tools_node)
billing_graph.add_edge(START, "billing_agent_node")
billing_graph.add_conditional_edges("billing_agent_node", tools_condition, {
    "tools": "billing_tools",
    "__end__": END,
})
billing_graph.add_edge("billing_tools", "billing_agent_node")
billing_workflow = billing_graph.compile()
billing_workflow.get_graph().draw_mermaid_png(
    output_file_path="billing_agent.png"
)

# 5. Connect the billing graph to the outer ticket graph
def run_billing_agent(state, billing_model=None):
    messages = [
        SystemMessage(content="""You handle NovaCart order lookups and simulated refunds.
Use get_order before issue_refund, and request only one tool at a time.
Python supplies customer_id and ticket_id; you cannot change the customer or operation key.
Use only the order and amount requested by the customer. Do not invent missing details.
All amounts are INR in integer paise: ₹2,500 = 250000 paise.
Automatic refunds are limited to ₹5,000 total per order; larger amounts need human review.
Invoices, plan changes, and other unsupported actions need human review.
Never claim an action succeeded without a successful tool result."""),
        HumanMessage(content=state["ticket"]),
    ]
    try:
        result = billing_workflow.invoke({
            "messages": messages,
            "customer_id": state.get("customer_id"),
            "ticket_id": state.get("ticket_id"),
            "model_calls": 0,
            "last_order": None,
            "tool_outcomes": [],
        }, config={"recursion_limit": 10, "configurable": {"billing_model": billing_model}})
    except Exception as error:
        return {
            "response": "This billing request needs human review.",
            "status": "NEEDS_REVIEW",
            "escalation_reason": "billing_failed_" + type(error).__name__,
            "tool_outcomes": [],
        }
    return {
        "response": result["response"],
        "status": result["status"],
        "escalation_reason": result["escalation_reason"],
        "tool_outcomes": result["tool_outcomes"],
    }
