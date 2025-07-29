import sqlite3
import re
from typing import NamedTuple

import ollama  # type: ignore[import-untyped]
import sqlite_vec  # type: ignore[import-untyped]
from .config import HyphoraConfig


def sanitize_fts5_query(text: str) -> str:
    """
    Sanitize text for use as an FTS5 query.

    Args:
        text: Input text

    Returns:
        Sanitized query string safe for FTS5
    """
    # First, escape FTS5 special characters by removing them
    # FTS5 special chars: " ^ * ( ) : { } [ ] -
    cleaned_text = re.sub(r'["\^\*\(\)\:\{\}\[\]\-\?]', " ", text)

    # Extract alphabetic words (3+ characters)
    words = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned_text.lower())

    # Quote each term for safety
    quoted_terms = [f'"{word}"' for word in words]

    # Join with spaces (each term is quoted for safety)
    return " ".join(quoted_terms) if quoted_terms else '"document"'


class SearchResult(NamedTuple):
    """A search result with ranking information."""

    id: int
    title: str
    content: str
    vec_rank: int | None
    fts_rank: int | None
    combined_rank: float
    vec_distance: float | None
    fts_score: float | None


def search_documents(
    config: HyphoraConfig,
    query: str,
    k: int = 10,
    rrf_k: int = 60,
    weight_fts: float = 1.0,
    weight_vec: float = 1.0,
    limit: int = 3,
) -> list[SearchResult]:
    """
    Search documents using reciprocal rank fusion of FTS5 and vector search.

    Args:
        config: Hyphora configuration
        query: Search query
        k: Number of results to consider from each search method
        rrf_k: RRF constant (typically 60)
        weight_fts: Weight for FTS5 results
        weight_vec: Weight for vector search results
        limit: Number of final results to return

    Returns:
        List of SearchResult objects ordered by combined rank
    """
    # Generate embedding for the query
    try:
        response = ollama.embeddings(model="nomic-embed-text", prompt=query)  # type: ignore[no-untyped-call]
        query_embedding = response.get("embedding", [])  # type: ignore[no-any-return]

        if not query_embedding:
            raise ValueError("Failed to generate query embedding")

    except Exception as e:
        raise RuntimeError(f"Failed to generate embedding for query: {e}")

    # Connect to database
    conn = sqlite3.connect(config.db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)  # type: ignore[no-untyped-call]
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Serialize the query embedding for sqlite-vec
        query_embedding_bytes = sqlite_vec.serialize_float32(query_embedding)  # type: ignore[no-untyped-call]

        # Sanitize the query for FTS5
        sanitized_query = sanitize_fts5_query(query)

        # Execute the RRF query
        cursor.execute(
            """
            -- Vector search results
            WITH vec_matches AS (
                SELECT
                    v.id,
                    ROW_NUMBER() OVER (ORDER BY vault_vec.distance) AS rank_number,
                    vault_vec.distance
                FROM vault_vec
                JOIN vault v ON v.id = vault_vec.id
                WHERE vault_vec.embedding MATCH ?
                AND vault_vec.k = ?
            ),
            -- FTS5 search results  
            fts_matches AS (
                SELECT
                    rowid,
                    ROW_NUMBER() OVER (ORDER BY rank) AS rank_number,
                    rank AS score
                FROM vault_fts
                WHERE vault_fts MATCH ?
                LIMIT ?
            ),
            -- Combine with RRF
            final AS (
                SELECT
                    v.id,
                    v.title,
                    v.content,
                    vec_matches.rank_number AS vec_rank,
                    fts_matches.rank_number AS fts_rank,
                    -- RRF algorithm
                    (
                        COALESCE(1.0 / (? + fts_matches.rank_number), 0.0) * ? +
                        COALESCE(1.0 / (? + vec_matches.rank_number), 0.0) * ?
                    ) AS combined_rank,
                    vec_matches.distance AS vec_distance,
                    fts_matches.score AS fts_score
                FROM fts_matches
                FULL OUTER JOIN vec_matches ON vec_matches.id = fts_matches.rowid
                JOIN vault v ON v.id = COALESCE(fts_matches.rowid, vec_matches.id)
                ORDER BY combined_rank DESC
            )
            SELECT * FROM final
            LIMIT ?
        """,
            (
                query_embedding_bytes,
                k,  # vec search params
                sanitized_query,
                k,  # fts search params
                rrf_k,
                weight_fts,  # RRF params for FTS
                rrf_k,
                weight_vec,  # RRF params for vector
                limit,  # final limit
            ),
        )

        results: list[SearchResult] = []
        for row in cursor.fetchall():
            results.append(
                SearchResult(
                    id=row["id"],
                    title=row["title"],
                    content=row["content"],
                    vec_rank=row["vec_rank"],
                    fts_rank=row["fts_rank"],
                    combined_rank=row["combined_rank"],
                    vec_distance=row["vec_distance"],
                    fts_score=row["fts_score"],
                )
            )

        return results

    finally:
        conn.close()
