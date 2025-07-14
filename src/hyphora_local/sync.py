import sqlite3
from datetime import datetime
from typing import Callable, cast

import ollama  # type: ignore[import-untyped]
import sqlite_vec  # type: ignore[import-untyped]
from .config import HyphoraConfig
from .graph import extract_wiki_links


def generate_embedding(
    text: str, model: str = "nomic-embed-text"
) -> list[float] | None:
    """Generate embedding for text using ollama. Returns None for very short texts."""
    # Skip empty or very short texts
    if not text or len(text.strip()) < 10:
        return None

    try:
        response = ollama.embeddings(model=model, prompt=text)  # type: ignore[no-untyped-call]
        embedding = response.get("embedding", [])  # type: ignore[no-any-return]

        if not embedding:
            return None

        # Validate dimensions
        if len(embedding) != 768:
            raise ValueError(
                f"Expected 768-dimensional embedding, got {len(embedding)} dimensions"
            )

        return embedding  # type: ignore[no-any-return]
    except Exception as e:
        if "OLLAMA_HOST" in str(e) or "connect" in str(e).lower():
            raise RuntimeError(
                "Failed to connect to Ollama. Make sure Ollama is running with: ollama serve"
            )
        raise RuntimeError(f"Failed to generate embedding: {e}")


def extract_and_store_links(cursor: sqlite3.Cursor) -> int:
    """Extract wiki links from all documents and store in links table."""
    # Clear existing links
    cursor.execute("DELETE FROM links")
    
    # Get all documents with their content
    cursor.execute("SELECT id, title, content FROM vault")
    documents = cursor.fetchall()
    
    links_added = 0
    
    for doc in documents:
        source_id = cast(int, doc["id"])
        content = cast(str, doc["content"])
        
        # Extract wiki links from content
        wiki_links = extract_wiki_links(content)
        
        for link_text in wiki_links:
            # Try to find the target document by title
            # Look for exact matches first, then try with .md extension
            cursor.execute("SELECT id FROM vault WHERE title = ? OR title = ?", 
                          (link_text, f"{link_text}.md"))
            target_row = cursor.fetchone()
            
            if target_row:
                target_id = cast(int, target_row["id"])
                # Insert the link relationship
                cursor.execute(
                    "INSERT OR IGNORE INTO links (source_id, target_id) VALUES (?, ?)",
                    (source_id, target_id)
                )
                links_added += 1
    
    return links_added


def sync_vault_to_database(
    config: HyphoraConfig,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[int, int, int, int, int]:
    """
    Sync markdown files from the vault directory to the database.

    Returns a tuple of (inserted, updated, deleted, embeddings_generated, links_extracted) counts.
    """
    inserted = 0
    updated = 0
    deleted = 0
    embeddings_generated = 0
    links_extracted = 0

    # Get all markdown files from the vault
    vault_files: dict[str, dict[str, str]] = {}
    for file_path in config.vault_path.rglob("*.md"):
        relative_path = file_path.relative_to(config.vault_path)
        title = str(relative_path)

        # Get file metadata
        stat = file_path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        vault_files[title] = {
            "content": content,
            "modified_at": modified_at,
        }

    # Connect to database
    conn = sqlite3.connect(config.db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)  # type: ignore[no-untyped-call]
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get all existing documents from database
        cursor.execute("SELECT id, title, modified_at FROM vault")
        db_documents = {
            row["title"]: {"id": row["id"], "modified_at": row["modified_at"]}
            for row in cursor.fetchall()
        }

        # Track which documents need new embeddings
        docs_needing_embeddings: list[int] = []

        # Find documents to delete (in DB but not in filesystem)
        for title, doc_info in db_documents.items():
            if title not in vault_files:
                cursor.execute("DELETE FROM vault WHERE id = ?", (doc_info["id"],))
                deleted += 1

        # Process files in vault
        for title, file_info in vault_files.items():
            if title in db_documents:
                # Document exists in DB - check if it needs updating
                db_modified = db_documents[title]["modified_at"]
                if file_info["modified_at"] > db_modified:
                    cursor.execute(
                        "UPDATE vault SET content = ?, modified_at = ? WHERE title = ?",
                        (file_info["content"], file_info["modified_at"], title),
                    )
                    doc_id = cast(int, db_documents[title]["id"])
                    docs_needing_embeddings.append(doc_id)
                    updated += 1
            else:
                # New document - insert it
                cursor.execute(
                    "INSERT INTO vault (title, content, modified_at) VALUES (?, ?, ?)",
                    (title, file_info["content"], file_info["modified_at"]),
                )
                last_id = cursor.lastrowid
                if last_id is not None:
                    docs_needing_embeddings.append(last_id)
                inserted += 1

        conn.commit()

        # Phase 2: Generate embeddings for new/updated documents
        # First check for any documents missing embeddings
        cursor.execute("""
            SELECT v.id, v.content, v.title
            FROM vault v 
            LEFT JOIN vault_vec vv ON v.id = vv.id 
            WHERE vv.id IS NULL
        """)
        missing_embeddings = cursor.fetchall()

        # Combine all documents needing embeddings
        all_docs_needing_embeddings: list[sqlite3.Row] = []

        # Add newly inserted/updated documents
        for doc_id in docs_needing_embeddings:
            cursor.execute(
                "SELECT id, content, title FROM vault WHERE id = ?", (doc_id,)
            )
            row = cursor.fetchone()
            if row:
                all_docs_needing_embeddings.append(row)

        # Add documents missing embeddings
        all_docs_needing_embeddings.extend(missing_embeddings)

        if all_docs_needing_embeddings:
            # Get existing embeddings to know if we need to update or insert
            cursor.execute("SELECT id FROM vault_vec")
            existing_embeddings = {row["id"] for row in cursor.fetchall()}

            total = len(all_docs_needing_embeddings)
            for i, row in enumerate(all_docs_needing_embeddings):
                doc_id = cast(int, row["id"])
                content = cast(str, row["content"])
                title = cast(str, row["title"])

                if progress_callback:
                    progress_callback(
                        i + 1, total, f"Generating embedding for: {title}"
                    )

                # Generate embedding
                embedding = generate_embedding(content)

                if embedding is not None:
                    embedding_bytes = sqlite_vec.serialize_float32(embedding)  # type: ignore[no-untyped-call]

                    if doc_id in existing_embeddings:
                        cursor.execute(
                            "UPDATE vault_vec SET embedding = ? WHERE id = ?",
                            (embedding_bytes, doc_id),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO vault_vec (id, embedding) VALUES (?, ?)",
                            (doc_id, embedding_bytes),
                        )

                    embeddings_generated += 1
                else:
                    # Skip documents with very short content
                    if progress_callback:
                        progress_callback(
                            i + 1, total, f"Skipping short document: {title}"
                        )

            conn.commit()
        
        # Phase 3: Extract and store wiki links
        if progress_callback:
            progress_callback(1, 1, "Extracting wiki links...")
        
        links_extracted = extract_and_store_links(cursor)
        conn.commit()

    finally:
        conn.close()

    return inserted, updated, deleted, embeddings_generated, links_extracted
