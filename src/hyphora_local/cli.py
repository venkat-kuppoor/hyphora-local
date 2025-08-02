import typer
from pathlib import Path
import caribou  # type: ignore[import-untyped]
from hyphora_local.config import load_hyphora_config
from hyphora_local.sync import sync_vault_to_database
from hyphora_local.search import search_documents
from hyphora_local.graph_walk import recursive_graph_walk

app = typer.Typer()


@app.command()
def sync():
    """Sync markdown files from the vault to the database."""
    match load_hyphora_config():
        case ("ok", conf):
            typer.echo(f"Syncing vault at: {conf.vault_path}")
            typer.echo(f"Database: {conf.db_path}")
            typer.echo("-" * 50)

            try:
                typer.echo("Syncing documents...")

                # Progress callback that shows embedding generation progress
                def progress_callback(current: int, total: int, msg: str) -> None:
                    typer.echo(f"\r[{current}/{total}] {msg[:60]}...", nl=False)

                inserted, updated, deleted, embeddings_generated, links_extracted = (
                    sync_vault_to_database(conf, progress_callback)
                )

                if embeddings_generated > 0:
                    typer.echo()  # New line after progress

                typer.echo("\nSync completed successfully:")
                typer.echo(f"  - Inserted: {inserted} documents")
                typer.echo(f"  - Updated: {updated} documents")
                typer.echo(f"  - Deleted: {deleted} documents")
                typer.echo(f"  - Embeddings generated: {embeddings_generated}")
                typer.echo(f"  - Links extracted: {links_extracted}")

            except Exception as e:
                typer.echo(f"Error during sync: {e}")
                raise typer.Exit(1)

        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)


@app.command()
def update():
    """Apply database migrations to bring the database up to date."""
    match load_hyphora_config():
        case ("ok", conf):
            typer.echo(f"Database: {conf.db_path}")
            typer.echo("-" * 50)

            # Ensure database directory exists
            conf.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Get migrations directory
            migrations_dir = Path(__file__).parent.parent.parent / "migrations"

            try:
                # Upgrade to most recent version
                caribou.upgrade(str(conf.db_path), str(migrations_dir))  # type: ignore[no-untyped-call]
                typer.echo("Database migrations applied successfully!")

            except Exception as e:
                typer.echo(f"Error applying migrations: {e}")
                raise typer.Exit(1)

        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)


@app.command()
def search(
    query: str,
    limit: int = typer.Option(3, "--limit", "-l", help="Number of results to return"),
    k: int = typer.Option(
        10, "--k", help="Number of candidates from each search method"
    ),
    rrf_k: int = typer.Option(60, "--rrf-k", help="RRF constant"),
    weight_fts: float = typer.Option(
        1.0, "--weight-fts", help="Weight for FTS5 results"
    ),
    weight_vec: float = typer.Option(
        1.0, "--weight-vec", help="Weight for vector results"
    ),
):
    """Search documents using reciprocal rank fusion of FTS5 and vector search."""
    match load_hyphora_config():
        case ("ok", conf):
            try:
                typer.echo(f"Searching for: '{query}'")
                typer.echo("-" * 50)

                results = search_documents(
                    conf,
                    query,
                    k=k,
                    rrf_k=rrf_k,
                    weight_fts=weight_fts,
                    weight_vec=weight_vec,
                    limit=limit,
                )

                if not results:
                    typer.echo("No results found.")
                    return

                for i, result in enumerate(results, 1):
                    typer.echo(f"\n{i}. {result.title}")
                    typer.echo(f"   Combined Score: {result.combined_rank:.4f}")

                    rank_info: list[str] = []
                    if result.fts_rank is not None:
                        rank_info.append(
                            f"FTS: #{result.fts_rank} (score: {result.fts_score:.2f})"
                        )
                    if result.vec_rank is not None:
                        rank_info.append(
                            f"Vector: #{result.vec_rank} (dist: {result.vec_distance:.4f})"
                        )

                    if rank_info:
                        typer.echo(f"   Ranks: {' | '.join(rank_info)}")

                    # Show content preview (first 200 chars)
                    content_preview = result.content[:200].replace("\n", " ")
                    if len(result.content) > 200:
                        content_preview += "..."
                    typer.echo(f"   Preview: {content_preview}")

            except Exception as e:
                typer.echo(f"Error during search: {e}")
                raise typer.Exit(1)

        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)


