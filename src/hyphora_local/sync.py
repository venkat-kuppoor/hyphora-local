import sqlite3
from datetime import datetime

from .config import HyphoraConfig


def sync_vault_to_database(config: HyphoraConfig) -> tuple[int, int, int]:
    """
    Sync markdown files from the vault directory to the database.

    Returns a tuple of (inserted, updated, deleted) counts.
    """
    inserted = 0
    updated = 0
    deleted = 0

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
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get all existing documents from database
        cursor.execute("SELECT id, title, modified_at FROM vault")
        db_documents = {
            row["title"]: {"id": row["id"], "modified_at": row["modified_at"]}
            for row in cursor.fetchall()
        }

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
                    updated += 1
            else:
                # New document - insert it
                cursor.execute(
                    "INSERT INTO vault (title, content, modified_at) VALUES (?, ?, ?)",
                    (title, file_info["content"], file_info["modified_at"]),
                )
                inserted += 1

        conn.commit()

    finally:
        conn.close()

    return inserted, updated, deleted
