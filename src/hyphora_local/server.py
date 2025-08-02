"""FastMCP server for Hyphora hybrid search and graph walk functionality."""

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
    the most relevant starting points.
    Feel free to use this tool if a user provides a prompt without any context.
    Keep in mind, using graph walk after seed selection
    is highly recommended as it traverses the information-rich knowledge graph to
    discover additional relevant documents through high-quality relationships that
    may not surface in direct search.

    Args:
        query: Search query text
        limit: Number of seed documents to return (default: 5, range: 1-20)
        k: Number of candidates to retrieve from each search method before fusion
           (default: 10, range: 5-50). Higher values cast a wider net.
        rrf_k: Reciprocal Rank Fusion constant that controls ranking behavior
               (default: 60, range: 10-100). Lower values favor top-ranked items more strongly.
        weight_fts: Weight multiplier for full-text search results (default: 1.0, range: 0-5).
                    Higher values prioritize exact/partial text matches.
        weight_vec: Weight multiplier for vector similarity results (default: 1.0, range: 0-5).
                    Higher values prioritize semantic similarity.

    Returns:
        Selected seed documents with relevance scores, rankings, and full content
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
    use_mmr: bool = True,
    mmr_lambda: float = 0.635,
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
    1. Provide seed_documents from select_seed_documents() for manual control. Choose to omit seeds you don't think are relevant.
    2. Provide only a query to automatically run hybrid search + graph walk in one go

    The graph walk explores document relationships to find relevant information that
    may not appear in direct search results but is connected through the knowledge graph.

    Args:
        query: Original search query text
        seed_documents: Optional list of document objects from select_seed_documents().seed_documents array.
                       Each object should contain these fields from the seed selection results:
                       - id (required): Document ID (integer)
                       - title (required): Document title (string)
                       - content (optional): Full document content (string)
                       - combined_score (optional): Combined relevance score (float)
                       - vec_rank (optional): Vector search rank (integer or null)
                       - fts_rank (optional): Full-text search rank (integer or null)
                       - vec_distance (optional): Vector distance (float or null)
                       - fts_score (optional): Full-text search score (float or null)
                       Example: [{"id": 42, "title": "Graph Theory", "content": "...", "combined_score": 0.85}, ...]
                       If not provided, runs hybrid search automatically.
        max_hops: Maximum graph traversal depth from seed documents (default: 5, range: 1-10).
                  Each hop follows links to neighboring documents.
        score_threshold: Minimum relevance score to continue traversal (default: 0.01, range: 0-1).
                        Lower values explore more broadly, higher values stay focused.
        use_mmr: Enable Maximal Marginal Relevance for diversity-aware selection (default: True).
                 MMR balances relevance with diversity to avoid redundant documents.
        mmr_lambda: MMR diversity balance (default: 0.635, range: 0-1).
                    0 = maximum diversity (avoid similar documents)
                    1 = maximum relevance (ignore diversity)
                    0.635 = more balanced approach, but leaning towards relevance.
                    if no results appear, then try incrementing this by 0.05 at a time until results appear.
        mmr_adjacent_k: Maximum neighbors to evaluate per MMR iteration (default: 5, range: 1-20).
                        Higher values consider more options but increase computation.
        weight_original: Weight for original query when scoring neighbors (default: 0.7, range: 0-1).
                        Higher values keep focus on initial query throughout traversal.
        weight_current: Weight for current document content when scoring neighbors (default: 0.3, range: 0-1).
                       Higher values allow more topic drift based on current context.
                       Note: weight_original + weight_current should equal 1.0
        seed_limit: Number of initial seeds if running integrated search (default: 3, range: 1-10)
        k: Candidates per search method if running integrated search (default: 10, range: 5-50)
        rrf_k: RRF constant if running integrated search (default: 60, range: 10-100)
        weight_fts: FTS5 weight if running integrated search (default: 1.0, range: 0-5)
        weight_vec: Vector weight if running integrated search (default: 1.0, range: 0-5)

    Returns:
        Graph walk path with discovered documents, traversal details, and full content
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
                    combined_rank=doc.get(
                        "combined_score", doc.get("combined_rank", 1.0)
                    ),
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
        "max_distance_reached": max([s.distance_from_seed for s in walk_steps])
        if walk_steps
        else 0,
    }


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()

