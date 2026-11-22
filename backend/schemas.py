from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Product ──────────────────────────────────────────────
class ProductBase(BaseModel):
    barcode:   Optional[str] = None   # UPC 12자리 — 기본 검색 키
    name:      str
    category:  Optional[str] = "Alcohol"
    size:      Optional[str] = None
    vendor:         Optional[str] = None   # Connect / BDL / Sleeman
    unit:           float = 0.0
    delivery_price: float = 0.0
    cost:           float = 0.0
    price:          float = 0.0
    min_stock: int = 0

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    barcode:   Optional[str] = None
    name:      Optional[str] = None
    category:  Optional[str] = None
    size:      Optional[str] = None
    vendor:         Optional[str] = None
    unit:           Optional[float] = None
    delivery_price: Optional[float] = None
    cost:           Optional[float] = None
    price:          Optional[float] = None
    min_stock: Optional[int] = None
    is_active:      Optional[bool] = None

class ProductOut(ProductBase):
    id:         int
    is_active:  bool
    stock:      int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Stock ─────────────────────────────────────────────────
class ReceiveRequest(BaseModel):
    product_id: int
    quantity:   int = Field(..., gt=0)
    unit_cost:  float = 0.0
    supplier:   Optional[str] = None
    order_no:   Optional[str] = None
    note:       Optional[str] = None

class AdjustRequest(BaseModel):
    product_id: int
    quantity:   int   # +증가 / -감소
    note:       Optional[str] = None

class SplitRequest(BaseModel):
    from_product_id: int
    to_product_id:   int
    qty:             int   # 분할할 원본 수량 (예: 24캔짜리 2개)
    ratio:           Optional[int] = None  # 명시적 비율; None이면 이름에서 자동 감지
    note:            Optional[str] = None

class MovementOut(BaseModel):
    id:           int
    product_id:   int
    product_name: str = ""
    type:         str
    quantity:     int
    stock_before: int
    stock_after:  int
    unit_cost:    float = 0.0
    note:         Optional[str] = None
    supplier:     Optional[str] = None
    order_no:     Optional[str] = None
    created_at:   datetime

    model_config = {"from_attributes": True}


# ── Supplier SKU Map ──────────────────────────────────────
class SkuMapCreate(BaseModel):
    supplier:   str
    item_no:    str
    barcode:    Optional[str] = None
    product_id: Optional[int] = None

class SkuMapOut(SkuMapCreate):
    id:         int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Order ─────────────────────────────────────────────────
class OrderItemIn(BaseModel):
    supplier_sku: Optional[str] = None
    barcode:      Optional[str] = None
    name:         str
    qty_ordered:  int = 0
    qty_received: int = 0
    unit_price:   float = 0.0

class OrderCreate(BaseModel):
    supplier:      str
    order_no:      str
    order_date:    Optional[str] = None
    delivery_date: Optional[str] = None
    items:         List[OrderItemIn]

# ── Sales (전일 판매 입력) ────────────────────────────────
class SaleItem(BaseModel):
    barcode:      Optional[str] = None
    product_id:   Optional[int] = None
    name:         Optional[str] = None
    qty_sold:     int = Field(..., gt=0)
    sale_amount:  float = 0.0   # 판매금액

class SaleCreate(BaseModel):
    sale_date:  str            # YYYY-MM-DD
    items:      List[SaleItem]
    note:       Optional[str] = None

class SaleItemResult(BaseModel):
    barcode:      Optional[str]
    name:         str
    qty_sold:     int
    stock_before: int
    stock_after:  int
    matched:      bool
    created:      bool = False   # True이면 이번 판매 등록 시 신규 추가된 제품

class SaleResult(BaseModel):
    sale_date:    str
    total_items:  int
    matched:      int
    unmatched:    int
    items:        List[SaleItemResult]


# ── Bulk Product Register ────────────────────────────────
class BulkProductItem(BaseModel):
    barcode:       str
    name:          str
    initial_stock: int = 0   # 0이면 등록 건너뜀

class BulkRegisterResultItem(BaseModel):
    barcode: str
    name:    str
    created: bool   # True=신규등록 / False=기존제품

class BulkRegisterResult(BaseModel):
    created: int
    skipped: int
    items:   List[BulkRegisterResultItem]


class BulkSetItem(BaseModel):
    barcode: str
    qty:     int

class BulkSetResultItem(BaseModel):
    barcode:      str
    name:         str
    found:        bool
    stock_before: int = 0
    stock_after:  int = 0
    delta:        int = 0

class BulkSetResult(BaseModel):
    matched:   int
    not_found: int
    unchanged: int
    items:     List[BulkSetResultItem]


class MovementUpdate(BaseModel):
    quantity:  Optional[int]   = None
    unit_cost: Optional[float] = None
    note:      Optional[str]   = None

class OrderItemUpdate(BaseModel):
    qty_received: Optional[float] = None
    unit_price:   Optional[float] = None
    barcode:      Optional[str]   = None
    product_id:   Optional[int]   = None


class OrderOut(BaseModel):
    id:            int
    supplier:      str
    order_no:      str
    order_date:    Optional[str] = None
    delivery_date: Optional[str] = None
    status:        str
    total_amount:  float
    item_count:    int = 0
    created_at:    datetime

    model_config = {"from_attributes": True}
