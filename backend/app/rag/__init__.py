"""
The question interface (FR-2.11 to FR-2.16).

Three parts, kept apart because the briefing's central rule depends on the
separation:

    queries.py    numbers. Every figure an answer contains comes from one of
                  these, executed against the database.
    documents.py  meanings. Definitions retrieved from the six reference
                  documents. Never a number.
    engine.py     routing and phrasing, and the rule that a question which
                  matches neither is answered with "I do not have that
                  information" rather than with a guess.
"""
