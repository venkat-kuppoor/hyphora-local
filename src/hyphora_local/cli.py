import typer
from pathlib import Path
from typing import cast
import caribou  # type: ignore[import-untyped]
from hyphora_local.config import load_hyphora_config
from hyphora_local.graph import build_wiki_graph, analyze_graph, extract_wiki_links  # type: ignore[attr-defined]
from hyphora_local.sync import sync_vault_to_database

app = typer.Typer()


@app.command()
def analyze_vault():
    """Build and analyze the wiki link graph from the vault."""
    match load_hyphora_config():
        case ("ok", conf):
            vault_path = Path(conf.vault_path)
            if not vault_path.exists():
                typer.echo(f"Error: Vault path does not exist: {vault_path}")
                raise typer.Exit(1)

            typer.echo(f"Analyzing vault at: {vault_path}")
            typer.echo("-" * 50)

            graph, _ = build_wiki_graph(vault_path)  # type: ignore[misc]
            analyze_graph(graph)  # type: ignore[arg-type]

        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)


@app.command()
def find_links(filename: str):
    """Find all wiki links in a specific file."""
    match load_hyphora_config():
        case ("ok", conf):
            vault_path = Path(conf.vault_path)
            if not vault_path.exists():
                typer.echo(f"Error: Vault path does not exist: {vault_path}")
                raise typer.Exit(1)

            # Find the file
            file_path = None
            for path in vault_path.rglob("*.md"):
                if path.stem == filename or path.name == filename:
                    file_path = path
                    break

            if not file_path:
                typer.echo(f"Error: File '{filename}' not found in vault")
                raise typer.Exit(1)

            # Extract links
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                links = extract_wiki_links(content)

            typer.echo(f"File: {file_path.relative_to(vault_path)}")
            typer.echo(f"Found {len(links)} wiki links:")
            for link in links:
                typer.echo(f"  - [[{link}]]")

        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)


@app.command()
def link_stats():
    """Show statistics about links between files."""
    match load_hyphora_config():
        case ("ok", conf):
            vault_path = Path(conf.vault_path)
            if not vault_path.exists():
                typer.echo(f"Error: Vault path does not exist: {vault_path}")
                raise typer.Exit(1)

            graph, _ = build_wiki_graph(vault_path)  # type: ignore[misc]

            typer.echo(f"\nLink Statistics for vault at: {vault_path}")
            typer.echo("=" * 50)

            # Basic stats
            typer.echo(f"Total files: {graph.number_of_nodes()}")  # type: ignore[no-untyped-call]
            typer.echo(f"Total links: {graph.number_of_edges()}")  # type: ignore[no-untyped-call]

            # Files with most incoming links
            in_degree: dict[str, int] = {}
            for node in graph.nodes():  # type: ignore[no-untyped-call]
                in_degree[node] = cast(int, graph.in_degree(node))  # type: ignore[no-untyped-call]
            most_linked = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[
                :5
            ]

            typer.echo("\nTop 5 most referenced files:")
            for file, count in most_linked:
                if count > 0:
                    typer.echo(f"  - {file}: {count} incoming links")

            # Files with most outgoing links
            out_degree: dict[str, int] = {}
            for node in graph.nodes():  # type: ignore[no-untyped-call]
                out_degree[node] = cast(int, graph.out_degree(node))  # type: ignore[no-untyped-call]
            most_linking = sorted(out_degree.items(), key=lambda x: x[1], reverse=True)[
                :5
            ]

            typer.echo("\nTop 5 files with most outgoing links:")
            for file, count in most_linking:
                if count > 0:
                    typer.echo(f"  - {file}: {count} outgoing links")

        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)


@app.command()
def sync():
    """Sync markdown files from the vault to the database."""
    match load_hyphora_config():
        case ("ok", conf):
            typer.echo(f"Syncing vault at: {conf.vault_path}")
            typer.echo(f"Database: {conf.db_path}")
            typer.echo("-" * 50)

            try:
                inserted, updated, deleted = sync_vault_to_database(conf)

                typer.echo("\nSync completed successfully:")
                typer.echo(f"  - Inserted: {inserted} documents")
                typer.echo(f"  - Updated: {updated} documents")
                typer.echo(f"  - Deleted: {deleted} documents")

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
