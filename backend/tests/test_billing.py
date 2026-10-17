from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from pydantic import ValidationError

from billing_agent import run_billing_agent, billing_workflow
from billing_tools import get_order, issue_refund, billing_tools
from mock_store import orders, refunds
from schemas import TicketClassification
from triage_graph import workflow


def fresh_store():
    store = deepcopy(orders)
    for order in store.values():
        order["refunded_paise"] = 0
    return store


def refund_request(order_id, amount_paise, ticket_id, customer_id="C-001"):
    return issue_refund.invoke({
        "order_id": order_id, "amount_paise": amount_paise,
        "customer_id": customer_id, "ticket_id": ticket_id,
    })


def ticket(ticket_id="T-BILL", customer_id="C-001"):
    return {"ticket_id": ticket_id, "customer_id": customer_id,
            "ticket": "Refund ₹2,500 for order O-1001."}


def tool_reply(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_owned_order_and_tool_list():
    with patch.dict(orders, fresh_store(), clear=True):
        assert [item.name for item in billing_tools] == ["get_order", "issue_refund"]
        found = get_order.invoke({"order_id": "O-1001", "customer_id": "C-001"})
        assert found["currency"] == "INR"
        assert found["paid_paise"] == 250000
        found["paid_paise"] = 0
        assert orders["O-1001"]["paid_paise"] == 250000
        for order_id in ["O-2001", "O-MISSING"]:
            assert get_order.invoke({"order_id": order_id, "customer_id": "C-001"}) == {
                "status": "REVIEW_REQUIRED", "reason": "order_unavailable"}


def test_refund_replay_and_changed_request():
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        assert refund_request("O-1001", 250000, "T-REFUND")["status"] == "REFUNDED"
        assert refund_request("O-1001", 250000, "T-REFUND")["status"] == "ALREADY_REFUNDED"
        assert orders["O-1001"]["refunded_paise"] == 250000
        assert len(refunds) == 1
        for order_id, amount in [("O-1001", 100000), ("O-1002", 250000)]:
            assert refund_request(order_id, amount, "T-REFUND")["reason"] == "refund_request_changed"
        assert orders["O-1002"]["refunded_paise"] == 0


def test_refund_policy_and_no_denied_mutations():
    cases = [
        ("O-2001", 100000, "order_unavailable"),
        ("O-MISSING", 100000, "order_unavailable"),
        ("O-1003", 100000, "refund_ineligible"),
        ("O-1001", 260000, "exceeds_remaining_payment"),
        ("O-1002", 750000, "manager_approval_required"),
    ]
    for order_id, amount, reason in cases:
        with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
            before = deepcopy(orders)
            assert refund_request(order_id, amount, "T-DENIED")["reason"] == reason
            assert orders == before
            assert refunds == {}


def test_invalid_amounts_raise_before_mutation():
    for amount in [0, -1, 25.5, "250000", True]:
        with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
            with pytest.raises(ValidationError):
                refund_request("O-1001", amount, "T-INVALID")
            assert orders["O-1001"]["refunded_paise"] == 0
            assert refunds == {}


def test_exact_five_thousand_and_cumulative_limit():
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        assert refund_request("O-1002", 500000, "T-5000")["status"] == "REFUNDED"
        assert refund_request("O-1002", 10000, "T-SPLIT")["reason"] == "manager_approval_required"
        assert orders["O-1002"]["refunded_paise"] == 500000
        assert len(refunds) == 1


def test_remaining_balance_after_partial_refund():
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        refund_request("O-1001", 100000, "T-PARTIAL")
        assert refund_request("O-1001", 150001, "T-TOO-MUCH")["reason"] == "exceeds_remaining_payment"
        assert orders["O-1001"]["refunded_paise"] == 100000


def test_agent_executes_tools_and_uses_results():
    mock_billing_model = Mock()
    mock_billing_model.bind_tools.return_value.invoke.side_effect = [
        tool_reply("get_order", {"order_id": "O-1001"}, "call-1"),
        tool_reply("issue_refund", {"order_id": "O-1001", "amount_paise": 250000}, "call-2"),
    ]
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        result = run_billing_agent(ticket(), mock_billing_model)
        assert result["status"] == "ANSWERED"
        assert result["tool_outcomes"][-1]["result"]["currency"] == "INR"
        assert result["response"] == "Simulated refund of ₹2,500.00 for order O-1001 recorded."
        assert orders["O-1001"]["refunded_paise"] == 250000
        assert [item["tool"] for item in result["tool_outcomes"]] == ["get_order", "issue_refund"]
        assert any(isinstance(message, ToolMessage) for message in mock_billing_model.bind_tools.return_value.invoke.call_args.args[0])
        assert mock_billing_model.bind_tools.return_value.invoke.call_count == 2


def test_model_text_cannot_fabricate_refund_success():
    mock_billing_model = Mock()
    mock_billing_model.bind_tools.return_value.invoke.side_effect = [
        tool_reply("get_order", {"order_id": "O-1001"}, "call-1"),
        AIMessage(content="Refund completed!"),
    ]
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        result = run_billing_agent(ticket(), mock_billing_model)
        assert "No refund was issued" in result["response"]
        assert "Refund completed!" not in result["response"]
        assert orders["O-1001"]["refunded_paise"] == 0
        assert refunds == {}


def test_agent_requires_context_and_verified_lookup():
    mock_billing_model = Mock()
    assert run_billing_agent({"ticket_id": "T-NO-CUSTOMER", "ticket": "Refund me."}, mock_billing_model)["status"] == "NEEDS_REVIEW"
    mock_billing_model.bind_tools.assert_not_called()
    mock_billing_model.bind_tools.return_value.invoke.return_value = tool_reply(
        "issue_refund", {"order_id": "O-1001", "amount_paise": 250000}, "call-1")
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        result = run_billing_agent(ticket(), mock_billing_model)
        assert result["escalation_reason"] == "order_lookup_required"
        assert refunds == {}


def test_agent_bounds_and_failures():
    cases = [
        ([AIMessage(content="Refund done")], "billing_details_required"),
        ([tool_reply("delete_order", {}, "call-1")], "unknown_billing_tool"),
        ([tool_reply("get_order", {"order_id": 7}, "call-1")], "billing_failed_ToolInvocationError"),
        ([RuntimeError("Private provider details")], "billing_failed_RuntimeError"),
        ([tool_reply("get_order", {"order_id": "O-1001"}, "call-" + str(index))
          for index in range(3)], "billing_tool_limit"),
        ([AIMessage(content="", tool_calls=[
            {"name": "get_order", "args": {"order_id": "O-1001"}, "id": str(index)}
            for index in range(2)])], "one_tool_at_a_time"),
    ]
    for replies, reason in cases:
        mock_billing_model = Mock()
        mock_billing_model.bind_tools.return_value.invoke.side_effect = replies
        with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
            result = run_billing_agent(ticket(), mock_billing_model)
            assert result["status"] == "NEEDS_REVIEW"
            assert result["escalation_reason"] == reason
            assert "Private provider details" not in str(result)
            assert mock_billing_model.bind_tools.return_value.invoke.call_count <= 3
            assert refunds == {}


def test_graph_refund_and_review_termination():
    classification = TicketClassification(category="billing", confidence=0.9, reasoning="Refund request.")
    for order_id, amount, nodes, status in [
        ("O-1001", 250000, ["classify", "billing"], "ANSWERED"),
        ("O-1002", 750000, ["classify", "billing", "escalate"], "ESCALATED"),
        ("O-2001", 250000, ["classify", "billing", "escalate"], "ESCALATED"),
    ]:
        mock_billing_model = Mock()
        mock_billing_model.bind_tools.return_value.invoke.side_effect = [
            tool_reply("get_order", {"order_id": order_id}, "call-1"),
            tool_reply("issue_refund", {"order_id": order_id, "amount_paise": amount}, "call-2"),
        ]
        with (
            patch.dict(orders, fresh_store(), clear=True),
            patch.dict(refunds, {}, clear=True),
            patch("graph_nodes.classify_ticket", return_value=classification),
            patch("billing_agent.run_billing_agent", side_effect=lambda state: run_billing_agent(state, mock_billing_model)),
        ):
            updates = list(workflow.stream(ticket(), stream_mode="updates"))
            assert [list(update)[0] for update in updates] == nodes
            final = list(updates[-1].values())[0]
            assert final["status"] == status
            if status == "ANSWERED":
                assert orders["O-1001"]["refunded_paise"] == 250000
            else:
                assert refunds == {}
                billing = updates[1]["billing"]
                assert billing["escalation_reason"] in ["manager_approval_required", "order_unavailable"]
                assert final["response"] == billing["response"]


def test_model_cannot_override_python_context():
    mock_billing_model = Mock()
    mock_billing_model.bind_tools.return_value.invoke.return_value = tool_reply(
        "get_order", {"order_id": "O-2001", "customer_id": "C-002"}, "call-1")
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        result = run_billing_agent(ticket(), mock_billing_model)
        assert result["escalation_reason"] == "order_unavailable"
        assert refunds == {}
    mock_billing_model.bind_tools.return_value.invoke.side_effect = [
        tool_reply("get_order", {"order_id": "O-1001", "customer_id": "C-002"}, "call-1"),
        tool_reply("issue_refund", {
            "order_id": "O-1001", "amount_paise": 250000,
            "customer_id": "C-002", "ticket_id": "FAKE-TICKET",
        }, "call-2"),
    ]
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        assert run_billing_agent(ticket(), mock_billing_model)["status"] == "ANSWERED"
        assert set(refunds) == {("C-001", "T-BILL")}
        assert orders["O-1001"]["refunded_paise"] == 250000


def test_inner_tool_graph_trace_and_result_messages():
    mock_billing_model = Mock()
    mock_billing_model.bind_tools.return_value.invoke.side_effect = [
        tool_reply("get_order", {"order_id": "O-1001"}, "call-1"),
        tool_reply("issue_refund", {"order_id": "O-1001", "amount_paise": 250000}, "call-2"),
    ]
    with patch.dict(orders, fresh_store(), clear=True), patch.dict(refunds, {}, clear=True):
        updates = list(billing_workflow.stream({
            "messages": [HumanMessage(content="Refund ₹2,500 for order O-1001.")],
            "customer_id": "C-001", "ticket_id": "T-INNER",
            "model_calls": 0, "last_order": None, "tool_outcomes": [],
        }, config={"recursion_limit": 10, "configurable": {"billing_model": mock_billing_model}}, stream_mode="updates"))
        assert [list(update)[0] for update in updates] == [
            "billing_agent_node", "billing_tools", "billing_agent_node", "billing_tools", "billing_agent_node"]
        for update in [updates[1], updates[3]]:
            message = update["billing_tools"]["messages"][0]
            assert isinstance(message, ToolMessage)
            assert message.tool_call_id in ["call-1", "call-2"]
        assert updates[-1]["billing_agent_node"]["status"] == "ANSWERED"
        assert updates[-1]["billing_agent_node"]["model_calls"] == 2
        assert orders["O-1001"]["refunded_paise"] == 250000
        assert mock_billing_model.bind_tools.return_value.invoke.call_count == 2

    mock_billing_model.bind_tools.return_value.invoke.side_effect = [
        tool_reply("get_order", {"order_id": "O-1001"}, "lookup-1"),
        AIMessage(content="Here are the order details."),
    ]
    with patch.dict(orders, fresh_store(), clear=True):
        result = billing_workflow.invoke({
            "messages": [HumanMessage(content="Show order O-1001.")],
            "customer_id": "C-001", "ticket_id": "T-LOOKUP",
            "model_calls": 0, "last_order": None, "tool_outcomes": [],
        }, config={"recursion_limit": 10, "configurable": {"billing_model": mock_billing_model}})
        assert result["model_calls"] == 2
        assert result["status"] == "ANSWERED"
        assert "No refund was issued" in result["response"]
