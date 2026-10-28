from __future__ import annotations

import re
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import COURSE


def normalize(text: str) -> str:
    return re.sub(r"[\u064b-\u065f\u0640]", "", text.lower()).translate(str.maketrans("أإآى", "اااي"))


@lru_cache(maxsize=1)
def documents() -> tuple[dict, ...]:
    docs = []
    for path in sorted((COURSE / "labs/data/policies").glob("*.md")):
        raw = path.read_text()
        head, body = raw[3:].split("---", 1)
        meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
        # Entire bilingual policies fit within a bounded result; preserve exact source citations.
        docs.append({"policy_id": meta["id"], "title": meta["title"], "text": body.strip()})
    return tuple(docs)


@lru_cache(maxsize=1)
def index():
    texts = [normalize(d["title"] + " " + d["text"]) for d in documents()]
    words = TfidfVectorizer(ngram_range=(1, 2))
    chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    return words, words.fit_transform(texts), chars, chars.fit_transform(texts)


def search(query: str, configuration: str = "B") -> dict:
    words, word_matrix, chars, char_matrix = index()
    q = normalize(query)
    word_scores = cosine_similarity(words.transform([q]), word_matrix)[0]
    scores = word_scores
    if configuration == "B":
        char_scores = cosine_similarity(chars.transform([q]), char_matrix)[0]
        scores = .55 * word_scores + .45 * char_scores
    ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:3]
    hits = [dict(documents()[i], score=round(float(scores[i]), 4)) for i in ranked if scores[i] > 0]
    return {"ok": True, "data": hits, "untrusted_source": True}
