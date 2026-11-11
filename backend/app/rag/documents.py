"""
The explanatory half of the question interface (FR-2.13).

WHAT THIS RETRIEVES, AND WHAT IT MUST NOT
-----------------------------------------
Definitions only. What technical loss is, what phase imbalance means, how the
tariff works, what an alarm code is. The briefing is blunt about the boundary:

    "Classic RAG searches text documents. Your data is numbers in database
     tables. If you embed rows as text and search them, the answers will be
     wrong, and you will not know they are wrong."

So no row of the database is ever indexed here. A question about a quantity
goes to SQL (app/rag/queries.py); a question about a meaning comes here; and a
question that needs both gets a number from SQL and its explanation from here,
never a number from here.

WHY TF-IDF AND NOT EMBEDDINGS
-----------------------------
Two honest reasons rather than one.

The corpus is six documents of definitions, a few hundred lines, written in the
vocabulary the questions will use: somebody asking about phase imbalance says
"phase imbalance". Sparse lexical retrieval is well suited to that, and it has
a property dense retrieval does not: you can see exactly which words matched,
which matters when the whole system is built on being able to show why it said
what it said.

The second reason is a constraint and should be recorded as one: a sentence
embedding model has to be downloaded, and the environment this was developed in
cannot reach a model host. If dense retrieval is wanted later, the interface
below is the only thing that has to change; `retrieve()` returns passages and
nothing above it knows how they were found.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Defaults. The values in force come from config/chatbot.toml ([ask_the_data]).
DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "rag_documents"

# Below this the match is coincidence rather than relevance, and an answer
# built on it would be a confident irrelevance.
MIN_SCORE = 0.08


@dataclass(frozen=True)
class Passage:
    """One section of one document, with enough context to cite it."""

    document: str          # the file it came from
    heading: str           # the ## heading, or the title for a preamble
    text: str
    score: float = 0.0

    @property
    def citation(self) -> str:
        return f"{self.document}, {self.heading}"


def _split_sections(path: Path) -> list[Passage]:
    """
    One passage per heading.

    Splitting on headings rather than on a fixed character count keeps a
    definition whole. A glossary entry cut in half retrieves the half without
    the meaning in it.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = next((line.lstrip("# ").strip() for line in lines if line.startswith("# ")), path.stem)
    passages: list[Passage] = []
    heading = title
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            passages.append(Passage(document=path.name, heading=heading, text=body))

    for line in lines:
        if line.startswith("## "):
            flush()
            heading = line.lstrip("# ").strip()
            buffer = []
        elif line.startswith("# "):
            continue
        else:
            buffer.append(line)
    flush()

    # A glossary is a list of definitions under one heading, and retrieving the
    # whole of it to answer "what is rollover" buries the answer. Split it per
    # term instead: a term is a line that starts at column zero and is followed
    # by indented continuation lines.
    if "glossary" in path.name.lower():
        entries: list[Passage] = []
        current: list[str] = []
        term = ""
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            if not line.startswith(" ") and line.strip():
                if term and current:
                    entries.append(Passage(path.name, term, " ".join(x.strip() for x in current)))
                parts = re.split(r"\s{2,}", line.strip(), maxsplit=1)
                term = parts[0].strip()
                current = [parts[1]] if len(parts) > 1 else []
            else:
                current.append(line)
        if term and current:
            entries.append(Passage(path.name, term, " ".join(x.strip() for x in current)))
        if entries:
            return entries

    return passages


class DocumentIndex:
    """TF-IDF over the reference documents. Built once, held in memory."""

    def __init__(self, directory: Path | None = None) -> None:
        from app.core import chatbot_config

        config = chatbot_config.get().ask
        self.directory = directory or config.documents_dir
        self.min_score = config.min_relevance
        self.passages: list[Passage] = []
        self._matrix = None
        self._vectorizer = None
        self._build()

    def _build(self) -> None:
        if not self.directory.is_dir():
            logger.warning("No reference documents at %s; definitions unavailable", self.directory)
            return

        for path in sorted(self.directory.glob("*.md")):
            self.passages.extend(_split_sections(path))

        if not self.passages:
            return

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            # Bigrams as well as single words: "phase imbalance" and "technical
            # loss" are the terms of art here, and either word alone points
            # somewhere else.
            self._vectorizer = TfidfVectorizer(
                ngram_range=(1, 2), sublinear_tf=True, stop_words="english"
            )
            corpus = [f"{p.heading}. {p.heading}. {p.text}" for p in self.passages]
            # The heading is repeated deliberately: it is the most reliable
            # description of what the passage is about.
            self._matrix = self._vectorizer.fit_transform(corpus)
            logger.info("Reference documents indexed: %d passages", len(self.passages))
        except Exception:
            logger.warning("Could not build the document index", exc_info=True)
            self._vectorizer = None

    def retrieve(self, question: str, k: int = 3) -> list[Passage]:
        """The k most relevant passages, or nothing if none is relevant."""
        if not self.passages or self._vectorizer is None or self._matrix is None:
            return []

        from sklearn.metrics.pairwise import linear_kernel

        vector = self._vectorizer.transform([question])
        scores = linear_kernel(vector, self._matrix).ravel()

        ranked = sorted(
            (
                Passage(p.document, p.heading, p.text, float(s))
                for p, s in zip(self.passages, scores)
                if s >= self.min_score
            ),
            key=lambda p: p.score,
            reverse=True,
        )
        return ranked[:k]


_index: DocumentIndex | None = None


def index() -> DocumentIndex:
    global _index
    if _index is None:
        _index = DocumentIndex()
    return _index
