from pydantic import BaseModel, Field
from typing import Literal

class SelectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    node_ids: list[str] = Field(min_length=1)

class QATestCase(BaseModel):
    title: str = Field(min_length=3)
    preconditions: list[str]
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=3)
    source_node_ids: list[str] = Field(min_length=1)
    risk_level: Literal["low", "medium", "high"]
    rationale: str

class QAGeneration(BaseModel):
    test_cases: list[QATestCase] = Field(min_length=3, max_length=5)
