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


class ProductSearchItem(BaseModel):
    """
    Один товар в ответе /api/v1/products/search.

    Поля синхронизированы с SELECT в catalog_search и _normalize_product_row().
    """

    code: str
    name: str

    producer: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    color: Optional[str] = None
    style: Optional[str] = None

    grapes: Optional[str] = None
    vintage: Optional[int] = None

    price_list_rub: Optional[float] = None
    price_final_rub: Optional[float] = None

    stock_total: Optional[int] = None
    stock_free: Optional[int] = None

    vivino_rating: Optional[float] = None
    vivino_url: Optional[str] = None

    supplier: Optional[str] = None

    # новые поля, про которые мы дальше будем говорить в UI/экспорте
    producer_site: Optional[str] = None
    image_url: Optional[str] = None

    # ⚙️ новые поля из справочника wineries
    winery_name_ru: Optional[str] = None
    winery_description_ru: Optional[str] = None


class SkuResponse(BaseModel):
    """
    Карточка товара для `GET /api/v1/sku/<code>`.

    Поля синхронизированы с `_fetch_sku_row()` и `_normalize_product_row()`.
    """

    code: str

    # Заголовок из Excel / products.title_ru
    title_ru: Optional[str] = None
    # 🔧 Раньше было: name: str
    # Для тестовых SKU (INTTEST_...) продукта в справочнике может не быть,
    # поэтому name может оказаться None.
    name: Optional[str] = None


    producer: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    color: Optional[str] = None
    style: Optional[str] = None

    grapes: Optional[str] = None
    vintage: Optional[int] = None

    price_list_rub: Optional[float] = None
    price_final_rub: Optional[float] = None

    stock_total: Optional[int] = None
    stock_free: Optional[int] = None

    vivino_rating: Optional[float] = None
    vivino_url: Optional[str] = None

    supplier: Optional[str] = None
    producer_site: Optional[str] = None
    image_url: Optional[str] = None

    # ⚙️ поля из справочника wineries
    supplier_ru: Optional[str] = None
    winery_description_ru: Optional[str] = None

    @model_validator(mode="after")
    def _fill_title_ru(self):
        """
        Совместимость со старыми тестами/кодом:
        если title_ru не пришёл, используем name.
        """
        if self.title_ru is None:
            self.title_ru = self.name
        return self

class CatalogSearchResponse(BaseModel):
    """
    Ответ /api/v1/products/search.

    items — список товаров (ProductSearchItem),
    total — общее количество найденных,
    offset/limit — параметры пагинации,
    query — исходная строка поиска (может быть None).
    """

    items: list[ProductSearchItem]
    total: int
    offset: int
    limit: int
    query: str | None = None



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
