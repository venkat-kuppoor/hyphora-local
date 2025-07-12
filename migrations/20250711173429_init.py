"""
This module contains a Caribou migration.

Migration Name: init
Migration Version: 20250711173429
"""

import sqlite3


def upgrade(connection: sqlite3.Connection):
    sql = """
            CREATE TABLE vault (
                id INTEGER PRIMARY KEY,
                title TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                modified_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE vault_fts USING fts5(
                title,
                content,
                content='vault',
                content_rowid='id'
            );

            CREATE VIRTUAL TABLE vault_vec USING vec0(
                id INTEGER PRIMARY KEY,
                embedding VECTOR(768)
            );

            CREATE TABLE links (
                id INTEGER PRIMARY KEY,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                FOREIGN KEY (source_id) REFERENCES vault(id),
                FOREIGN KEY (target_id) REFERENCES vault(id)
            );


            CREATE TRIGGER vault_ai AFTER INSERT ON vault BEGIN
                INSERT INTO vault_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;

            CREATE TRIGGER vault_au AFTER UPDATE ON vault BEGIN
                UPDATE vault_fts SET title = new.title, content = new.content
                WHERE rowid = old.id;
            END;


            CREATE TRIGGER vault_ad AFTER DELETE ON vault BEGIN
                DELETE FROM vault_fts WHERE rowid = old.id;
            END;


            CREATE TRIGGER vault_vec_ad AFTER DELETE ON vault BEGIN
                DELETE FROM vault_vec WHERE id = old.id;
            END;
            """
    _ = connection.execute(sql)


def downgrade(connection: sqlite3.Connection):
    _ = connection.execute("drop table animals")
