import json, uuid, datetime
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
from app.models import Document, DocumentVersion, Node, Selection
from app.schemas import SelectionCreate
from app.services.ingestion import ingest_pdf
from app.services.generation import save_generation, list_generations
from app.services.staleness import generation_staleness

Base.metadata.create_all(bind=engine)
app=FastAPI(title="CT-200 AI QA Traceability API", version="0.1.0")

def _node_out(n, db, include_children=True):
    data={"id":n.id,"logical_node_id":n.logical_node_id,"version_id":n.version_id,"heading":n.heading,
          "section_number":n.section_number,"level":n.level,"parent_id":n.parent_id,"body_text":n.body_text,
          "content_hash":n.content_hash,"page_start":n.page_start,"page_end":n.page_end,
          "content_blocks":json.loads(n.content_blocks_json or "[]")}
    if include_children:
        data["children"]=[_node_out(x,db,False) for x in db.query(Node).filter_by(version_id=n.version_id,parent_id=n.id).all()]
    return data

@app.get("/health")
def health():
    return {"status":"ok"}

@app.post("/documents/ingest")
async def ingest(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF input is supported.")
    temp=Path("data_uploads"); temp.mkdir(exist_ok=True)
    dest=temp/(str(uuid.uuid4())+"_"+Path(file.filename).name)
    dest.write_bytes(await file.read())
    try:
        return ingest_pdf(db, str(dest))
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {e}")

@app.get("/documents/{document_id}/sections")
def sections(document_id: str="ct200", version: int|None=None, db: Session=Depends(get_db)):
    q=db.query(DocumentVersion).filter_by(document_id=document_id)
    versions=q.order_by(DocumentVersion.version_number.desc()).all()
    if not versions: raise HTTPException(404,"Document not found")
    chosen=next((v for v in versions if v.version_number==version), versions[0] if version is None else None)
    if chosen is None: raise HTTPException(404,"Version not found")
    roots=db.query(Node).filter_by(version_id=chosen.id,parent_id=None).all()
    return {"document_id":document_id,"version":chosen.version_number,"sections":[_node_out(n,db) for n in roots]}

@app.get("/nodes/{node_id}")
def get_node(node_id: str, db: Session=Depends(get_db)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    return _node_out(n,db)

@app.get("/nodes/search")
def search_nodes(q: str=Query(min_length=1), version: int|None=None, db: Session=Depends(get_db)):
    vq=db.query(DocumentVersion).filter_by(document_id="ct200")
    versions=vq.order_by(DocumentVersion.version_number.desc()).all()
    if not versions: return {"results":[]}
    chosen=next((v for v in versions if v.version_number==version),versions[0] if version is None else None)
    if chosen is None: raise HTTPException(404,"Version not found")
    matches=db.query(Node).filter(Node.version_id==chosen.id).filter(
        (Node.heading.ilike(f"%{q}%")) | (Node.body_text.ilike(f"%{q}%"))).all()
    return {"version":chosen.version_number,"results":[_node_out(n,db,False) for n in matches]}

@app.get("/nodes/{node_id}/changes")
def node_changes(node_id: str, db: Session=Depends(get_db)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    v=db.get(DocumentVersion,n.version_id)
    versions=db.query(DocumentVersion).filter_by(document_id=v.document_id).order_by(DocumentVersion.version_number).all()
    latest=versions[-1]
    current=next((x for x in db.query(Node).filter_by(version_id=latest.id).all() if x.logical_node_id==n.logical_node_id),None)
    if current is None: return {"changed":True,"status":"removed_or_unmatched","source_version":v.version_number,"latest_version":latest.version_number}
    return {"changed":n.content_hash!=current.content_hash,"source_version":v.version_number,
            "latest_version":latest.version_number,"source_hash":n.content_hash,"latest_hash":current.content_hash,
            "diff_summary":"Content hash differs; inspect source text for detailed diff." if n.content_hash!=current.content_hash else "No content change detected."}

@app.post("/selections")
def create_selection(payload: SelectionCreate, db: Session=Depends(get_db)):
    nodes=[db.get(Node,nid) for nid in payload.node_ids]
    if any(n is None for n in nodes): raise HTTPException(404,"One or more node IDs were not found.")
    versions={n.version_id for n in nodes}
    if len(versions)!=1: raise HTTPException(400,"All selected nodes must belong to the same document version.")
    snapshot=[{"node_id":n.id,"logical_node_id":n.logical_node_id,"version_id":n.version_id,
               "heading":n.heading,"body_text":n.body_text,"content_hash":n.content_hash} for n in nodes]
    sid=str(uuid.uuid4())
    sel=Selection(id=sid,name=payload.name,created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  snapshot_json=json.dumps(snapshot,ensure_ascii=False))
    db.add(sel); db.commit()
    return {"selection_id":sid,"name":payload.name,"version_id":next(iter(versions)),"snapshot":snapshot}

@app.get("/selections/{selection_id}")
def get_selection(selection_id: str, db: Session=Depends(get_db)):
    s=db.get(Selection,selection_id)
    if not s: raise HTTPException(404,"Selection not found")
    return {"selection_id":s.id,"name":s.name,"created_at":s.created_at,"snapshot":json.loads(s.snapshot_json)}

@app.post("/selections/{selection_id}/generate")
def generate(selection_id: str, db: Session=Depends(get_db)):
    s=db.get(Selection,selection_id)
    if not s: raise HTTPException(404,"Selection not found")
    snapshot=json.loads(s.snapshot_json)
    text="\n\n".join(f"{x['heading']}\n{x['body_text']}" for x in snapshot)
    try:
        return save_generation(selection_id,snapshot,text,[x["node_id"] for x in snapshot])
    except Exception as e:
        raise HTTPException(502, f"Generation failed; no successful output stored: {e}")

@app.get("/test-cases")
def get_test_cases(selection_id: str|None=None, node_id: str|None=None, db: Session=Depends(get_db)):
    if not selection_id and not node_id: raise HTTPException(400,"Provide selection_id or node_id.")
    records=list_generations(selection_id,node_id)
    return {"results":[{**r,"staleness":generation_staleness(db,r)} for r in records]}
