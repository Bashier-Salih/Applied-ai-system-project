"""Pure-Python TF-IDF retrieval over the knowledge/ markdown knowledge base.

No numpy/sklearn/vector DB — the knowledge base is small and curated, so
dict-based term vectors and cosine similarity are sufficient, fast, and easy
to unit test deterministically.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "being", "it", "its", "this",
    "that", "these", "those", "as", "at", "by", "with", "from", "into",
    "than", "then", "so", "not", "no", "can", "will", "should", "would",
    "if", "when", "which", "what", "how", "do", "does", "did",
}


def tokenize(text: str) -> list:
    """Lowercase, strip punctuation, drop stopwords."""
    words = _TOKEN_RE.findall(text.lower())
    return [w for w in words if w not in _STOPWORDS]


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_title: str
    source_file: str
    heading: str
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float


def _parse_markdown_file(path: Path) -> list:
    """Split a markdown file into (heading, text) sections on '## ' boundaries."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    doc_title = path.stem.replace("_", " ").title()
    if lines and lines[0].startswith("# "):
        doc_title = lines[0][2:].strip()
        lines = lines[1:]

    sections = []
    current_heading = None
    current_lines = []

    def flush():
        if current_heading is not None:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append((current_heading, body))

    for line in lines:
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()

    return doc_title, sections


class DocStore:
    """Loads knowledge/*.md, chunks by section, and answers TF-IDF queries."""

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else KNOWLEDGE_DIR
        self.chunks: list = []
        self._doc_freq: dict = {}
        self._chunk_vectors: dict = {}
        self._load()

    def _load(self):
        self.chunks = []
        chunk_index = 0
        for path in sorted(self.knowledge_dir.glob("*.md")):
            doc_title, sections = _parse_markdown_file(path)
            for heading, body in sections:
                chunk_index += 1
                self.chunks.append(
                    Chunk(
                        id=f"S{chunk_index}",
                        doc_title=doc_title,
                        source_file=path.name,
                        heading=heading,
                        text=body,
                    )
                )
        self._build_index()

    def _build_index(self):
        doc_freq = {}
        term_freqs_by_chunk = {}

        for chunk in self.chunks:
            tokens = tokenize(f"{chunk.heading} {chunk.text}")
            tf = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            term_freqs_by_chunk[chunk.id] = tf
            for term in tf:
                doc_freq[term] = doc_freq.get(term, 0) + 1

        n_docs = max(len(self.chunks), 1)
        idf = {
            term: math.log((n_docs + 1) / (df + 1)) + 1.0
            for term, df in doc_freq.items()
        }

        chunk_vectors = {}
        for chunk_id, tf in term_freqs_by_chunk.items():
            vector = {term: count * idf[term] for term, count in tf.items()}
            chunk_vectors[chunk_id] = vector

        self._doc_freq = doc_freq
        self._idf = idf
        self._chunk_vectors = chunk_vectors

    def _query_vector(self, query: str) -> dict:
        tokens = tokenize(query)
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        return {
            term: count * self._idf.get(term, 0.0)
            for term, count in tf.items()
            if term in self._idf
        }

    @staticmethod
    def _cosine_similarity(vec_a: dict, vec_b: dict) -> float:
        common_terms = set(vec_a) & set(vec_b)
        if not common_terms:
            return 0.0
        dot = sum(vec_a[t] * vec_b[t] for t in common_terms)
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def retrieve(self, query: str, k: int = 3) -> list:
        """Return the top-k chunks most relevant to `query`, best first.

        Chunks with zero similarity (no shared vocabulary with the query)
        are excluded rather than padded in, so callers can tell when the
        knowledge base genuinely has nothing relevant.
        """
        query_vector = self._query_vector(query)
        if not query_vector:
            return []

        scored = []
        for chunk in self.chunks:
            score = self._cosine_similarity(query_vector, self._chunk_vectors[chunk.id])
            if score > 0.0:
                scored.append(RetrievedChunk(chunk=chunk, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    def get_by_id(self, chunk_id: str) -> Optional[Chunk]:
        for chunk in self.chunks:
            if chunk.id == chunk_id:
                return chunk
        return None
