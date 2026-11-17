from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Product(Base):
    __tablename__ = "products"

    id         = Column(Integer, primary_key=True, index=True)
    barcode    = Column(String(20), unique=True, nullable=True, index=True)  # UPC 12자리
    name       = Column(String(200), nullable=False, index=True)
    category   = Column(String(50), default="Alcohol")
    size       = Column(String(50), nullable=True)
    vendor         = Column(String(100), nullable=True)   # Connect / BDL / Sleeman
    delivery_price = Column(Float, default=0.0)           # 입고가 (case price from supplier)
    cost           = Column(Float, default=0.0)           # 단가/원가 (calculated unit cost)
    price          = Column(Float, default=0.0)           # selling price
    unit           = Column(Float, default=0.0)
    min_stock  = Column(Integer, default=0)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    movements = relationship("StockMovement", back_populates="product")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id           = Column(Integer, primary_key=True, index=True)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=False)
    type         = Column(String(10), nullable=False)   # in / out / adj
    quantity     = Column(Integer, nullable=False)
    stock_before = Column(Integer, nullable=False)
    stock_after  = Column(Integer, nullable=False)
    unit_cost    = Column(Float, default=0.0)
    note         = Column(String(200), nullable=True)
    supplier     = Column(String(50), nullable=True)    # Connect / BDL / Sleeman
    order_no     = Column(String(50), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="movements")


class SupplierSkuMap(Base):
    """공급사 내부 SKU(6자리) → UPC 바코드 매핑"""
    __tablename__ = "supplier_sku_map"

    id         = Column(Integer, primary_key=True, index=True)
    supplier   = Column(String(50), nullable=False)    # Connect / BDL / Sleeman
    item_no    = Column(String(20), nullable=False)    # 공급사 SKU
    barcode    = Column(String(20), nullable=True)     # UPC 12자리
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product")


class Order(Base):
    __tablename__ = "orders"

    id            = Column(Integer, primary_key=True, index=True)
    supplier      = Column(String(50), nullable=False)
    order_no      = Column(String(50), nullable=False, unique=True)
    order_date    = Column(String(20), nullable=True)
    delivery_date = Column(String(20), nullable=True)
    status        = Column(String(20), default="pending")  # pending / received
    total_amount  = Column(Float, default=0.0)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id           = Column(Integer, primary_key=True, index=True)
    order_id     = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=True)
    supplier_sku = Column(String(20), nullable=True)
    barcode      = Column(String(20), nullable=True)
    name         = Column(String(200), nullable=False)
    qty_ordered  = Column(Integer, default=0)
    qty_received = Column(Integer, default=0)
    unit_price   = Column(Float, default=0.0)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    order   = relationship("Order", back_populates="items")
    product = relationship("Product")
