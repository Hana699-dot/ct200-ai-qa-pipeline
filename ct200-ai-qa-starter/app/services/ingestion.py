import json, uuid, datetime, re
from pathlib import Path
from sqlalchemy.orm import Session
from app.models import Document, DocumentVersion, Node
from app.parser.pdf_extractor import extract_pdf, reconstruct_tree, normalize_text

def _logical_key(node):
    # Path + normalized heading is more discriminative than title alone.
    return (node["path"], normalize_text(node["heading"]).casefold())

def ingest_pdf(db: Session, path: str, document_id: str | None = None):
    extracted = extract_pdf(path)
    parsed = reconstruct_tree(extracted)
    document_id = document_id or "ct200"
    document = db.get(Document, document_id)
    if document is None:
        document = Document(id=document_id, name=extracted["title"])
        db.add(document)
        db.flush()
    prior_versions = db.query(DocumentVersion).filter_by(document_id=document_id).order_by(DocumentVersion.version_number).all()
    version_number = len(prior_versions) + 1
    version_id = str(uuid.uuid4())
    version = DocumentVersion(id=version_id, document_id=document_id, version_number=version_number,
                              source_filename=Path(path).name, created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    db.add(version)
    db.flush()

    # Build paths from parent indices, preserving duplicate headings under different parents.
    for n in parsed:
        p = n["parent_index"]
        n["path"] = (parsed[p]["path"] + " > " if p is not None else "") + n["heading"]
    old_nodes = []
    if prior_versions:
        old_nodes = db.query(Node).filter_by(version_id=prior_versions[-1].id).all()
    old_by_key = {}
    for old in old_nodes:
        old_by_key.setdefault((old._path if hasattr(old, "_path") else "", normalize_text(old.heading).casefold()), []).append(old)
    # Recover old paths from stored parent relationships.
    old_map = {x.id: x for x in old_nodes}
    def old_path(x):
        chain=[]; seen=set(); cur=x
        while cur and cur.id not in seen:
            seen.add(cur.id); chain.append(cur.heading)
            cur=old_map.get(cur.parent_id)
        return " > ".join(reversed(chain))
    old_by_key={}
    for old in old_nodes:
        old_by_key.setdefault((old_path(old), normalize_text(old.heading).casefold()), []).append(old)

    node_ids=[]
    for n in parsed:
        key=_logical_key(n)
        matches=old_by_key.get(key, [])
        logical_id=matches[0].logical_node_id if matches else str(uuid.uuid4())
        node_ids.append(str(uuid.uuid4()))
        n["logical_node_id"]=logical_id
    for n, node_id in zip(parsed, node_ids):
        parent_id=node_ids[n["parent_index"]] if n["parent_index"] is not None else None
        db.add(Node(id=node_id, logical_node_id=n["logical_node_id"], version_id=version_id,
                    parent_id=parent_id, heading=n["heading"], section_number=n["section_number"],
                    level=n["level"], body_text=n["body_text"], content_hash=n["content_hash"],
                    page_start=n["page_start"], page_end=n["page_end"],
                    content_blocks_json=json.dumps(n["content_blocks"], ensure_ascii=False)))
    db.commit()
    return {"document_id": document_id, "version_id": version_id, "version_number": version_number,
            "node_count": len(parsed), "page_count": extracted["page_count"],
            "page_stats": extracted["page_stats"], "warnings": [
                "Tables are preserved as typed text cells; complex row/column reconstruction is not guaranteed.",
                "Scanned pages without embedded text are marked OCR_REQUIRED and require OCR configuration."
            ]}
