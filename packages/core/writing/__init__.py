"""W16a — the writing surface's pure rules and gates.

Nothing here touches the database, the model or HTTP. `core.services.writing`
owns the SQL and the model call; this package owns the decisions that can be
tested without either, so each one has a test that states its own expected
value rather than deriving it from the function under test (CLAUDE.md §3 rule 5).
"""
