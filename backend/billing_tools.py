from langchain_core.tools import tool
from pydantic import BaseModel, Field
from mock_store import orders, refunds


@tool
def get_order(order_id: str, customer_id: str) -> dict:
    """Look up an owned order. Python supplies the current customer_id."""
    order = orders.get(order_id)
    if order is None or order["customer_id"] != customer_id:
        return {"status": "REVIEW_REQUIRED", "reason": "order_unavailable"}
    return {
        "status": "FOUND",
        "currency": "INR",
        "order_id": order_id,
        "paid_paise": order["paid_paise"],
        "refunded_paise": order["refunded_paise"],
        "eligible": order["eligible"],
    }



class RefundInput(BaseModel):
    order_id: str = Field(min_length=1, strict=True)
    amount_paise: int = Field(gt=0, strict=True, description="Refund in paise: ₹2,500 means 250000.")
    customer_id: str = Field(min_length=1, strict=True)
    ticket_id: str = Field(min_length=1, strict=True)

@tool(args_schema=RefundInput)
def issue_refund(order_id: str, amount_paise: int, customer_id: str, ticket_id: str) -> dict:
    """Simulate an eligible owned-order refund up to ₹5,000 total. Python supplies customer/ticket IDs."""
    order = orders.get(order_id)
    if order is None or order["customer_id"] != customer_id:
        return {"status": "REVIEW_REQUIRED", "reason": "order_unavailable"}

    operation_key = (customer_id, ticket_id)
    previous = refunds.get(operation_key)
    if previous is not None:
        if previous["order_id"] != order_id or previous["amount_paise"] != amount_paise:
            return {"status": "REVIEW_REQUIRED", "reason": "refund_request_changed"}
        return {"status": "ALREADY_REFUNDED", **previous}

    if not order["eligible"]:
        return {"status": "REVIEW_REQUIRED", "reason": "refund_ineligible"}
    if amount_paise > order["paid_paise"] - order["refunded_paise"]:
        return {"status": "REVIEW_REQUIRED", "reason": "exceeds_remaining_payment"}
    if amount_paise > 500000 or order["refunded_paise"] + amount_paise > 500000:
        return {"status": "REVIEW_REQUIRED", "reason": "manager_approval_required"}

    order["refunded_paise"] += amount_paise
    record = {"currency": "INR", "order_id": order_id, "amount_paise": amount_paise}
    refunds[operation_key] = record
    return {"status": "REFUNDED", **record}


billing_tools = [get_order, issue_refund]