# api/validation.py
from typing import Optional, Tuple, Type, TypeVar

from flask import jsonify, request
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def serialize_validation_error(e: ValidationError) -> dict:
    """Превращает pydantic v2 ValidationError в JSON-безопасный словарь."""
    # Берём только безопасные поля без ctx (там могут быть несериализуемые объекты)
    details = [
        {
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        }
        for err in e.errors(include_url=False)
    ]
    return {"error": "validation_error", "details": details}


def validate_query_params(model: Type[T]) -> Tuple[Optional[T], Optional[tuple]]:
    """
    Валидирует request.args через переданную Pydantic-модель.

    Возвращает (params, error_response):
      * если всё ок: (params, None)
      * если валидация упала: (None, (jsonify(...), 400))

    error_response можно прямо return'нуть из вьюхи.
    """
    try:
        params = model.model_validate(request.args.to_dict(flat=True))
        return params, None
    except ValidationError as e:
        return None, (jsonify(serialize_validation_error(e)), 400)
