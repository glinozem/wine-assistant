# api/schemas.py

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SimpleSearchParams(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    max_price: float | None = Field(default=None, ge=0)
    color: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("q")
    @classmethod
    def q_min_len(cls, v: str | None):
        if v is None:
            return v
        v2 = v.strip()
        if v2 and len(v2) < 2:
            raise ValueError("q must be at least 2 characters")
        return v2 or None


class CatalogSort(str, Enum):
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"
    CODE_ASC = "code_asc"
    CODE_DESC = "code_desc"


class CatalogSearchParams(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    grapes: str | None = Field(default=None, max_length=100)

    in_stock: bool = False

    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)

    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=10, ge=1, le=100)

    sort: CatalogSort | None = None

    @field_validator("q")
    @classmethod
    def q_min_len(cls, v: str | None):
        if v is None:
            return v
        v2 = v.strip()
        if v2 and len(v2) < 2:
            raise ValueError("q must be at least 2 characters")
        return v2 or None

    @model_validator(mode="after")
    def _check_price_range(self):
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price must be <= max_price")
        return self


class DateRangeParams(BaseModel):
    """
    Базовая модель для параметров с диапазоном дат (from/to + limit/offset).
    Используется для history-эндпоинтов.
    """

    dt_from: Optional[date] = Field(None, alias="from")
    dt_to: Optional[date] = Field(None, alias="to")
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0, le=100_000)

    @model_validator(mode="after")
    def _check_range(self):
        if self.dt_from and self.dt_to and self.dt_from > self.dt_to:
            raise ValueError("'from' must be <= 'to'")
        return self


class PriceHistoryParams(DateRangeParams):
    """Query params for price history endpoint."""


class InventoryHistoryParams(DateRangeParams):
    """Query params for inventory history endpoint."""
