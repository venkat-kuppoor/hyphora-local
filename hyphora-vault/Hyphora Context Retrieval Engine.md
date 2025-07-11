The following steps will take us through the process of how our engine takes a prompt and builds lightweight and efficient context sourced from the documentation in a [[Hyphora Vault]]
1. [[Embeddings]] will be created for a user's [[Prompt]].
2. [[Candidate Seed Selection]] is the first part of our context engine pipeline. The prompt embeddings in step 1 will be used to select candidate nodes in [[Link Graph]]
3. [[Subgraph Construction]]
4. [[Feature Extraction]]
5. [[Scoring Function]]
6. Rerank with Authority Detection
7. Prune and Select Final Context
8. Serialize for Prompting
