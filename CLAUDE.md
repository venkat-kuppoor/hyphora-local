# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup

```bash
# Install dependencies using UV package manager
uv install
```

### Type Checking

```bash
# Run basedpyright type checker (strict mode enabled)
uvx basedpyright
```

### Linting and Formatting

```bash
# Run ruff linter and formatter
ruff check src/
ruff format src/
```

### Building

```bash
# Build the package
uv build
```

### Running the CLI

```bash
# Run the CLI tool
hyphora-local --help

# Apply database migrations (run this first to set up the database)
hyphora-local update

# Sync markdown files from vault to database
hyphora-local sync

# Search documents using RRF (reciprocal rank fusion)
hyphora-local search "your search query"
hyphora-local search "machine learning" --limit 5 --weight-fts 1.5 --weight-vec 0.8
hyphora-local search "neural networks" --k 20 --rrf-k 100

# Analyze vault and build wiki link graph
hyphora-local analyze-vault

# Find wiki links in a specific file
hyphora-local find-links <file_path>

# Show link statistics
hyphora-local link-stats
```

### Database Migrations

```bash
# Run migrations using caribou CLI (alternative to hyphora-local update)
caribou migrate migrations

# Run migrations programmatically via CLI
hyphora-local update
```

## Architecture Overview

**hyphora-local** is a Python CLI application that analyzes markdown vaults (similar to Obsidian) to extract and
analyze wiki-style links between documents.

### Core Components

1. **CLI Interface** (`src/hyphora_local/cli.py`):

   - Built with Typer framework
   - Commands: `update`, `sync`, `search`, `analyze-vault`, `find-links`, `link-stats`
   - Entry point is the `main()` function in `__init__.py`

2. **Configuration** (`src/hyphora_local/config.py`):

   - Uses functional error handling with result types
   - Reads from `hyphora.toml` in project root
   - Configuration includes vault path and database path
   - Pattern: `ConfigResult = tuple[Config | None, list[str]]`

3. **Sync Engine** (`src/hyphora_local/sync.py`):

   - Syncs markdown files from vault to SQLite database
   - Detects changes using filesystem modification time
   - Handles insertions, updates, and deletions
   - Uses relative paths as document titles

4. **Search Engine** (`src/hyphora_local/search.py`):

   - Implements reciprocal rank fusion (RRF) combining FTS5 and vector search
   - Uses ollama for query embedding generation
   - Configurable weights for FTS5 vs vector search results
   - Returns top candidates with detailed ranking information

5. **Graph Analysis** (`src/hyphora_local/graph.py`):

   - Extracts wiki links in formats: `[[Link]]`, `[[Link|Display]]`, `[[Link#Section]]`
   - Uses NetworkX for graph operations
   - Analyzes link relationships, connectivity, and statistics

6. **Database Schema** (defined in `migrations/`):
   - SQLite database stored in `.hyphora/hyphora.db`
   - Tables:
     - `vault`: Stores markdown files (id, title, content, modified_at)
     - `vault_fts`: Full-text search index (FTS5)
     - `vault_vec`: Vector embeddings (768 dimensions) for future semantic search
     - `links`: Stores document relationships
   - Automatic triggers maintain the FTS index

### Key Design Patterns

- **Error Handling**: Functional approach using tuples `(result | None, errors)`
- **Type Safety**: Strict type checking with basedpyright
- **CLI Design**: Command-based interface with Typer
- **Graph Operations**: NetworkX for link analysis
- **Search Capabilities**: FTS5 for text search, sqlite-vec for future vector search

### Search Parameters

The `search` command supports several parameters for tuning search results:

- `--limit` / `-l`: Number of final results to return (default: 3)
- `--k`: Number of candidates from each search method (default: 10)
- `--rrf-k`: RRF constant for rank fusion (default: 60)
- `--weight-fts`: Weight for FTS5 text search results (default: 1.0)
- `--weight-vec`: Weight for vector similarity results (default: 1.0)

**RRF Algorithm**: Combines rankings using `(1/(rrf_k + rank)) * weight` for each search method.

**Search Strategy Examples**:
- Favor semantic similarity: `--weight-vec 2.0 --weight-fts 0.5`
- Favor exact text matches: `--weight-fts 2.0 --weight-vec 0.5`
- Balanced approach: `--weight-fts 1.0 --weight-vec 1.0` (default)

### Important Notes

- The vault path is currently hardcoded to `hyphora-vault` directory
- Requires ollama running with `nomic-embed-text` model for vector search
- Vector embeddings are 768-dimensional (nomic-embed-text)
- Empty or very short documents (< 10 chars) skip embedding generation
- No test suite exists yet - consider adding pytest when implementing tests
- The project uses modern Python tooling: UV for packages, Hatchling for builds

