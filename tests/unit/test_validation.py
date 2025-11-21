# tests/unit/test_validation.py
from flask import Flask
from pydantic import BaseModel, Field

from api.validation import validate_query_params

app = Flask(__name__)


class DummyParams(BaseModel):
    x: int = Field(ge=0)
    y: str | None = None


def test_validate_query_params_ok():
    """
    validate_query_params должен вернуть модель и error=None,
    если query-параметры валидны.
    """
    with app.test_request_context("/dummy?x=10&y=hello"):
        params, error = validate_query_params(DummyParams)

    assert error is None
    assert isinstance(params, DummyParams)
    assert params.x == 10
    assert params.y == "hello"


def test_validate_query_params_error():
    """
    При невалидных параметрах validate_query_params должен вернуть
    (None, (Response, 400)) с JSON в формате validation_error.
    """
    # x обязателен и должен быть int >= 0, поэтому "foo" сломает валидацию
    with app.test_request_context("/dummy?x=foo"):
        params, error = validate_query_params(DummyParams)

    assert params is None
    assert error is not None

    resp, status = error
    assert status == 400

    data = resp.get_json()
    assert data["error"] == "validation_error"
    assert isinstance(data["details"], list)
    assert data["details"], "Ожидаем хотя бы одну запись об ошибке"

    first = data["details"][0]
    assert "loc" in first
    assert "msg" in first
    assert "type" in first
