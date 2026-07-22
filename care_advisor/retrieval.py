"""Pure-Python TF-IDF retrieval over the knowledge/ markdown knowledge base.

No numpy/sklearn/vector DB — the knowledge base is small and curated, so
dict-based term vectors and cosine similarity are sufficient, fast, and easy
to unit test deterministically.

DEMO NOTE: this is the "Retriever" box in diagrams/care_advisor_flow.mmd.
It's the first stage of the RAG pipeline — it never talks to Claude, it
just ranks knowledge/*.md chunks against a query using classic TF-IDF math.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# knowledge/ lives one level up from this file, at the project root.
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

# Matches runs of letters/digits -- used to split raw text into words.
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Common words that carry no topical signal ("the", "and", ...). Removing
# them keeps the TF-IDF vectors focused on words that actually distinguish
# one chunk from another (e.g. "grooming" vs. "medication").
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
    """One retrievable unit of knowledge: a single '## heading' section of a
    knowledge/*.md file. `id` (e.g. "S7") is the citation marker the model
    is required to use when it draws on this chunk's text.
    """
    id: str
    doc_title: str
    source_file: str
    heading: str
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    """A Chunk plus how well it matched a specific query (cosine similarity, 0-1)."""
    chunk: Chunk
    score: float


def _parse_markdown_file(path: Path) -> list:
    """Split a markdown file into (heading, text) sections on '## ' boundaries.

    Each knowledge/*.md file is one document (e.g. "Grooming Frequency") made
    of a few '## ' sub-sections (e.g. "Bathing", "Nail trims"). Each
    sub-section becomes one Chunk below, so a query can match a specific
    paragraph instead of an entire document.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # The doc title comes from the top-level '# Heading' line, if present,
    # else falls back to a title-cased version of the filename.
    doc_title = path.stem.replace("_", " ").title()
    if lines and lines[0].startswith("# "):
        doc_title = lines[0][2:].strip()
        lines = lines[1:]

    sections = []
    current_heading = None
    current_lines = []

    def flush():
        # Save the section we've been accumulating once we hit the next
        # '## ' heading (or the end of the file).
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
    """Loads knowledge/*.md, chunks by section, and answers TF-IDF queries.

    This is built once (see app.py's `get_advisor()`, which caches it across
    Streamlit reruns) and then queried many times via `retrieve()`.
    """

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else KNOWLEDGE_DIR
        self.chunks: list = []
        self._doc_freq: dict = {}
        self._chunk_vectors: dict = {}
        self._load()

    def _load(self):
        """Read every knowledge/*.md file and turn it into a flat list of Chunks."""
        self.chunks = []
        chunk_index = 0
        # sorted() makes chunk ids stable across runs -- same file always
        # gets the same "S#" id, which matters for the citation contract.
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
        """Build the TF-IDF vectors for every chunk, once, up front.

        TF-IDF = "term frequency x inverse document frequency": a word that
        appears often in one chunk but rarely across the whole knowledge base
        (e.g. "bloat") gets a high weight, while a word that appears
        everywhere (e.g. "pet") gets a low weight, since it doesn't help
        distinguish one chunk from another.
        """
        doc_freq = {}              # how many chunks each word appears in
        term_freqs_by_chunk = {}   # per-chunk word counts

        for chunk in self.chunks:
            tokens = tokenize(f"{chunk.heading} {chunk.text}")
            tf = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            term_freqs_by_chunk[chunk.id] = tf
            for term in tf:
                doc_freq[term] = doc_freq.get(term, 0) + 1

        # Standard smoothed IDF formula: log((N+1)/(df+1)) + 1, so a word
        # that appears in every chunk still gets a small positive weight
        # instead of zero.
        n_docs = max(len(self.chunks), 1)
        idf = {
            term: math.log((n_docs + 1) / (df + 1)) + 1.0
            for term, df in doc_freq.items()
        }

        # Each chunk's vector: for every word it contains, (count in chunk) * idf.
        chunk_vectors = {}
        for chunk_id, tf in term_freqs_by_chunk.items():
            vector = {term: count * idf[term] for term, count in tf.items()}
            chunk_vectors[chunk_id] = vector

        self._doc_freq = doc_freq
        self._idf = idf
        self._chunk_vectors = chunk_vectors

    def _query_vector(self, query: str) -> dict:
        """Build the same kind of TF-IDF vector for an incoming query string,
        reusing the IDF weights already computed from the knowledge base."""
        tokens = tokenize(query)
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        return {
            term: count * self._idf.get(term, 0.0)
            for term, count in tf.items()
            if term in self._idf   # words never seen in the knowledge base contribute nothing
        }

    @staticmethod
    def _cosine_similarity(vec_a: dict, vec_b: dict) -> float:
        """Standard cosine similarity between two sparse (dict-based) vectors:
        dot product divided by the product of their magnitudes. Returns a
        value in [0, 1] for these non-negative TF-IDF vectors — 0 means no
        shared vocabulary at all, 1 means identical.
        """
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

        # Score every chunk against the query, keep only real matches (score > 0).
        scored = []
        for chunk in self.chunks:
            score = self._cosine_similarity(query_vector, self._chunk_vectors[chunk.id])
            if score > 0.0:
                scored.append(RetrievedChunk(chunk=chunk, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    def get_by_id(self, chunk_id: str) -> Optional[Chunk]:
        """Look up a chunk by its citation id (e.g. "S7") -- used when
        verifying that a model's citation actually refers to a real source."""
        for chunk in self.chunks:
            if chunk.id == chunk_id:
                return chunk
        return None
