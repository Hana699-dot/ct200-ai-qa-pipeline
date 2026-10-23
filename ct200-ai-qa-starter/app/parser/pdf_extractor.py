"""PDF-first extraction. Uses embedded text first; OCR is intentionally an optional fallback."""
import re
import unicodedata
import hashlib
from pathlib import Path
import fitz

HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*(?:\d+[.)]|[-•▪])\s+")
TABLE_HEADER_WORDS = {"parameter", "value", "code", "meaning", "device behavior"}

def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace("\\u00ad", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()

def content_hash(heading: str, body: str, blocks=None) -> str:
    payload = normalize_text(heading).casefold() + "\n" + normalize_text(body)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _line_blocks(page, page_number):
    """Return ordered text lines with font metadata; avoid OCR unless no usable text exists."""
    data = page.get_text("dict")
    out = []
    for block in data.get("blocks", []):
        if "lines" not in block:
            continue
        for line in block["lines"]:
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            size = max((s.get("size", 0) for s in spans), default=0)
            bbox = line.get("bbox", [0, 0, 0, 0])
            out.append({"text": text, "page": page_number, "font_size": size,
                        "bbox": bbox, "kind": "text"})
    # PyMuPDF dict order is usually visual order. Sort by vertical then horizontal position.
    out.sort(key=lambda x: (round(x["bbox"][1], 1), x["bbox"][0]))
    return out

def extract_pdf(path: str) -> dict:
    path = str(path)
    doc = fitz.open(path)
    all_lines = []
    page_text_stats = []
    for idx, page in enumerate(doc, start=1):
        lines = _line_blocks(page, idx)
        page_text_stats.append({"page": idx, "characters": len(page.get_text("text").strip()),
                                "image_count": len(page.get_images())})
        if not page.get_text("text").strip():
            # Explicitly expose unsupported OCR rather than silently producing an empty tree.
            all_lines.append({"text": f"[OCR_REQUIRED_PAGE_{idx}]", "page": idx,
                              "font_size": 0, "bbox": [0,0,0,0], "kind": "unsupported"})
        else:
            all_lines.extend(lines)
    return {"title": "CardioTrack CT-200 Home Blood Pressure Monitor — Technical & User Manual",
            "lines": all_lines, "page_stats": page_text_stats, "page_count": len(doc)}

def classify_line(line):
    text = normalize_text(line["text"])
    if not text:
        return "empty"
    if text.startswith("[OCR_REQUIRED_PAGE_"):
        return "unsupported"
    if HEADING_RE.match(text):
        return "heading"
    if LIST_RE.match(text):
        return "list_item"
    # Tables in these manuals are text-based and extracted as stacked cells.
    if text.casefold() in TABLE_HEADER_WORDS:
        return "table_cell"
    return "paragraph"

def reconstruct_tree(extracted: dict) -> list[dict]:
    """Build nodes; section-number prefixes determine parent where possible.
    Missing numbering levels attach to the nearest existing prefix. Unnumbered content is retained.
    """
    lines = extracted["lines"]
    nodes = []
    stack = []
    current = None
    pending = []
    title = extracted.get("title", "Document")

    def flush_pending():
        nonlocal pending, current
        if current is not None and pending:
            text = normalize_text(" ".join(x["text"] for x in pending))
            if text:
                current["body_text"] = (current["body_text"] + "\n" + text).strip()
                current["page_end"] = pending[-1]["page"]
                current["content_blocks"].append({
                    "type": "list" if any(classify_line(x) == "list_item" for x in pending) else "paragraph",
                    "text": text,
                    "page_start": pending[0]["page"],
                    "page_end": pending[-1]["page"]
                })
        pending = []

    for line in lines:
        text = normalize_text(line["text"])
        kind = classify_line(line)
        if kind == "heading":
            flush_pending()
            m = HEADING_RE.match(text)
            number = m.group(1).rstrip(".")
            label = m.group(2).strip()
            parts = number.split(".")
            level = len(parts)
            # A malformed/deep heading is retained; missing numeric parents are not fabricated.
            parent = None
            for candidate in reversed(stack):
                if number.startswith(candidate["section_number"] + "."):
                    parent = candidate
                    break
                if len(candidate["section_number"].split(".")) < level and number.startswith(candidate["section_number"] + "."):
                    parent = candidate
                    break
            node = {
                "heading": f"{number} {label}", "section_number": number, "level": level,
                "parent_ref": parent, "body_text": "", "page_start": line["page"],
                "page_end": line["page"], "content_blocks": []
            }
            nodes.append(node)
            # Stack keeps only ancestors that can parent the next numeric section.
            stack = [n for n in stack if number.startswith(n["section_number"] + ".")]
            stack.append(node)
            current = node
        elif kind == "unsupported":
            flush_pending()
            if current is None:
                current = {"heading": "Unparsed content", "section_number": None, "level": 1,
                           "parent_ref": None, "body_text": "", "page_start": line["page"],
                           "page_end": line["page"], "content_blocks": []}
                nodes.append(current)
            current["content_blocks"].append({"type": "unsupported", "text": text, "page_start": line["page"]})
        else:
            if current is None:
                current = {"heading": title, "section_number": None, "level": 0,
                           "parent_ref": None, "body_text": "", "page_start": line["page"],
                           "page_end": line["page"], "content_blocks": []}
                nodes.append(current)
            # Keep table-like cell lines as individual typed blocks; do not pretend to know row alignment.
            if kind == "table_cell":
                flush_pending()
                current["content_blocks"].append({"type": "table_cell", "text": text,
                                                  "page_start": line["page"], "page_end": line["page"]})
                current["body_text"] = (current["body_text"] + "\n" + text).strip()
            else:
                pending.append(line)
    flush_pending()

    # Flatten references into node indices and attach parents by identity, not heading text.
    idx_by_obj = {id(n): i for i, n in enumerate(nodes)}
    for i, n in enumerate(nodes):
        parent = n.pop("parent_ref", None)
        n["parent_index"] = idx_by_obj.get(id(parent)) if parent is not None else None
        n["children_indices"] = []
        n["content_hash"] = content_hash(n["heading"], n["body_text"], n["content_blocks"])
        n["node_index"] = i
    for n in nodes:
        if n["parent_index"] is not None:
            nodes[n["parent_index"]]["children_indices"].append(n["node_index"])
    return nodes
