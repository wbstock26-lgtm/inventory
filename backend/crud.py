"""공통 DB 유틸리티 — 재고 계산 및 제품 검색"""
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional, Dict
from . import models


def get_current_stock(db: Session, product_id: int) -> int:
    """단일 제품 현재 재고 계산 (stock_movements 합산)"""
    result = db.query(func.sum(
        case(
            (models.StockMovement.type == "out", -models.StockMovement.quantity),
            else_=models.StockMovement.quantity,
        )
    )).filter(models.StockMovement.product_id == product_id).scalar()
    return result or 0


def get_all_stocks_bulk(db: Session) -> Dict[int, int]:
    """전체 제품 재고를 1번 쿼리로 계산 (N+1 대신 사용)"""
    rows = db.query(
        models.StockMovement.product_id,
        func.sum(
            case(
                (models.StockMovement.type == "out", -models.StockMovement.quantity),
                else_=models.StockMovement.quantity,
            )
        ).label("stock"),
    ).group_by(models.StockMovement.product_id).all()
    return {row.product_id: (row.stock or 0) for row in rows}


def find_product(
    db: Session,
    barcode: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[models.Product]:
    """UPC 바코드 우선 검색. 바코드가 제공된 경우 이름 fallback을 사용하지 않음.
    바코드 없이 이름만 있을 때만 키워드 매칭 사용."""
    if barcode:
        p = db.query(models.Product).filter(
            models.Product.barcode == barcode,
            models.Product.is_active == True,
        ).first()
        # 바코드가 있으면 바코드 결과만 반환 (다른 바코드 = 다른 제품)
        return p

    if name:
        # 바코드 없을 때만 이름 키워드 매칭 사용
        words = [w for w in name.lower().split() if len(w) > 3]
        products = db.query(models.Product).filter(
            models.Product.is_active == True
        ).all()
        best, best_score = None, 0
        for p in products:
            score = sum(1 for w in words if w in p.name.lower())
            if score >= 2 and score > best_score:
                best, best_score = p, score
        return best

    return None


def get_sku_mapping(db: Session, supplier: str, item_no: str) -> Optional[models.SupplierSkuMap]:
    return db.query(models.SupplierSkuMap).filter(
        models.SupplierSkuMap.supplier == supplier,
        models.SupplierSkuMap.item_no == item_no,
    ).first()
