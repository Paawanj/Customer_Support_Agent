from triage_graph import workflow

examples = [
    "I cannot log in. How do I reset my NovaCart password?",
    "My checkout page shows an error before payment.",
    "Where can I find the tracking link for a dispatched order?",
    "Can NovaCart install a custom warehouse automation plugin for me?",
]

for number, ticket in enumerate(examples, start=1):
    result = workflow.invoke({"ticket_id": f"T-TECH-{number}", "ticket": ticket, "customer_id": "C-001"})
    print("Ticket:", ticket)
    print("Route:", result["route"], "Status:", result["status"])
    print("Reply:", result["response"])
    print("Retrieved:", result.get("retrieved_source_ids", []))
    print("Citations:", result.get("citations", []))
    print("Review reason:", result.get("escalation_reason", ""))
    print()
