from app.models import Node, DocumentVersion

def generation_staleness(db, record):
    latest = db.query(DocumentVersion).filter_by(document_id="ct200").order_by(DocumentVersion.version_number.desc()).first()
    if latest is None:
        return {"status":"unknown","reason":"No document version is ingested."}
    current_nodes = db.query(Node).filter_by(version_id=latest.id).all()
    by_logical = {n.logical_node_id:n for n in current_nodes}
    changes=[]
    for source in record.get("source_snapshot", []):
        logical=source.get("logical_node_id")
        current=by_logical.get(logical)
        if current is None:
            changes.append({"node_id":source.get("node_id"),"change":"removed_or_unmatched"})
        elif current.content_hash != source.get("content_hash"):
            changes.append({"node_id":source.get("node_id"),"change":"content_changed",
                            "latest_node_id":current.id,"latest_hash":current.content_hash})
    if not changes:
        return {"status":"current","latest_version":latest.version_number,"changes":[]}
    return {"status":"potentially_stale","latest_version":latest.version_number,"changes":changes,
            "limitation":"Hash changes identify source changes, not whether each test case is clinically invalid."}
