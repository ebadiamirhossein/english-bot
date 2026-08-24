"""The lexicon: tokenising, lemmatising and known-word coverage.

Everything in this package is **pure**. No module here opens a database
connection, imports ``psycopg`` or holds a SQL string — every query against
``lexemes`` and ``user_lexemes`` lives in ``core.services.lexicon``. That split
is what lets ``coverage.compute_coverage`` be tested without a database and
keeps ``tests/test_core_boundary.py::test_no_sql_outside_services`` unexempted
(CLAUDE.md §2). ``test_lexicon_package_is_pure`` asserts it rather than
trusting it.

``normalize`` is the single entry point for turning text into lemmas. The seed
builder, every ledger write and every coverage computation call the same
``tokenize``/``lemmatize`` — if two call sites lemmatised differently the
ledger would silently never match and coverage would read low forever, with
nothing failing.
"""