@app.command()
def walk(
    query: str,
    seed_limit: int = typer.Option(
        3, "--seed-limit", help="Number of seed documents from initial search"
    ),
    max_hops: int = typer.Option(
        5, "--max-hops", help="Maximum number of hops in graph walk"
    ),
    score_threshold: float = typer.Option(
        0.01, "--score-threshold", help="Minimum score threshold for continuing walk"
    ),
    k: int = typer.Option(
        10, "--k", help="Number of candidates from each search method"
    ),
    rrf_k: int = typer.Option(60, "--rrf-k", help="RRF constant"),
    weight_fts: float = typer.Option(
        1.0, "--weight-fts", help="Weight for FTS5 results"
    ),
    weight_vec: float = typer.Option(
        1.0, "--weight-vec", help="Weight for vector results"
    ),
    query_weight_original: float = typer.Option(
        0.7, "--weight-original", help="Weight for original query"
    ),
    query_weight_current: float = typer.Option(
        0.3, "--weight-current", help="Weight for current node content"
    ),
    use_mmr: bool = typer.Option(
        False, "--mmr", help="Use MMR for diversity-aware selection"
    ),
    mmr_lambda: float = typer.Option(
        0.5, "--mmr-lambda", help="MMR lambda parameter (0=diversity, 1=relevance)"
    ),
    mmr_adjacent_k: int = typer.Option(
        5, "--mmr-adjacent-k", help="Max neighbors to consider per MMR iteration"
    ),
):
    """Search documents using hybrid search + recursive graph walk for context expansion."""
    match load_hyphora_config():
        case ("ok", conf):
            try:
                typer.echo(f"Walking graph for: '{query}'")
                typer.echo("-" * 50)

                # Step 1: Get seed documents using hybrid search
                typer.echo("Finding seed documents...")
                seed_results = search_documents(
                    conf,
                    query,
                    k=k,
                    rrf_k=rrf_k,
                    weight_fts=weight_fts,
                    weight_vec=weight_vec,
                    limit=seed_limit,
                )

                if not seed_results:
                    typer.echo("No seed documents found.")
                    return

                typer.echo(f"Found {len(seed_results)} seed documents:")
                for i, result in enumerate(seed_results, 1):
                    typer.echo(
                        f"  {i}. {result.title} (score: {result.combined_rank:.4f})"
                    )

                # Step 2: Perform recursive graph walk
                mode_text = "MMR-based" if use_mmr else "recursive"
                typer.echo(
                    f"\nPerforming {mode_text} graph walk (max {max_hops} hops)..."
                )
                if use_mmr:
                    typer.echo(
                        f"  MMR parameters: λ={mmr_lambda}, adjacent_k={mmr_adjacent_k}"
                    )

                walk_steps = recursive_graph_walk(
                    conf,
                    seed_results,
                    query,
                    max_hops=max_hops,
                    score_threshold=score_threshold,
                    query_weights=[query_weight_original, query_weight_current],
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

                if not walk_steps:
                    typer.echo("No additional documents found during graph walk.")
                    return

                typer.echo(
                    f"\nGraph walk found {len(walk_steps)} additional documents:"
                )
                typer.echo("-" * 50)

                for i, step in enumerate(walk_steps, 1):
                    typer.echo(f"\n{i}. {step.title}")
                    typer.echo(f"   Distance: {step.distance_from_seed} hops from seed")
                    typer.echo(f"   Combined Score: {step.combined_score:.4f}")

                    # Show query breakdown
                    for j, query_score in enumerate(step.query_scores):
                        typer.echo(
                            f"   Query {j + 1} ({query_score.query_type}): {query_score.rrf_score:.4f}"
                        )
                        typer.echo(f"     Text: {query_score.query_text}")

                        rank_info: list[str] = []
                        if query_score.fts_rank is not None:
                            rank_info.append(f"FTS: #{query_score.fts_rank}")
                        if query_score.vec_rank is not None:
                            rank_info.append(f"Vector: #{query_score.vec_rank}")
                        if rank_info:
                            typer.echo(f"     Ranks: {' | '.join(rank_info)}")

                    # Show content preview
                    content_preview = step.content[:200].replace("\n", " ")
                    if len(step.content) > 200:
                        content_preview += "..."
                    typer.echo(f"   Preview: {content_preview}")

                # Summary
                typer.echo(f"\n{'=' * 50}")
                typer.echo("SUMMARY:")
                typer.echo(f"Seed documents: {len(seed_results)}")
                typer.echo(f"Graph walk documents: {len(walk_steps)}")
                typer.echo(
                    f"Total documents found: {len(seed_results) + len(walk_steps)}"
                )

            except Exception as e:
                typer.echo(f"Error during graph walk: {e}")
                raise typer.Exit(1)

        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)


@app.command()
def serve():
    """Start the FastMCP server for Hyphora search and graph walk tools."""
    from hyphora_local.server import mcp

    try:
        mcp.run()
    except KeyboardInterrupt:
        typer.echo("\nServer stopped.")
    except Exception as e:
        typer.echo(f"Error running server: {e}")
        raise typer.Exit(1)
