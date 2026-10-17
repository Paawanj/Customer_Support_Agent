from typing import TypedDict


class TicketState(TypedDict, total=False):
    ticket_id: str
    ticket: str
    category: str | None
    confidence: float | None
    reasoning: str
    classification_error: str
    route: str
    escalation_reason: str
    response: str
    status: str
    customer_id: str
    tool_outcomes: list[dict]
    retrieved_source_ids: list[str]
    citations: list[str]
