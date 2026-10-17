from unittest.mock import patch

from schemas import TicketClassification
from triage_graph import workflow


def billing_placeholder(state):
    return {"response": "Billing placeholder.", "status": "PENDING_SPECIALIST"}


def tech_placeholder(state):
    return {"response": "Tech placeholder.", "status": "PENDING_SPECIALIST"}


def test_routes_and_threshold():
    cases = [
        ("billing", 0.9, "billing", "PENDING_SPECIALIST"),
        ("billing", 0.6, "billing", "PENDING_SPECIALIST"),
        ("tech", 0.9, "tech", "PENDING_SPECIALIST"),
        ("general", 0.9, "tech", "PENDING_SPECIALIST"),
        ("general", 0.59, "low_conf", "ESCALATED"),
        ("general", 0.0, "low_conf", "ESCALATED"),
    ]
    for category, confidence, route, status in cases:
        classification = TicketClassification(category=category, confidence=confidence, reasoning="Example.")
        with patch("graph_nodes.classify_ticket", return_value=classification), \
            patch("billing_agent.run_billing_agent", side_effect=billing_placeholder), \
            patch("tech_agent.run_tech_agent", side_effect=tech_placeholder):
            result = workflow.invoke({"ticket_id": "T-001", "ticket": "Please check my ticket."})
        assert result["route"] == route
        assert result["status"] == status
        assert result["confidence"] == confidence
        assert result["escalation_reason"] == ("low_confidence" if route == "low_conf" else "")


def test_anger_overrides_confident_billing():
    classification = TicketClassification(category="billing", confidence=0.95, reasoning="Duplicate charge.")
    for word in ["ANGRY", "furious", "unacceptable", "fed up"]:
        with patch("graph_nodes.classify_ticket", return_value=classification), \
            patch("billing_agent.run_billing_agent", side_effect=billing_placeholder), \
            patch("tech_agent.run_tech_agent", side_effect=tech_placeholder):
            result = workflow.invoke({"ticket_id": "T-002", "ticket": "I am " + word})
        assert result["route"] == "low_conf"
        assert result["escalation_reason"] == "angry_ticket"
        assert result["confidence"] == 0.95
        assert result["status"] == "ESCALATED"


def test_classification_failure_escalates():
    with patch("graph_nodes.classify_ticket", side_effect=ValueError("Private provider details.")):
        result = workflow.invoke({"ticket_id": "T-003", "ticket": "Please check my charge."})
    assert result["category"] is None
    assert result["confidence"] is None
    assert result["classification_error"] == "ValueError"
    assert result["escalation_reason"] == "classification_failed"
    assert result["status"] == "ESCALATED"
    assert "Private provider details" not in str(result)


def test_empty_ticket_escalates_without_api_call():
    result = workflow.invoke({"ticket_id": "T-004", "ticket": ""})
    assert result["classification_error"] == "ValueError"
    assert result["status"] == "ESCALATED"


def test_every_branch_finishes_after_two_nodes():
    cases = [("billing", 0.9, "billing"), ("tech", 0.9, "tech"), ("general", 0.2, "escalate")]
    for category, confidence, destination in cases:
        classification = TicketClassification(category=category, confidence=confidence, reasoning="Example.")
        with patch("graph_nodes.classify_ticket", return_value=classification), \
            patch("billing_agent.run_billing_agent", side_effect=billing_placeholder), \
            patch("tech_agent.run_tech_agent", side_effect=tech_placeholder):
            updates = list(workflow.stream({"ticket_id": "T-005", "ticket": "Example ticket."}, stream_mode="updates"))
        assert [list(update)[0] for update in updates] == ["classify", destination]


def test_ticket_state_is_separate_between_runs():
    classification = TicketClassification(category="billing", confidence=0.9, reasoning="Duplicate charge.")
    first_input = {"ticket_id": "T-006", "ticket": "I am angry about my charge."}
    second_input = {"ticket_id": "T-007", "ticket": "Please check my charge."}
    with patch("graph_nodes.classify_ticket", return_value=classification), \
            patch("billing_agent.run_billing_agent", side_effect=billing_placeholder), \
            patch("tech_agent.run_tech_agent", side_effect=tech_placeholder):
        first = workflow.invoke(first_input)
        second = workflow.invoke(second_input)
    assert first["status"] == "ESCALATED"
    assert first["escalation_reason"] == "angry_ticket"
    assert second["ticket_id"] == "T-007"
    assert second["route"] == "billing"
    assert second["escalation_reason"] == ""
    assert second["classification_error"] == ""
    assert second["status"] == "PENDING_SPECIALIST"
    assert first_input == {"ticket_id": "T-006", "ticket": "I am angry about my charge."}
    assert second_input == {"ticket_id": "T-007", "ticket": "Please check my charge."}
