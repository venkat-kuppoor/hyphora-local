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
hyphora-local analyze-vault
hyphora-local find-links <file_path>
hyphora-local link-stats
```

### Database Migrations

```bash
# Run migrations using caribou
caribou migrate migrations
```

## Architecture Overview

**hyphora-local** is a Python CLI application that analyzes markdown vaults (similar to Obsidian) to extract and
analyze wiki-style links between documents.

### Core Components

1. **CLI Interface** (`src/hyphora_local/cli.py`):

   - Built with Typer framework
   - Three main commands: `analyze-vault`, `find-links`, `link-stats`
   - Entry point is the `main()` function in `__init__.py`

2. **Configuration** (`src/hyphora_local/config.py`):

   - Uses functional error handling with result types
   - Reads from `hyphora.toml` in project root
   - Configuration includes vault path and database path
   - Pattern: `ConfigResult = tuple[Config | None, list[str]]`

3. **Graph Analysis** (`src/hyphora_local/graph.py`):

   - Extracts wiki links in formats: `[[Link]]`, `[[Link|Display]]`, `[[Link#Section]]`
   - Uses NetworkX for graph operations
   - Analyzes link relationships, connectivity, and statistics

4. **Database Schema** (defined in `migrations/`):
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

