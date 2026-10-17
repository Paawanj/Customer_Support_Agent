from triage_graph import workflow
from mock_store import orders, refunds


tickets = [
    ("T-LOOKUP", "Show payment details for order O-1002."),
    ("T-REFUND", "Please refund ₹2,500 for order O-1001."),
    ("T-REFUND", "Please refund ₹2,500 for order O-1001."),
    ("T-APPROVAL", "Please refund ₹7,500 for order O-1002."),
    ("T-OTHER-OWNER", "Please refund ₹3,000 for order O-2001."),
]

for ticket_id, message in tickets:
    result = workflow.invoke({"ticket_id": ticket_id, "ticket": message, "customer_id": "C-001"})
    print(ticket_id, result["route"], result["status"])
    print(result["response"])
    print(result.get("escalation_reason", ""))
    print(result.get("tool_outcomes", []))

print("O-1001 refunded paise:", orders["O-1001"]["refunded_paise"])
print("Refund records:", refunds)
