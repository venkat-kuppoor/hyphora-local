import typer
from pathlib import Path
from typing import cast
from hyphora_local.config import load_hyphora_config
from hyphora_local.graph import build_wiki_graph, analyze_graph, extract_wiki_links  # type: ignore[attr-defined]

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
            most_linked = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:5]
            
            typer.echo("\nTop 5 most referenced files:")
            for file, count in most_linked:
                if count > 0:
                    typer.echo(f"  - {file}: {count} incoming links")
            
            # Files with most outgoing links
            out_degree: dict[str, int] = {}
            for node in graph.nodes():  # type: ignore[no-untyped-call]
                out_degree[node] = cast(int, graph.out_degree(node))  # type: ignore[no-untyped-call]
            most_linking = sorted(out_degree.items(), key=lambda x: x[1], reverse=True)[:5]
            
            typer.echo("\nTop 5 files with most outgoing links:")
            for file, count in most_linking:
                if count > 0:
                    typer.echo(f"  - {file}: {count} outgoing links")
                    
        case ("error", err):
            typer.echo(f"Configuration error: {err}")
            raise typer.Exit(1)