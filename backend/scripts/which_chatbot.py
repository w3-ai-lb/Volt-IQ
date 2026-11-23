# -*- coding: utf-8 -*-
"""
Print which chatbot file is on disk, and when it was written.

A separate file rather than a `python -c "..."` one-liner in the batch script,
which is how the first version did it and why it failed: the batch expanded
%CD% into the command string, the path contained
C:\\Users\\... , and Python read \\U as the start of a unicode escape. The
script died with a SyntaxError about a truncated \\UXXXXXXXX escape and printed
nothing about the chatbot at all.

Nothing that looks at a Windows path should be built by string-pasting it into
another language.

Run:  python -m scripts.which_chatbot
"""

from __future__ import annotations

import datetime
import io
import pathlib


def main() -> int:
    path = pathlib.Path("app/ai/chatbot.py").resolve()
    if not path.exists():
        print("    [X] app/ai/chatbot.py is not here.")
        print("        Looked in: %s" % pathlib.Path.cwd())
        return 1

    source = io.open(path, encoding="utf-8").read()
    # Two names that exist only in the version with Arabic in it.
    is_new = "_ARABIC_TEXT" in source and "capabilities" in source
    written = datetime.datetime.fromtimestamp(path.stat().st_mtime)

    print("    path    : %s" % path)
    print("    version : %s" % ("NEW, answers Arabic" if is_new else "OLD, English only"))
    print("    size    : %d characters" % len(source))
    print("    written : %s" % written.strftime("%d %B %Y at %H:%M"))
    if not is_new:
        print()
        print("    [X] This is the old file. The new chatbot.py has to be copied")
        print("        over the path printed above, and nowhere else.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
