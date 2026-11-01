# Corpus ingestion

Place UTF-8 Markdown/text or text-layer PDFs under `public/` or `municipal/`, then run `python -m scripts.seed` from the project virtual environment. Files remain unverified; an administrator reviews them through `/api/knowledge/docs` and `/verify`.

For accurate publisher, official URL, city, Hindi language, and expiry metadata, use the upload API rather than relying on seed defaults. Use actual official documents and labels for evaluation. No invented government content or automatically "verified" demo corpus is shipped.
