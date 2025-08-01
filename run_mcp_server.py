#!/usr/bin/env python
"""Entry point for running the MCP server."""

from src.hyphora_local.server import mcp

if __name__ == "__main__":
    mcp.run()