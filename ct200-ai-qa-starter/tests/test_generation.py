import pytest
from pydantic import ValidationError
from app.schemas import QAGeneration

def test_malformed_generation_is_rejected():
    with pytest.raises(ValidationError):
        QAGeneration.model_validate({"test_cases":[{"title":"incomplete"}]})
