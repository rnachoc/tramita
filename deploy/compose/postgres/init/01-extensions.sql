-- Runs once, when the PostgreSQL volume is first initialised.
-- pgvector stores the policy clause embeddings next to the core data.
CREATE EXTENSION IF NOT EXISTS vector;
