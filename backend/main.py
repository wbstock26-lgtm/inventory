from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from .database import engine
from . import models
from .routers import products, stock, orders, sku_map, ocr, auth


def _ensure_indexes():
    """성능 인덱스 추가 (없으면 생성)"""
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sm_product_id ON stock_movements(product_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sm_type ON stock_movements(type)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sm_order_no ON stock_movements(order_no)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sm_created_at ON stock_movements(created_at)"
        ))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    _ensure_indexes()
    yield


app = FastAPI(
    title="Little Red Deer Store — 재고 관리 시스템",
    version="1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,     prefix="/api/auth",      tags=["auth"])
app.include_router(products.router, prefix="/api/products",  tags=["products"])
app.include_router(stock.router,    prefix="/api/stock",     tags=["stock"])
app.include_router(orders.router,   prefix="/api/orders",    tags=["orders"])
app.include_router(sku_map.router,  prefix="/api/sku-map",   tags=["sku-map"])
app.include_router(ocr.router,      prefix="/api/ocr",        tags=["ocr"])

# 프론트엔드 정적 파일 (frontend/ 폴더에 index.html 배치)
_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="static")
