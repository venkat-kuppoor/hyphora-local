"""FastMCP server for Hyphora hybrid search and graph walk functionality."""

import numpy as np
import ollama  # type: ignore[import-untyped]
from fastmcp import FastMCP
from typing import Optional, Any

from .config import load_hyphora_config, HyphoraConfig
from .search import search_documents, SearchResult
from .graph_walk import recursive_graph_walk

# Initialize FastMCP server
mcp = FastMCP("hyphora-local")


def get_config() -> HyphoraConfig:
    """Load the Hyphora configuration."""
    match load_hyphora_config():
        case ("ok", conf):
            return conf
        case ("error", msg):
            raise ValueError(f"Failed to load config: {msg}")


@mcp.tool()
async def select_seed_documents(
    query: str,
    limit: int = 5,
    k: int = 10,
    rrf_k: int = 60,
    weight_fts: float = 1.0,
    weight_vec: float = 1.0,
) -> dict[str, Any]:
    """
    Select initial seed documents using hybrid search (FTS5 + vector embeddings).
    
    This tool performs the first stage of knowledge graph exploration by finding
    the most relevant starting points. However, using graph walk after seed selection
    is highly recommended as it traverses the information-rich knowledge graph to
    discover additional relevant documents through high-quality relationships that
    may not surface in direct search.
    
    Args:
        query: Search query
        limit: Number of seed documents to return
        k: Number of candidates from each search method
        rrf_k: RRF constant for rank fusion
        weight_fts: Weight for FTS5 text search results
        weight_vec: Weight for vector similarity results
    
    Returns:
        Selected seed documents with relevance scores
    """
    config = get_config()
    
    results = search_documents(
        config,
        query,
        k=k,
        rrf_k=rrf_k,
        weight_fts=weight_fts,
        weight_vec=weight_vec,
        limit=limit,
    )
    
    return {
        "query": query,
        "seed_documents": [
            {
                "id": r.id,
                "title": r.title,
                "content": r.content,
                "combined_score": r.combined_rank,
                "vec_rank": r.vec_rank,
                "fts_rank": r.fts_rank,
                "vec_distance": r.vec_distance,
                "fts_score": r.fts_score,
            }
            for r in results
        ],
        "total_found": len(results),
    }


@mcp.tool()
async def graph_walk(
    query: str,
    seed_documents: Optional[list[dict[str, Any]]] = None,
    max_hops: int = 5,
    score_threshold: float = 0.01,
    use_mmr: bool = False,
    mmr_lambda: float = 0.5,
    mmr_adjacent_k: int = 5,
    weight_original: float = 0.7,
    weight_current: float = 0.3,
    # Parameters for integrated search if seed_documents not provided
    seed_limit: int = 3,
    k: int = 10,
    rrf_k: int = 60,
    weight_fts: float = 1.0,
    weight_vec: float = 1.0,
) -> dict[str, Any]:
    """
    Traverse the knowledge graph starting from seed documents to discover related content.
    
    This tool can be used in two ways:
    1. Provide seed_documents from select_seed_documents() for manual control
    2. Provide only a query to automatically run hybrid search + graph walk in one go
    
    The graph walk explores document relationships to find relevant information that
    may not appear in direct search results but is connected through the knowledge graph.
    
    Args:
        query: Original search query
        seed_documents: Optional list of seed documents (if not provided, runs hybrid search first)
        max_hops: Maximum number of graph traversal hops
        score_threshold: Minimum score to continue traversal
        use_mmr: Enable MMR for diversity-aware selection
        mmr_lambda: MMR balance (0=diversity, 1=relevance)
        mmr_adjacent_k: Max neighbors per MMR iteration
        weight_original: Weight for original query in scoring
        weight_current: Weight for current node content
        seed_limit: Number of seeds (if running integrated search)
        k: Candidates per search method (if running integrated search)
        rrf_k: RRF constant (if running integrated search)
        weight_fts: FTS5 weight (if running integrated search)
        weight_vec: Vector weight (if running integrated search)
    
    Returns:
        Graph walk path with discovered documents and traversal details
    """
    config = get_config()
    
    # Convert seed documents to SearchResult objects or run search
    if seed_documents:
        # Use provided seed documents
        seed_results = []
        for doc in seed_documents:
            seed_results.append(
                SearchResult(
                    id=doc["id"],
                    title=doc["title"],
                    content=doc.get("content", ""),
                    vec_rank=doc.get("vec_rank"),
                    fts_rank=doc.get("fts_rank"),
                    combined_rank=doc.get("combined_score", doc.get("combined_rank", 1.0)),
                    vec_distance=doc.get("vec_distance"),
                    fts_score=doc.get("fts_score"),
                )
            )
    else:
        # Run hybrid search to get seeds
        seed_results = search_documents(
            config,
            query,
            k=k,
            rrf_k=rrf_k,
            weight_fts=weight_fts,
            weight_vec=weight_vec,
            limit=seed_limit,
        )
    
    if not seed_results:
        return {
            "query": query,
            "seeds": [],
            "walk_path": [],
            "error": "No seed documents found",
        }
    
    # Perform graph walk
    walk_steps = recursive_graph_walk(
        config,
        seed_results,
        query,
        max_hops=max_hops,
        score_threshold=score_threshold,
        query_weights=[weight_original, weight_current],
        rrf_params={
            "k": k,
            "rrf_k": rrf_k,
            "weight_fts": weight_fts,
            "weight_vec": weight_vec,
        },
        use_mmr=use_mmr,
        mmr_lambda=mmr_lambda,
        mmr_adjacent_k=mmr_adjacent_k,
    )
    
    return {
        "query": query,
        "mode": "mmr" if use_mmr else "standard",
        "seeds_used": [
            {
                "id": s.id,
                "title": s.title,
                "score": s.combined_rank,
            }
            for s in seed_results
        ],
        "walk_path": [
            {
                "id": step.id,
                "title": step.title,
                "content": step.content,
                "combined_score": step.combined_score,
                "distance_from_seed": step.distance_from_seed,
                "scoring_details": [
                    {
                        "query_type": qs.query_type,
                        "query_text": qs.query_text,
                        "score": qs.rrf_score,
                        "vec_rank": qs.vec_rank,
                        "fts_rank": qs.fts_rank,
                    }
                    for qs in step.query_scores
                ],
            }
            for step in walk_steps
        ],
        "total_documents_found": len(walk_steps),
        "max_distance_reached": max([s.distance_from_seed for s in walk_steps]) if walk_steps else 0,
    }


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()