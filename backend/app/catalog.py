"""Agent-readable product catalog (Module 1).

Pinecone-backed RAG with a deterministic keyword fallback so the demo never
dies on stage if the network does. Retrieval returns structured CartLine-ready
dicts, not prose — the agent must not have to parse text to know a price.
"""
from __future__ import annotations
import json, os, re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_settings

CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "catalog.json"


@lru_cache
def load_catalog() -> list[dict[str, Any]]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def by_sku() -> dict[str, dict]:
    return {p["sku"]: p for p in load_catalog()}


def _doc_text(p: dict) -> str:
    return (f"{p['name']}. Category: {p['category']}. {p.get('description','')} "
            f"Tags: {', '.join(p.get('tags', []))}. Price: Rs {p['price_paise']/100:.0f}.")


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------
def _embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    s = get_settings()
    kwargs = {"api_key": s.openai_api_key}
    if s.openai_base_url:
        kwargs["base_url"] = s.openai_base_url
    client = OpenAI(**kwargs)
    resp = client.embeddings.create(model=s.openai_embed_model, input=texts)
    return [d.embedding for d in resp.data]


def _pinecone_index():
    import time
    from pinecone import Pinecone, ServerlessSpec
    s = get_settings()
    pc = Pinecone(api_key=s.pinecone_api_key)
    existing = {getattr(i, "name", i["name"] if isinstance(i, dict) else str(i)) for i in pc.list_indexes()}
    if s.pinecone_index not in existing:
        pc.create_index(
            name=s.pinecone_index, dimension=1536, metric="cosine",
            spec=ServerlessSpec(cloud=s.pinecone_cloud, region=s.pinecone_region),
        )
        while not pc.describe_index(s.pinecone_index).status.get("ready", False):
            time.sleep(1)
    return pc.Index(s.pinecone_index)


def seed_pinecone(batch: int = 64) -> int:
    """Embed the catalog and upsert into Pinecone. Run once: `python -m app.catalog`."""
    products = load_catalog()
    index = _pinecone_index()
    n = 0
    for i in range(0, len(products), batch):
        chunk = products[i:i + batch]
        vectors = _embed([_doc_text(p) for p in chunk])
        index.upsert(vectors=[
            {"id": p["sku"], "values": v,
             "metadata": {"name": p["name"], "category": p["category"],
                          "price_paise": p["price_paise"], "tags": p.get("tags", [])}}
            for p, v in zip(chunk, vectors)
        ])
        n += len(chunk)
    return n


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------
def _keyword_search(query: str, top_k: int) -> list[dict]:
    """Offline fallback — BM25-ish token overlap. Deterministic, demo-safe."""
    tokens = {t for t in re.findall(r"[a-z]+", query.lower()) if len(t) > 2}
    scored = []
    for p in load_catalog():
        hay = _doc_text(p).lower()
        score = sum(1 for t in tokens if t in hay)
        score += sum(1 for t in tokens if t in p["name"].lower()) * 2
        score += sum(2 for t in tokens for tag in p.get("tags", []) if t == tag.lower())
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1]["price_paise"]))
    return [p for _, p in scored[:top_k]]


def search(query: str, top_k: int = 6) -> list[dict]:
    """Returns catalog rows ready to become CartLines."""
    s = get_settings()
    if (
        s.catalog_retrieval_mode == "pinecone"
        and s.pinecone_api_key
        and s.openai_api_key
    ):
        try:
            vec = _embed([query])[0]
            res = _pinecone_index().query(vector=vec, top_k=top_k, include_metadata=True)
            skus = [m["id"] for m in res.get("matches", [])]
            rows = [by_sku()[sku] for sku in skus if sku in by_sku()]
            if rows:
                return rows
        except Exception as exc:  # pragma: no cover - network path
            print(f"[catalog] Pinecone query failed, using keyword fallback: {exc}")
    return _keyword_search(query, top_k)


def cross_sell(skus: list[str], limit: int = 3) -> list[dict]:
    """Organic in-chat cross-sell: same tags, not already in the cart."""
    have = set(skus)
    tags: set[str] = set()
    for sku in skus:
        tags |= set(by_sku().get(sku, {}).get("tags", []))
    out = [p for p in load_catalog()
           if p["sku"] not in have and tags & set(p.get("tags", []))]
    out.sort(key=lambda p: p["price_paise"])
    return out[:limit]


if __name__ == "__main__":  # pragma: no cover
    print(f"Seeded {seed_pinecone()} products into Pinecone "
          f"index '{get_settings().pinecone_index}'.")
