-- schema.sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  doc_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  filename TEXT NOT NULL,
  title TEXT,
  document_type TEXT,
  source TEXT, 
  page_count INTEGER,
  upload_date DATE,
  tags TEXT[]
);

CREATE TABLE IF NOT EXISTS document_chunks (
  chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  doc_id UUID REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_number INTEGER,
  section TEXT,
  chunk_text TEXT NOT NULL,
  tags TEXT[],
  created_at TIMESTAMP DEFAULT timezone('utc', now())
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id UUID PRIMARY KEY REFERENCES document_chunks(chunk_id) ON DELETE CASCADE,
  embedding vector(768)
);

CREATE TABLE IF NOT EXISTS retrieval_logs (
  log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  timestamp TIMESTAMP DEFAULT timezone('utc', now()),
  query TEXT,
  filters JSONB,
  matched_chunk_ids UUID[],
  agent_context TEXT
);
