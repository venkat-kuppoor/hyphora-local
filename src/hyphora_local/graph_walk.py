import sqlite3
import re
from typing import NamedTuple, Optional, Any
from dataclasses import dataclass

from .config import HyphoraConfig
from .search import SearchResult, search_documents


def sanitize_fts5_query(text: str, max_terms: int = 10) -> str:
    """
    Sanitize text for use as an FTS5 query by extracting key terms.
    
    Args:
        text: Input text (could be document content)
        max_terms: Maximum number of terms to include in query
        
    Returns:
        Sanitized query string safe for FTS5
    """
    # Remove special characters and extract words
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Remove common stop words
    stop_words = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 
        'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 
        'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy',
        'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'
    }
    
    # Filter out stop words and get unique terms
    meaningful_words: list[str] = []
    seen: set[str] = set()
    for word in words:
        if word not in stop_words and word not in seen and len(word) >= 3:
            meaningful_words.append(word)
            seen.add(word)
            if len(meaningful_words) >= max_terms:
                break
    
    # Join with spaces (simple FTS5 query)
    return ' '.join(meaningful_words) if meaningful_words else 'document'


@dataclass
class QueryScore:
    """Individual RRF score for a specific query."""
    query_type: str  # "original", "parent", "current"
    query_text: str
    rrf_score: float
    vec_rank: int | None
    fts_rank: int | None


class WalkStep(NamedTuple):
    """A single step in the graph walk."""
    id: int
    title: str
    content: str
    combined_score: float
    distance_from_seed: int
    query_scores: list[QueryScore]  # Individual scores for each query


def get_neighbors(config: HyphoraConfig, node_id: int) -> list[int]:
    """Get all neighboring node IDs (both incoming and outgoing links)."""
    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()
    
    try:
        # Get both outgoing and incoming links (bidirectional)
        cursor.execute("""
            SELECT DISTINCT target_id as neighbor_id FROM links WHERE source_id = ?
            UNION
            SELECT DISTINCT source_id as neighbor_id FROM links WHERE target_id = ?
        """, (node_id, node_id))
        
        neighbors = [row[0] for row in cursor.fetchall()]
        return neighbors
        
    finally:
        conn.close()


def get_document_content(config: HyphoraConfig, doc_id: int) -> Optional[str]:
    """Get the content of a document by ID."""
    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT content FROM vault WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        return row[0] if row else None
        
    finally:
        conn.close()


def score_neighbors_multi_query(
    config: HyphoraConfig,
    neighbor_ids: list[int],
    queries: list[str],
    query_weights: list[float],
    rrf_params: dict[str, Any]
) -> dict[int, tuple[float, list[QueryScore]]]:
    """
    Score neighbors using multiple queries and combine with weights.
    
    Returns:
        Dict mapping neighbor_id to (combined_score, query_details)
    """
    neighbor_scores: dict[int, tuple[float, list[QueryScore]]] = {}
    
    for neighbor_id in neighbor_ids:
        individual_scores: list[float] = []
        query_details: list[QueryScore] = []
        
        # Score this neighbor against each query
        for i, query in enumerate(queries):
            # Sanitize query for FTS5 compatibility
            sanitized_query = sanitize_fts5_query(query)
            
            # Use existing search_documents but create a temporary result set
            # that only includes this neighbor to get its RRF score
            all_results = search_documents(
                config, 
                sanitized_query, 
                k=rrf_params.get("k", 10),
                rrf_k=rrf_params.get("rrf_k", 60),
                weight_fts=rrf_params.get("weight_fts", 1.0),
                weight_vec=rrf_params.get("weight_vec", 1.0),
                limit=1000  # Get many results to find our neighbor
            )
            
            # Find our specific neighbor in the results
            neighbor_result = None
            for result in all_results:
                if result.id == neighbor_id:
                    neighbor_result = result
                    break
            
            if neighbor_result:
                score = neighbor_result.combined_rank
                query_details.append(QueryScore(
                    query_type=f"query_{i}" if i > 0 else "original",
                    query_text=sanitized_query[:50] + "..." if len(sanitized_query) > 50 else sanitized_query,
                    rrf_score=score,
                    vec_rank=neighbor_result.vec_rank,
                    fts_rank=neighbor_result.fts_rank
                ))
                individual_scores.append(score)
            else:
                # Neighbor not found in results (very low relevance)
                individual_scores.append(0.0)
                query_details.append(QueryScore(
                    query_type=f"query_{i}" if i > 0 else "original",
                    query_text=sanitized_query[:50] + "..." if len(sanitized_query) > 50 else sanitized_query,
                    rrf_score=0.0,
                    vec_rank=None,
                    fts_rank=None
                ))
        
        # Combine scores using weights
        combined_score = sum(
            score * weight 
            for score, weight in zip(individual_scores, query_weights)
        )
        
        neighbor_scores[neighbor_id] = (combined_score, query_details)
    
    return neighbor_scores


