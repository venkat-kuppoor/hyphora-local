import re
from typing import cast
import networkx as nx
from pathlib import Path


def extract_wiki_links(content: str) -> list[str]:
    """Extract wiki-style links from markdown content.

    Supports formats like:
    - [[Link Text]]
    - [[Link Text|Display Text]]
    - [[Link Text#Section]]
    """
    # Pattern to match [[link]] or [[link|display]] or [[link#section]]
    pattern = r"\[\[([^\]]+)\]\]"
    matches = re.findall(pattern, content)

    links: list[str] = []
    for match in matches:
        # Handle [[link|display]] format
        if "|" in match:
            link = match.split("|")[0].strip()
        else:
            link = match.strip()

        # Remove section anchors if present
        if "#" in link:
            link = link.split("#")[0].strip()

        links.append(link)

    return links


def build_wiki_graph(directory_path: str | Path) -> tuple[nx.DiGraph[str], dict[str, str]]:
    """Build a graph from wiki links in markdown files."""
    graph: nx.DiGraph[str] = nx.DiGraph()  # Directed graph since links have direction
    directory = Path(directory_path)

    # Dictionary to store file content for reference
    file_contents: dict[str, str] = {}

    # First pass: collect all markdown files
    md_files: dict[str, Path] = {}
    for file_path in directory.rglob("*.md"):
        # Use filename without extension as the node name
        node_name = file_path.stem
        md_files[node_name] = file_path

        # Add node to graph
        graph.add_node(node_name, file_path=str(file_path))

    # Second pass: extract links and build edges
    for node_name, file_path in md_files.items():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                file_contents[node_name] = content

                # Extract wiki links
                links = extract_wiki_links(content)

                # Add edges for each link
                for link in links:
                    # Only add edge if the target exists as a file
                    if link in md_files:
                        graph.add_edge(node_name, link)
                    else:
                        # Optionally track broken links
                        print(f"Broken link in {node_name}: {link}")

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    return graph, file_contents


def analyze_graph(graph: nx.DiGraph[str]) -> None:
    """Analyze the wiki link graph."""
    print("Graph Statistics:")
    print(f"- Nodes (files): {graph.number_of_nodes()}")
    print(f"- Edges (links): {graph.number_of_edges()}")
    density: float = cast(float, nx.density(graph))  # type: ignore[reportUnknownMemberType]
    print(f"- Density: {density:.3f}")
    print(f"- Is connected: {nx.is_weakly_connected(graph)}")

    # Find most linked pages
    # Get in-degree for each node
    in_degree: dict[str, int] = {}
    for node in graph.nodes():
        in_degree[node] = cast(int, graph.in_degree(node))
    most_linked = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:10]
    print("\nMost linked pages:")
    for page, count in most_linked:
        print(f"  {page}: {count} incoming links")

    # Find pages with most outgoing links
    # Get out-degree for each node
    out_degree: dict[str, int] = {}
    for node in graph.nodes():
        out_degree[node] = cast(int, graph.out_degree(node))
    most_linking = sorted(out_degree.items(), key=lambda x: x[1], reverse=True)[:10]
    print("\nPages with most outgoing links:")
    for page, count in most_linking:
        print(f"  {page}: {count} outgoing links")

    # Find isolated nodes (no links in or out)
    # Find isolated nodes (no links in or out)
    isolated: list[str] = [node for node in graph.nodes() if graph.degree(node) == 0]
    if isolated:
        print(f"\nIsolated pages ({len(isolated)}): {isolated[:10]}")
