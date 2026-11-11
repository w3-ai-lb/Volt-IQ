"""
One place that knows how this business writes an amount.

WHY THIS EXISTS
---------------
The currency was wrong in eleven separate places and each one had its own copy
of the format string: the chatbot's replies, the alert messages, the risk
summary, the PDF receipt, the PDF bill, the report builder, the admin activity
feed. All of them wrote `f"${value:,.2f}"`.

Every row of the provider's data says otherwise. All 5,400 invoices, all 5,229
payments and all 18 tariffs carry `currency = 'LBP'`. A receipt handed to a
customer that reads $2,900 where the invoice says 2,900,000 LBP is wrong by a
factor of about a thousand, and a PDF is the one artefact that leaves the
building and cannot be corrected afterwards.

Scattered format strings are how that happened, and fixing eleven of them
without giving them somewhere to live is how it would happen again. So there is
one function, and `settings.CURRENCY` is the single fact behind it.

NO DECIMAL PLACES
-----------------
The smallest note in circulation is 1,000 LBP. Two decimals on a nine-digit
figure are noise, and on a bill they invite the reader to think the provider
bills to the piastre. Other currencies keep two, because they mean something
there.
"""

from __future__ import annotations

from app.config import settings

# Currencies whose smallest circulating unit makes decimal places meaningless.
_NO_SUBUNIT = frozenset({"LBP", "JPY", "KRW", "IQD", "IRR", "SYP", "VND"})


def money(amount: float | None, currency: str | None = None) -> str:
    """
    An amount as this provider writes it: `16,301,139 LBP`.

    The code goes after the number rather than a symbol in front, because LBP
    has no widely-recognised symbol and because it matches what the database
    stores in its `currency` column, a figure on a screen and a figure in a
    query then read the same.
    """
    value = float(amount or 0.0)
    code = (currency or settings.CURRENCY or "LBP").upper()
    if code in _NO_SUBUNIT:
        return f"{value:,.0f} {code}"
    return f"{value:,.2f} {code}"
