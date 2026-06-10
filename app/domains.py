"""Domain packs — swappable per document type. The engine stays fixed."""

from functools import lru_cache
from pathlib import Path

import yaml

DOMAINS_DIR = Path(__file__).resolve().parent.parent / "domains"


@lru_cache
def _load_all() -> dict[str, dict]:
    packs: dict[str, dict] = {}
    if not DOMAINS_DIR.exists():
        return packs
    for path in DOMAINS_DIR.glob("*.yaml"):
        with path.open(encoding="utf-8") as f:
            pack = yaml.safe_load(f) or {}
        packs[path.stem] = pack
    return packs


def list_domains() -> list[str]:
    return sorted(_load_all().keys())


def get_domain(name: str) -> dict:
    """Return a domain pack, falling back to a generic one if unknown."""
    packs = _load_all()
    if name in packs:
        return packs[name]
    return packs.get(
        "generic",
        {
            "name": "Generic",
            "description": "Any policy, contract, or terms document.",
            "watch_for": [],
            "typical_terms": [],
        },
    )
