Hyphora DB is a SQLite database with extensions for Full Text Search (via FTS5) and Vector Similarity Search (via sqlite-vec).

## Schema
Vault
- Table that contains markdown documents
- Columns
	- doc_id is the primary key
	- title
	- body
	- title_embedding
	- body_embedding
	- modified at

## Migrations
We use a simple python library called caribou built primarily to manage the evolution of client side databases over multiple releases of an application.

Migrations files will be in the migrations directory of the source code for Hyphora