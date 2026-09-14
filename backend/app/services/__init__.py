"""Domain operations shared by more than one entry point.

A route handler is one caller of the domain; the chat assistant's tool
execution (specs/chatbot/design.md §4) is another, and Phase 5's rule is that
it "calls the same service-layer function directly — never a second copy of
that logic". That is what this package is for: the operation lives here, and
both the HTTP route and the tool call it.

It is deliberately *not* a layer every route now has to route through. Reads
that are a query plus a response model — the list and detail endpoints — stay
where they are; a function is extracted here when a second caller appears, not
in anticipation of one.
"""
