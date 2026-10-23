import os, json, uuid, datetime
from pathlib import Path
import requests
from pydantic import ValidationError
from app.schemas import QAGeneration

def _output_path():
    p=Path(os.getenv("OUTPUT_STORE_PATH", "./generated_output"))
    p.mkdir(parents=True, exist_ok=True)
    return p

def _call_llm(source_text: str, node_ids: list[str]) -> dict:
    api_key=os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured. Set it in .env before generation.")
    base=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    schema=QAGeneration.model_json_schema()
    prompt = f"""You are generating QA test ideas for a fictional medical device manual.
Use only the source text. Do not invent thresholds, timings, error codes, or behaviors.
If a necessary detail is missing, say so in rationale and avoid guessing.
Return 3 to 5 distinct executable test cases with preconditions, numbered steps,
expected_result, source_node_ids drawn only from this list: {node_ids}, risk_level, rationale.
Return JSON matching this schema: {json.dumps(schema)}
SOURCE TEXT:
{source_text}
"""
    errors=None
    for attempt in range(2):
        content=prompt if not errors else prompt + "\nYour previous response failed validation with these errors: " + errors + "\nReturn corrected JSON only."
        response=requests.post(base + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"},
            json={"model":model,"temperature":0.2,"response_format":{"type":"json_object"},
                  "messages":[{"role":"system","content":"Return valid JSON only."},{"role":"user","content":content}]},
            timeout=90)
        response.raise_for_status()
        raw=response.json()["choices"][0]["message"]["content"]
        try:
            data=json.loads(raw)
            validated=QAGeneration.model_validate(data)
            return {"data": validated.model_dump(), "model": model, "attempts": attempt+1}
        except (json.JSONDecodeError, ValidationError) as e:
            errors=str(e)
    raise RuntimeError("LLM response failed structured validation after 2 attempts: " + (errors or "unknown error"))

def save_generation(selection_id: str, snapshot: dict, source_text: str, node_ids: list[str]):
    result=_call_llm(source_text, node_ids)
    generation_id=str(uuid.uuid4())
    record={"generation_id":generation_id,"selection_id":selection_id,"created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_snapshot":snapshot,"source_node_ids":node_ids,"model":result["model"],"attempts":result["attempts"],
            "test_cases":result["data"]["test_cases"]}
    (_output_path()/f"{generation_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record

def list_generations(selection_id=None, node_id=None):
    records=[]
    for p in _output_path().glob("*.json"):
        try: rec=json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        if selection_id and rec.get("selection_id") != selection_id: continue
        if node_id and node_id not in rec.get("source_node_ids", []): continue
        records.append(rec)
    return records
