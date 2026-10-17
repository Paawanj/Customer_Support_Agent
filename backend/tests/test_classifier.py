from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from classifier import classify_ticket
from schemas import TicketClassification


def test_schema():
    for category in ["billing", "tech", "general"]:
        result = TicketClassification(category=category, confidence=0.9, reasoning="Example ticket.")
        assert result.category == category

    invalid_cases = [
        {"category": "sales"},
        {"confidence": -0.1},
        {"confidence": 1.1},
        {"confidence": float("nan")},
        {"confidence": float("inf")},
        {"reasoning": ""},
        {"reasoning": "x" * 241},
    ]
    for updates in invalid_cases:
        data = {"category": "billing", "confidence": 0.9, "reasoning": "Example ticket."}
        data.update(updates)
        with pytest.raises(ValidationError):
            TicketClassification(**data)

    for field in ["category", "confidence", "reasoning"]:
        data = {"category": "billing", "confidence": 0.9, "reasoning": "Example ticket."}
        del data[field]
        with pytest.raises(ValidationError):
            TicketClassification(**data)


def test_confidence_rule():
    for confidence, category in [(0, "general"), (0.59, "general"), (0.6, "billing"), (1, "billing")]:
        chain = Mock()
        chain.invoke.return_value = TicketClassification(
            category="billing", confidence=confidence, reasoning="Duplicate charge."
        )
        result = classify_ticket("Please check my charge.", chain)
        assert result.category == category
        assert result.confidence == confidence


def test_empty_ticket_does_not_call_model():
    for ticket in [None, 123, "", "   "]:
        chain = Mock()
        with pytest.raises(ValueError):
            classify_ticket(ticket, chain)
        chain.invoke.assert_not_called()


def test_missing_output():
    chain = Mock()
    chain.invoke.return_value = None
    with pytest.raises(ValueError):
        classify_ticket("Please check my charge.", chain)


def test_provider_failure():
    chain = Mock()
    chain.invoke.side_effect = RuntimeError("Provider unavailable.")
    with pytest.raises(RuntimeError):
        classify_ticket("Please check my charge.", chain)
