"""Embedding providers.

* ``SentenceTransformerEmbedder``: the production embedder (``EMBEDDING_MODEL``,
  default all-MiniLM-L6-v2), loaded once per process.
* ``HashingEmbedder``: a deterministic bag-of-words embedder with no model
  download. Used by tests, and as an explicit fallback (``--embedder hashing``)
  on machines without the model. It is lexical, not semantic.

The embedder name is stored on the Chroma collection, so queries always use the
same embedder that built the index.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

HASHING_NAME = "hashing-bow-512"
_TOKEN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i if in is it its me my of on or our so that the this to was "
    "what when where which who why will with you your we us they there their".split()
)


def tokens(text: str) -> list[str]:
    out = []
    for token in _TOKEN.findall(text.lower().replace(",", "")):
        if token in STOPWORDS:
            continue
        out.append(token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token)
    return out


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    model_name = HASHING_NAME

    def __init__(self, dims: int = 512) -> None:
        self.dims = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dims
            for token in tokens(text):
                vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dims] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


@lru_cache(maxsize=4)
def get_embedding_provider(model_name: str) -> EmbeddingProvider:
    if model_name == HASHING_NAME:
        return HashingEmbedder()
    return SentenceTransformerEmbedder(model_name)
