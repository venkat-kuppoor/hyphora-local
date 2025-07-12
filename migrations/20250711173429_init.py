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
                modified_at TEXT NOT NULL,
            );

            CREATE TABLE links (
                id INTEGER PRIMARY KEY,
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                FOREIGN KEY (from_id) REFERENCES vault(id),
                FOREIGN KEY (to_id) REFERENCES vault(id)
            );
            """
    _ = connection.execute(sql)


def downgrade(connection: sqlite3.Connection):
    _ = connection.execute("drop table animals")
