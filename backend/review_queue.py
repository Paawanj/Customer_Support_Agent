from copy import deepcopy


review_queue = {}


def add_review_item(state):
    ticket_id = state.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        raise ValueError("A review item needs a ticket ID.")

    customer_id = state.get("customer_id")
    key = (customer_id, ticket_id)
    review_id = f"review:{customer_id or 'UNKNOWN'}:{ticket_id}"
    ticket = state.get("ticket", "")
    summary = " ".join(ticket.split())[:280] if isinstance(ticket, str) else "Invalid ticket text."
    item = {
        "review_id": review_id,
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "ticket": ticket,
        "summary": summary or "Empty ticket text.",
        "category": state.get("category"),
        "confidence": state.get("confidence"),
        "reasoning": state.get("reasoning", ""),
        "classification_error": state.get("classification_error", ""),
        "route": state.get("route", ""),
        "escalation_reason": state.get("escalation_reason") or "manual_review_required",
        "response": state.get("response") or "This ticket needs human review.",
        "tool_outcomes": state.get("tool_outcomes", []),
        "retrieved_source_ids": state.get("retrieved_source_ids", []),
        "citations": state.get("citations", []),
        "currency": "INR",
        "status": "OPEN",
    }
    review_queue[key] = deepcopy(item)
    return review_id


def get_review_items():
    return deepcopy(list(review_queue.values()))
