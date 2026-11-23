"""
AI-Powered Energy Analytics and Customer Engagement Platform, Backend.

NXTTRN x MUBS Industry Internship.
"""

import sys

# The codebase uses `datetime.UTC` (Python 3.11+) and PEP 604 unions
# evaluated at runtime. Without this guard, an older interpreter fails with a
# confusing ImportError deep inside a module instead of saying what is wrong.
if sys.version_info < (3, 11):
    raise RuntimeError(
        f"Python 3.11 or newer is required, you are running "
        f"{sys.version_info.major}.{sys.version_info.minor}.\n"
        f"Download a newer version from https://www.python.org/downloads/"
    )
