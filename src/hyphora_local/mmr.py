"""MMR (Maximal Marginal Relevance) implementation for graph traversal."""

import sqlite3
import numpy as np
from typing import Optional
from dataclasses import dataclass
import sqlite_vec  # type: ignore[import-untyped]

from .config import HyphoraConfig
from .search import SearchResult
from .graph_walk import WalkStep, QueryScore, get_neighbors


@dataclass
class MMRCandidate:
    """Candidate node for MMR selection."""

    id: int
    title: str
    content: str
    embedding: np.ndarray
    similarity: float  # Cosine similarity to query
    max_redundancy: float = 0.0  # Max cosine to selected nodes
    depth: int = 0  # Hops from seed

    def mmr_score(self, lambda_mult: float) -> float:
        """Calculate MMR score: λ*sim - (1-λ)*redundancy"""
        return lambda_mult * self.similarity - (1 - lambda_mult) * self.max_redundancy


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between normalized vectors."""
    # Ensure vectors are normalized
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    vec1_norm = vec1 / norm1
    vec2_norm = vec2 / norm2

    return float(np.dot(vec1_norm, vec2_norm))


def get_embedding(config: HyphoraConfig, doc_id: int) -> Optional[np.ndarray]:
    """Retrieve embedding vector for a document."""
    conn = sqlite3.connect(config.db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)  # type: ignore[no-untyped-call]
    conn.enable_load_extension(False)

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT embedding FROM vault_vec WHERE id = ?", (doc_id,))
        row = cursor.fetchone()

        if row and row[0]:
            # Deserialize from sqlite-vec format (raw bytes to numpy array)
            return np.frombuffer(row[0], dtype=np.float32)
        return None
    finally:
        conn.close()


def get_embeddings_batch(
    config: HyphoraConfig, doc_ids: list[int]
) -> dict[int, np.ndarray]:
    """Retrieve embeddings for multiple documents efficiently."""
    if not doc_ids:
        return {}

    conn = sqlite3.connect(config.db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)  # type: ignore[no-untyped-call]
    conn.enable_load_extension(False)

    embeddings: dict[int, np.ndarray] = {}

    try:
        # Create placeholder string for SQL IN clause
        placeholders = ",".join("?" * len(doc_ids))
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, embedding FROM vault_vec WHERE id IN ({placeholders})", doc_ids
        )

        for row in cursor.fetchall():
            if row[1]:
                embeddings[row[0]] = np.frombuffer(row[1], dtype=np.float32)

        return embeddings
    finally:
        conn.close()


def get_document_info(config: HyphoraConfig, doc_id: int) -> Optional[tuple[str, str]]:
    """Get title and content for a document."""
    conn = sqlite3.connect(config.db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT title, content FROM vault WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None
    finally:
        conn.close()


def get_documents_batch(
    config: HyphoraConfig, doc_ids: list[int]
) -> dict[int, tuple[str, str]]:
    """Get title and content for multiple documents efficiently."""
    if not doc_ids:
        return {}

    conn = sqlite3.connect(config.db_path)
    documents: dict[int, tuple[str, str]] = {}

    try:
        placeholders = ",".join("?" * len(doc_ids))
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, title, content FROM vault WHERE id IN ({placeholders})",
            doc_ids,
        )

        for row in cursor.fetchall():
            documents[row[0]] = (row[1], row[2])

        return documents
    finally:
        conn.close()


def mmr_graph_walk(
    config: HyphoraConfig,
    seed_results: list[SearchResult],
    query_embedding: np.ndarray,
    lambda_mult: float = 0.5,
    select_k: int = 10,
    adjacent_k: int = 5,
    max_depth: int = 5,
    min_mmr_score: float = 0.01,
) -> list[WalkStep]:
    """
    MMR-based graph traversal starting from seed documents.

    Args:
        config: Hyphora configuration
        seed_results: Initial seeds from search
        query_embedding: Query embedding vector (normalized)
        lambda_mult: Balance between relevance & diversity (0-1)
        select_k: Total nodes to select
        adjacent_k: Max neighbors to consider per iteration
        max_depth: Maximum graph traversal depth
        min_mmr_score: Minimum MMR score threshold

    Returns:
        List of WalkStep objects with MMR scoring
    """
    if not seed_results:
        return []

    # Normalize query embedding
    query_norm = np.linalg.norm(query_embedding)
    if query_norm > 0:
        query_embedding = query_embedding / query_norm

    # Initialize candidates from seeds
    candidates: dict[int, MMRCandidate] = {}
    selected: list[tuple[int, float]] = []  # (id, mmr_score)
    selected_embeddings: list[np.ndarray] = []  # For redundancy calc
    visited: set[int] = set()

    # Get embeddings for all seeds at once
    seed_ids = [seed.id for seed in seed_results[:3]]  # Top 3 seeds
    seed_embeddings = get_embeddings_batch(config, seed_ids)

    # Add seed documents as initial candidates
    for seed in seed_results[:3]:
        if seed.id not in seed_embeddings:
            continue

        embedding = seed_embeddings[seed.id]
        similarity = cosine_similarity(query_embedding, embedding)

        candidates[seed.id] = MMRCandidate(
            id=seed.id,
            title=seed.title,
            content=seed.content,
            embedding=embedding,
            similarity=similarity,
            depth=0,
        )
        visited.add(seed.id)

    # MMR iteration
    path: list[WalkStep] = []

    while len(selected) < select_k and candidates:
        # Find candidate with best MMR score
        best_id = None
        best_score = float("-inf")

        for cand_id, candidate in candidates.items():
            score = candidate.mmr_score(lambda_mult)
            if score > best_score:
                best_score = score
                best_id = cand_id

        if best_id is None or best_score < min_mmr_score:
            break

        # Move best candidate to selected
        best_candidate = candidates[best_id]
        del candidates[best_id]

        selected.append((best_id, best_score))
        selected_embeddings.append(best_candidate.embedding)

        # Create WalkStep with MMR details
        mmr_details = [
            QueryScore(
                query_type="mmr_relevance",
                query_text=f"Query similarity: {best_candidate.similarity:.3f}",
                rrf_score=best_candidate.similarity,
                vec_rank=None,
                fts_rank=None,
            ),
            QueryScore(
                query_type="mmr_diversity",
                query_text=f"Max redundancy: {best_candidate.max_redundancy:.3f}",
                rrf_score=1.0 - best_candidate.max_redundancy,
                vec_rank=None,
                fts_rank=None,
            ),
            QueryScore(
                query_type="mmr_combined",
                query_text=f"MMR score (λ={lambda_mult}): {best_score:.3f}",
                rrf_score=best_score,
                vec_rank=None,
                fts_rank=None,
            ),
        ]

        path.append(
            WalkStep(
                id=best_candidate.id,
                title=best_candidate.title,
                content=best_candidate.content,
                combined_score=best_score,
                distance_from_seed=best_candidate.depth,
                query_scores=mmr_details,
            )
        )

        # Update redundancy for remaining candidates
        for candidate in candidates.values():
            redundancy = cosine_similarity(
                candidate.embedding, best_candidate.embedding
            )
            candidate.max_redundancy = max(candidate.max_redundancy, redundancy)

        # Expand: add neighbors if not at max depth
        if best_candidate.depth < max_depth:
            neighbors = get_neighbors(config, best_id)
            unvisited_neighbors = [n for n in neighbors if n not in visited]

            if unvisited_neighbors:
                # Batch fetch neighbor data
                neighbor_embeddings = get_embeddings_batch(config, unvisited_neighbors)
                neighbor_docs = get_documents_batch(config, unvisited_neighbors)

                # Score and rank neighbors by similarity
                neighbor_candidates: list[tuple[int, str, str, np.ndarray, float]] = []

                for n_id in unvisited_neighbors:
                    if n_id not in neighbor_embeddings or n_id not in neighbor_docs:
                        continue

                    embedding = neighbor_embeddings[n_id]
                    title, content = neighbor_docs[n_id]
                    similarity = cosine_similarity(query_embedding, embedding)

                    neighbor_candidates.append(
                        (n_id, title, content, embedding, similarity)
                    )

                # Sort by similarity and take top-k
                neighbor_candidates.sort(key=lambda x: x[4], reverse=True)

                for n_id, title, content, embedding, similarity in neighbor_candidates[
                    :adjacent_k
                ]:
                    # Calculate initial redundancy against all selected nodes
                    max_red = 0.0
                    for sel_emb in selected_embeddings:
                        redundancy = cosine_similarity(embedding, sel_emb)
                        max_red = max(max_red, redundancy)

                    candidates[n_id] = MMRCandidate(
                        id=n_id,
                        title=title,
                        content=content,
                        embedding=embedding,
                        similarity=similarity,
                        max_redundancy=max_red,
                        depth=best_candidate.depth + 1,
                    )
                    visited.add(n_id)

    return path
