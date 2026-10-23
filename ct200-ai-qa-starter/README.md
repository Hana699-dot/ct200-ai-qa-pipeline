# CT-200 AI QA Traceability API

PDF-first FastAPI backend for parsing the CardioTrack CT-200 manuals, preserving a versioned hierarchy, pinning selections to source text, generating structured QA test ideas, and exposing staleness at retrieval time.

## Setup

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

The supplied PDFs are intentionally not committed by default. Ingest them through `POST /documents/ingest` as multipart PDF uploads. The first ingested file becomes version 1 and the next becomes version 2 of document `ct200`.

## LLM setup

Set `LLM_API_KEY`, `LLM_MODEL`, and optionally `LLM_BASE_URL` in `.env`. The default uses a Groq-compatible OpenAI chat-completions endpoint. Generation fails clearly without a key; it does not silently store fake output. JSON is validated against Pydantic, with one repair retry.

## Main endpoints

- `POST /documents/ingest` — upload a PDF.
- `GET /documents/ct200/sections?version=1` — browse a version (omitting version chooses latest).
- `GET /nodes/{node_id}` — node details and children.
- `GET /nodes/search?q=battery&version=1` — search headings/body.
- `GET /nodes/{node_id}/changes` — compare a node to the latest logical match.
- `POST /selections` — JSON `{ "name": "Battery QA", "node_ids": ["..."] }`.
- `GET /selections/{selection_id}` — exact pinned source snapshot.
- `POST /selections/{selection_id}/generate` — create a generation.
- `GET /test-cases?selection_id=...` or `GET /test-cases?node_id=...` — retrieve output with staleness metadata.

## v1 → v2 demonstration

1. Start the API and upload `ct200_manual.pdf` to `POST /documents/ingest`.
2. Browse version 1 and save node IDs for a section whose text changes, such as Battery Life or Cuff Inflation.
3. Create a selection using those version-1 node IDs and save the returned selection ID.
4. Configure the LLM environment variables and call `POST /selections/{selection_id}/generate`.
5. Upload `ct200_manual_v2.pdf` to the same ingestion endpoint. It becomes version 2.
6. Retrieve the old selection. Its snapshot still contains the exact v1 text and hashes.
7. Retrieve `GET /test-cases?selection_id=...`. The response includes `staleness` based on comparison with latest logical nodes.

## Parsing decisions and known limitations

- Uses embedded PDF text with PyMuPDF first; pages without extractable text are marked `OCR_REQUIRED_PAGE_n`. Tesseract/OCR integration is not enabled in this first version.
- Heading numbering and parent paths are used for hierarchy. Missing intermediate levels attach to the nearest existing numeric prefix. Duplicate heading text is not used as a unique key.
- Table-like cells are preserved as typed text blocks; full grid reconstruction is not guaranteed.
- The manuals have out-of-order 3.4/3.3 headings and a 2.1.1.1 heading without a visible 2.1.1 parent. Regression tests cover these patterns.
- Matching uses full hierarchy path + normalized heading. This is explainable and conservative, but a move/rename can look like a new node. Identical headings under different parents remain separate.
- Staleness uses source content hashes. It flags potential staleness, not clinical invalidity; it cannot decide whether a changed threshold invalidates a particular generated test case.
- Generated results are stored as JSON documents under `OUTPUT_STORE_PATH` as a justified lightweight NoSQL-like store for this assignment. For multi-process/production deployment, use MongoDB and atomic writes/indexes.
- Each explicit generation request creates a new generation record; duplicate requests do not overwrite prior output.

## Tests

```bash
pytest -q
```

## Safety note

This is an engineering demonstration for a fictional device manual, not a validated medical-device QA system. Generated test ideas require qualified review before use.
