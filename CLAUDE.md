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
   - Commands: `update`, `sync`, `analyze-vault`, `find-links`, `link-stats`
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

4. **Graph Analysis** (`src/hyphora_local/graph.py`):

   - Extracts wiki links in formats: `[[Link]]`, `[[Link|Display]]`, `[[Link#Section]]`
   - Uses NetworkX for graph operations
   - Analyzes link relationships, connectivity, and statistics

5. **Database Schema** (defined in `migrations/`):
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

### Important Notes

- The vault path is currently hardcoded to `hyphora-vault` directory
- No test suite exists yet - consider adding pytest when implementing tests
- Vector embeddings are 768-dimensional (likely for future OpenAI/similar embeddings)
- The project uses modern Python tooling: UV for packages, Hatchling for builds

