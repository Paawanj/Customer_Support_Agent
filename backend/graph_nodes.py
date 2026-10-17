from classifier import classify_ticket
from state import TicketState


def classify_node(state: TicketState):
    try:
        result = classify_ticket(state["ticket"])
    except Exception as error:
        return {
            "category": None,
            "confidence": None,
            "reasoning": "Classification unavailable.",
            "classification_error": type(error).__name__,
            "route": "low_conf",
            "escalation_reason": "classification_failed",
        }

    text = state["ticket"].lower()
    angry = any(word in text for word in ["angry", "furious", "unacceptable", "fed up"])

    if angry:
        route = "low_conf"
        reason = "angry_ticket"
    elif result.confidence < 0.6:
        route = "low_conf"
        reason = "low_confidence"
    elif result.category == "billing":
        route = "billing"
        reason = ""
    else:
        route = "tech"
        reason = ""

    return {
        "category": result.category,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "classification_error": "",
        "route": route,
        "escalation_reason": reason,
    }
def billing_node(state: TicketState):
    from billing_agent import run_billing_agent
    return run_billing_agent(state)


def route_billing(state: TicketState):
    if state["status"] == "NEEDS_REVIEW":
        return "escalate"
    return "done"


def tech_node(state: TicketState):
    return {
        "response": "Technical or FAQ ticket received for specialist review.",
        "status": "PENDING_SPECIALIST",
    }


def escalation_node(state: TicketState):
    return {
        "response": state.get("response") or "This ticket needs human review.",
        "status": "ESCALATED",
    }



def route_ticket(state: TicketState):
    return state["route"]


def tech_node(state: TicketState):
    from tech_agent import run_tech_agent
    return run_tech_agent(state)


def route_tech(state: TicketState):
    if state["status"] == "NEEDS_REVIEW":
        return "escalate"
    return "done"
