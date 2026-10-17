from classifier import build_classifier_chain, classify_ticket


tickets = [
    "I was charged twice for my subscription.",
    "Checkout fails with error E104 whenever I try to pay.",
    "What are your support opening hours?",
    "Something went wrong, but I am not sure what happened.",
]

chain = build_classifier_chain()
for ticket in tickets:
    result = classify_ticket(ticket, chain)
    print(ticket)
    print(result.model_dump())
