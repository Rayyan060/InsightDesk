"""Product-version specifications for ``product_versions`` (Annex B).

Grammar (case-insensitive, terms separated by ``,`` or ``;``):

    all          every version
    3.x          any 3.* version
    4.2+         4.2 and later
    4.0-4.1      inclusive range (major.minor)
    4.3          exactly 4.3 (and patch releases 4.3.*)

Annex B's own examples are ``4.2+`` and ``3.x``. The others extend the same
notation for exact versions and closed ranges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.synthetic.scenarios import CURRENT_VERSION, PRODUCT_VERSIONS

# Versions CloudFlow has shipped (shared with the Phase 2 account data).
KNOWN_VERSIONS: tuple[str, ...] = tuple(sorted(PRODUCT_VERSIONS, key=lambda v: tuple(int(p) for p in v.split("."))))
CURRENT = CURRENT_VERSION

# Release dates (from the release notes RN-2025-11 ... RN-2026-09; 3.x predates the KB).
# A ticket cannot be on a version that had not shipped when it was resolved.
RELEASE_DATES: dict[str, str] = {
    "3.8": "2024-05-06",
    "3.9": "2024-11-04",
    "4.0": "2025-11-03",
    "4.1": "2026-02-02",
    "4.2": "2026-04-14",
    "4.3": "2026-09-15",
}

_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
_TERM_RE = re.compile(r"^(?:(all)|(\d+)\.x|(\d+\.\d+)\+|(\d+\.\d+)-(\d+\.\d+)|(\d+\.\d+(?:\.\d+)?))$", re.IGNORECASE)


def parse_version(value: str) -> tuple[int, int]:
    """'4.3' or '4.3.1' -> (4, 3). Patch releases share their minor's documentation."""
    value = value.strip()
    if not _VERSION_RE.fullmatch(value):
        raise ValueError(f"not a product version (expected N.N or N.N.N): {value!r}")
    major, minor = value.split(".")[:2]
    return int(major), int(minor)


@dataclass(frozen=True)
class VersionTerm:
    kind: str  # all | major | from | range | exact
    low: tuple[int, int] | None = None
    high: tuple[int, int] | None = None

    def covers(self, version: tuple[int, int]) -> bool:
        if self.kind == "all":
            return True
        if self.kind == "major":
            return version[0] == self.low[0]  # type: ignore[index]
        if self.kind == "from":
            return version >= self.low  # type: ignore[operator]
        if self.kind == "range":
            return self.low <= version <= self.high  # type: ignore[operator]
        return version == self.low


@dataclass(frozen=True)
class VersionSpec:
    raw: str
    terms: tuple[VersionTerm, ...]

    def covers(self, version: str) -> bool:
        parsed = parse_version(version)
        return any(term.covers(parsed) for term in self.terms)

    def covered_known_versions(self) -> list[str]:
        return [v for v in KNOWN_VERSIONS if self.covers(v)]


def parse_version_spec(raw: str) -> VersionSpec:
    if raw is None or not str(raw).strip():
        raise ValueError("product_versions must not be empty")
    terms = []
    for part in re.split(r"[;,]", str(raw)):
        part = part.strip()
        if not part:
            continue
        match = _TERM_RE.fullmatch(part)
        if not match:
            raise ValueError(f"invalid product_versions term {part!r} (use e.g. 4.2+, 3.x, 4.0-4.1, 4.3 or all)")
        if match.group(1):
            terms.append(VersionTerm("all"))
        elif match.group(2):
            terms.append(VersionTerm("major", (int(match.group(2)), 0)))
        elif match.group(3):
            terms.append(VersionTerm("from", parse_version(match.group(3))))
        elif match.group(4):
            low, high = parse_version(match.group(4)), parse_version(match.group(5))
            if low > high:
                raise ValueError(f"version range {part!r} is reversed")
            terms.append(VersionTerm("range", low, high))
        else:
            terms.append(VersionTerm("exact", parse_version(match.group(6))))
    if not terms:
        raise ValueError("product_versions must not be empty")
    return VersionSpec(raw=str(raw), terms=tuple(terms))
