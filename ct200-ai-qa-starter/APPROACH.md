# CT-200 PDF Parsing, Versioning and QA Generation — Approach

## 1. Input inspection

The provided inputs are `ct200_manual.pdf` (6 pages) and `ct200_manual_v2.pdf` (7 pages). PyMuPDF inspection found embedded selectable text on every page and no embedded raster images in the inspected files, so the initial path uses native PDF text extraction rather than running OCR unconditionally. The extractor records per-page character counts and image counts. OCR is explicitly marked as required if a page has no extractable text; the initial version does not automatically invoke Tesseract.

Observed variations include:
- Section 3.4 appears before 3.3 in both versions.
- Heading `2.1.1.1 Battery Life Under Typical Use` appears without an explicit `2.1.1` heading.
- Tables are exposed by text extraction as stacked cell text rather than reliable row/column geometry.
- Text and paragraphs continue across page boundaries.
- V2 adds an E6 row and Section 5.3 Data Export.
- Content changes include battery cycle estimate, low-battery threshold, inflation increment and E3 response timing.

## 2. Extraction and hierarchy

PyMuPDF `page.get_text("dict")` provides line text, font size and bounding boxes. Lines are ordered top-to-bottom and left-to-right. Numbered headings are detected with a numeric-section regex. The numeric depth supplies the heading level; parent selection uses the closest existing numbered prefix. This means a missing intermediate heading is not fabricated, and 3.3 remains a sibling of 3.4 rather than becoming its child merely because it appears later in the PDF.

Each node stores heading, level, section number, body text, parent ID, page range, content blocks and SHA-256 content hash. List lines are retained in body text and marked as list blocks. Table cells are retained as typed cells instead of being silently discarded, but exact cell alignment is not guaranteed.

## 3. What the initial implementation does not fully handle

The current parser is deliberately scoped to the two CT-200 manuals:
- It does not automatically OCR scanned pages; it marks them for attention.
- It does not reconstruct a robust cell grid for complex tables.
- It does not distinguish every possible header/footer from body text.
- It uses section numbering as a strong structural signal; unnumbered headings and ambiguous numbering require manual review.
- The title is retained as a document title, but title/body separation may need improvement for unusual cover pages.

These limitations are surfaced in output or documentation rather than presented as guaranteed-correct parsing.

## 4. Version matching

Nodes are matched by their full hierarchy path and normalized heading. This handles identical heading labels under different parents and is easy to explain during review. Each version receives its own physical node IDs; matching nodes share a logical node ID across versions. Body hashes identify changed content.

Known failure mode: if a section is moved or renamed, the path changes and it may be treated as a new logical node. A production improvement would combine numbering/path, fuzzy title similarity and body similarity, then require manual review for ambiguous matches rather than force a match.

## 5. Selection and generated output persistence

Selections store a snapshot of exact node IDs, version IDs, headings, body text and hashes. Re-ingestion does not mutate the snapshot. Each generation is a separate JSON document in a local JSON store, linked to its selection and source snapshot. This is the justified lightweight alternative to MongoDB for a single-user assignment; MongoDB would be preferable for concurrent deployment and indexing.

Repeated generation requests create distinct records to preserve audit history. LLM output is validated using Pydantic, with a single retry after a malformed/incomplete response. If validation still fails, the API returns a generation error and does not persist the response as a successful generation.

## 6. Staleness

At retrieval, source logical node IDs and hashes are compared with the latest ingested version. The response reports `current` or `potentially_stale`, with per-node change reasons. A hash difference is evidence that source content changed, not proof that a specific test case is clinically invalid. The implementation conservatively flags the generation; it does not automatically regenerate test cases.

## 7. Validation and debugging

Tests cover duplicate headings under different parents, a missing intermediate numbering level, out-of-order siblings and changed content hashes. A further integration pass should compare every extracted heading and table against rendered page images and run the full v1-selection-generation-v2-retrieval workflow with a configured LLM key.

## 8. Decision log

### Most likely silent wrong result
Hierarchy reconstruction is the highest-risk silent failure: correct text can still be attached to the wrong parent. Catch it with parent-child invariant checks, regression fixtures for the observed 3.4/3.3 ordering and missing 2.1.1 level, plus visual comparison against PDF pages.

### Simplicity chosen over correctness
I chose exact path + normalized heading matching rather than semantic/fuzzy matching. It is auditable and avoids many false matches, but moves and renames can appear as removed/new nodes. Hash-based staleness also over-flags harmless edits and cannot determine clinical impact.

### An input not fully handled
A scanned page without embedded text is not OCRed automatically in this version. It is marked `OCR_REQUIRED_PAGE_n` and should be reviewed rather than silently treated as empty content. Complex multi-page tables are also retained as text cells without claiming reliable grid reconstruction.

## 9. Future work

Add optional Tesseract OCR with confidence scores; geometric table reconstruction; page-header/footer classification; visual regression artifacts; fuzzy matching with ambiguity review; MongoDB storage; per-test-case requirement dependencies; richer text diffs; and integration tests for LLM retries and complete versioning flow.
