from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from fastembed import TextEmbedding

from app.core.config import settings


_client: QdrantClient | None = None
_embedder: TextEmbedding | None = None
_collection_ready = False


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url, timeout=5.0)
    return _client


def _get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name=settings.embedding_model)
    return _embedder


def _embed_one(text: str) -> list[float]:
    emb = next(iter(_get_embedder().embed([text or ""])))
    return [float(x) for x in emb.tolist()]


def _ensure_collection() -> None:
    global _collection_ready
    if _collection_ready:
        return
    client = _get_client()
    collection = settings.qdrant_collection
    if not client.collection_exists(collection):
        vector_size = len(_embed_one("probe"))
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
    _collection_ready = True


def _product_to_point(product: Any) -> models.PointStruct:
    text = f"{product.brand or ''} {product.name or ''} {product.sku or ''}".strip()
    return models.PointStruct(
        id=product.id,
        vector=_embed_one(text),
        payload={
            "product_id": product.id,
            "sku": product.sku,
            "brand": product.brand,
            "name": product.name,
            "is_active": bool(getattr(product, "is_active", True)),
        },
    )


def upsert_catalog_products(products: list[Any]) -> int:
    """Upsert product vectors for the given catalog rows."""
    _ensure_collection()
    points: list[models.PointStruct] = []
    for product in products:
        points.append(_product_to_point(product))
    if points:
        _get_client().upsert(collection_name=settings.qdrant_collection, points=points)
    return len(points)


def delete_catalog_products(product_ids: list[str]) -> int:
    """Delete product vectors by product IDs."""
    _ensure_collection()
    clean_ids = [x for x in product_ids if x]
    if not clean_ids:
        return 0
    _get_client().delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.PointIdsList(points=clean_ids),
    )
    return len(clean_ids)


def ensure_catalog_index(products: list[Any]) -> bool:
    """Build index once if collection is empty."""
    _ensure_collection()
    count_result = _get_client().count(
        collection_name=settings.qdrant_collection,
        count_filter=None,
        exact=False,
    )
    if int(getattr(count_result, "count", 0)) > 0:
        return False
    upsert_catalog_products(products)
    return True


def reindex_catalog(products: list[Any]) -> int:
    """Recreate collection from scratch and reindex products."""
    global _collection_ready
    client = _get_client()
    collection = settings.qdrant_collection
    if client.collection_exists(collection):
        client.delete_collection(collection_name=collection)
    _collection_ready = False
    _ensure_collection()
    return upsert_catalog_products(products)


def sync_catalog_index(products: list[Any]) -> None:
    """Backward-compatible alias for full upsert."""
    upsert_catalog_products(products)


def vector_search(query: str, top_k: int = 25) -> dict[str, float]:
    """Returns map: product_id -> cosine score [0..1]."""
    _ensure_collection()
    result = _get_client().search(
        collection_name=settings.qdrant_collection,
        query_vector=_embed_one(query),
        limit=max(1, min(top_k, 200)),
        with_payload=True,
    )
    out: dict[str, float] = {}
    for hit in result:
        product_id = None
        if isinstance(hit.payload, dict):
            product_id = hit.payload.get("product_id")
        if not product_id:
            product_id = str(hit.id)
        out[str(product_id)] = float(hit.score or 0.0)
    return out