def recursive_graph_walk(
    config: HyphoraConfig,
    seed_results: list[SearchResult],
    original_prompt: str,
    max_hops: int = 5,
    score_threshold: float = 0.1,
    query_weights: Optional[list[float]] = None,
    rrf_params: Optional[dict[str, Any]] = None,
) -> list[WalkStep]:
    """
    Perform recursive graph walk starting from seed documents.
    
    Args:
        config: Hyphora configuration
        seed_results: Initial seed documents from hybrid search
        original_prompt: Original user query
        max_hops: Maximum number of hops to take
        score_threshold: Minimum score threshold for continuing
        query_weights: Weights for combining multiple queries [original, parent, current, ...]
        rrf_params: Parameters for RRF (k, rrf_k, weight_fts, weight_vec)
        
    Returns:
        List of WalkStep objects representing the path taken
    """
    if not seed_results:
        return []
    
    # Default parameters
    if query_weights is None:
        query_weights = [0.7, 0.3]  # [original_prompt, current_node]
    if rrf_params is None:
        rrf_params = {"k": 10, "rrf_k": 60, "weight_fts": 1.0, "weight_vec": 1.0}
    
    # Start from the highest-scoring seed
    current_node = seed_results[0]
    visited_nodes = {current_node.id}
    path: list[WalkStep] = []
    
    # Track the content of nodes we've visited for multi-query scoring
    content_history: list[str] = [original_prompt, current_node.content]
    
    for hop in range(max_hops):
        # Get neighbors of current node
        neighbors = get_neighbors(config, current_node.id)
        unvisited_neighbors = [n for n in neighbors if n not in visited_nodes]
        
        if not unvisited_neighbors:
            break
        
        # Prepare queries based on current history and weights
        queries_to_use = content_history[-len(query_weights):]
        weights_to_use = query_weights[-len(queries_to_use):]
        
        # Score all neighbors using multiple queries
        neighbor_scores = score_neighbors_multi_query(
            config, unvisited_neighbors, queries_to_use, weights_to_use, rrf_params
        )
        
        # Find the best neighbor
        if not neighbor_scores:
            break
            
        best_neighbor_id = max(neighbor_scores.keys(), key=lambda x: neighbor_scores[x][0])
        best_score, query_details = neighbor_scores[best_neighbor_id]
        
        # Check if score meets threshold
        if best_score < score_threshold:
            break
        
        # Get details about the best neighbor
        conn = sqlite3.connect(config.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, content FROM vault WHERE id = ?", (best_neighbor_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            break
        
        # Create walk step
        walk_step = WalkStep(
            id=row[0],
            title=row[1],
            content=row[2],
            combined_score=best_score,
            distance_from_seed=hop + 1,
            query_scores=query_details
        )
        
        path.append(walk_step)
        visited_nodes.add(best_neighbor_id)
        
        # Update current node and content history
        current_node = SearchResult(
            id=row[0], title=row[1], content=row[2],
            vec_rank=None, fts_rank=None, combined_rank=best_score,
            vec_distance=None, fts_score=None
        )
        content_history.append(current_node.content)
    
    return path