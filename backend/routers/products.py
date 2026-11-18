from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from ..database import get_db
from .. import models, schemas
from ..crud import get_current_stock, get_all_stocks_bulk, find_product

router = APIRouter()


@router.get("", response_model=List[schemas.ProductOut])
def list_products(
    q:         Optional[str] = Query(None, description="UPC 바코드 또는 제품명"),
    category:  Optional[str] = None,
    low_stock: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(models.Product).filter(models.Product.is_active == True)
    if q:
        query = query.filter(
            (models.Product.barcode == q) |
            (models.Product.name.ilike(f"%{q}%"))
        )
    if category:
        query = query.filter(models.Product.category == category)

    products = query.all()
    # 전체 재고를 1번 쿼리로 계산 (N+1 방지)
    stock_map = get_all_stocks_bulk(db)
    result = []
    for p in products:
        stock = stock_map.get(p.id, 0)
        if low_stock and stock > p.min_stock:
            continue
        out = schemas.ProductOut.model_validate(p)
        out.stock = stock
        result.append(out)
    return result


@router.get("/search", response_model=List[schemas.ProductOut])
def search_products(
    barcode: Optional[str] = None,
    name:    Optional[str] = None,
    db: Session = Depends(get_db),
):
    """UPC 바코드 또는 제품명으로 검색 (기본 검색 키)"""
    query = db.query(models.Product).filter(models.Product.is_active == True)
    if barcode:
        query = query.filter(models.Product.barcode == barcode)
    elif name:
        query = query.filter(models.Product.name.ilike(f"%{name}%"))

    result = []
    for p in query.all():
        out = schemas.ProductOut.model_validate(p)
        out.stock = get_current_stock(db, p.id)
        result.append(out)
    return result


@router.get("/valuation")
def stock_valuation(db: Session = Depends(get_db)):
    """부서별 재고 평가액 (BackOffice Stock Valuation by Department 대응)"""
    products = db.query(models.Product).filter(models.Product.is_active == True).all()
    stock_map = get_all_stocks_bulk(db)
    items, total = [], 0.0
    for p in products:
        stock = stock_map.get(p.id, 0)
        value = round(stock * p.cost, 2)
        total += value
        items.append({
            "id": p.id, "barcode": p.barcode, "name": p.name,
            "category": p.category, "stock": stock,
            "cost": p.cost, "total_cost": value,
        })
    return {"items": items, "total_value": round(total, 2)}


@router.post("", response_model=schemas.ProductOut, status_code=201)
def create_product(body: schemas.ProductCreate, db: Session = Depends(get_db)):
    if body.barcode:
        exists = db.query(models.Product).filter(
            models.Product.barcode == body.barcode
        ).first()
        if exists:
            raise HTTPException(400, f"바코드 {body.barcode} 제품이 이미 존재합니다")
    p = models.Product(**body.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    out = schemas.ProductOut.model_validate(p)
    out.stock = 0
    return out


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "제품을 찾을 수 없습니다")
    out = schemas.ProductOut.model_validate(p)
    out.stock = get_current_stock(db, p.id)
    return out


@router.patch("/{product_id}", response_model=schemas.ProductOut)
def patch_product(product_id: int, body: schemas.ProductUpdate, db: Session = Depends(get_db)):
    return update_product(product_id, body, db)


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, body: schemas.ProductUpdate, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "제품을 찾을 수 없습니다")
    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(p, k, v)
    # delivery_price 또는 unit이 변경됐고 cost가 명시 안 됐으면 자동 계산
    VENDOR_MARGIN = {'Connect': 0.31, 'BDL': 0.25, 'Sleeman': 0.25}
    if 'cost' not in data:
        d = p.delivery_price or 0
        u = p.unit or 0
        vendor = p.vendor or ''
        if d > 0 and u > 0:
            if vendor == 'Connect':
                p.cost = round(d / u, 2)
            elif vendor in ('BDL', 'Sleeman'):
                p.cost = round((d - u * 0.1) / 1.05 / u, 2)
    # price가 미설정이면 cost + vendor 마진으로 자동 계산
    if 'price' not in data and (not p.price or p.price <= 0):
        margin = VENDOR_MARGIN.get(p.vendor or '', 0)
        if margin > 0 and p.cost and p.cost > 0:
            p.price = round(p.cost / (1 - margin), 2)
    db.commit(); db.refresh(p)
    out = schemas.ProductOut.model_validate(p)
    out.stock = get_current_stock(db, p.id)
    return out


@router.post("/bulk-register", response_model=schemas.BulkRegisterResult)
def bulk_register(items: List[schemas.BulkProductItem], db: Session = Depends(get_db)):
    """여러 UPC+제품명+초기재고를 한꺼번에 등록.
    initial_stock == 0 이면 건너뜀. 양수/음수면 재고 이동(in/adj)도 함께 생성."""
    from ..crud import get_current_stock
    created, skipped = 0, 0
    result_items = []
    seen = set()
    for item in items:
        if item.barcode in seen or item.initial_stock == 0:
            continue
        seen.add(item.barcode)
        exists = db.query(models.Product).filter(
            models.Product.barcode == item.barcode
        ).first()
        if exists:
            result_items.append(schemas.BulkRegisterResultItem(
                barcode=item.barcode, name=exists.name, created=False
            ))
            skipped += 1
        else:
            p = models.Product(barcode=item.barcode, name=item.name,
                               category="Alcohol", cost=0.0, price=0.0, min_stock=0)
            db.add(p)
            db.flush()  # p.id 확보
            qty   = abs(item.initial_stock)
            mtype = "in" if item.initial_stock > 0 else "adj"
            movement = models.StockMovement(
                product_id=p.id,
                type=mtype,
                quantity=qty,
                stock_before=0,
                stock_after=qty if mtype == "in" else max(0, item.initial_stock),
                unit_cost=0.0,
                note="일괄등록 초기재고",
            )
            db.add(movement)
            result_items.append(schemas.BulkRegisterResultItem(
                barcode=item.barcode, name=item.name, created=True
            ))
            created += 1
    db.commit()
    return schemas.BulkRegisterResult(created=created, skipped=skipped, items=result_items)


@router.post("/{keep_id}/merge/{remove_id}")
def merge_products(keep_id: int, remove_id: int, db: Session = Depends(get_db)):
    """두 제품을 통합: keep_id 제품을 유지하고 remove_id 제품의 재고 이동을 흡수한 뒤 비활성화.
    바코드: keep_id에 없으면 remove_id의 것을 복사."""
    keep = db.query(models.Product).filter(models.Product.id == keep_id).first()
    remove = db.query(models.Product).filter(models.Product.id == remove_id).first()
    if not keep:
        raise HTTPException(404, f"제품 {keep_id}을 찾을 수 없습니다")
    if not remove:
        raise HTTPException(404, f"제품 {remove_id}을 찾을 수 없습니다")
    if keep_id == remove_id:
        raise HTTPException(400, "같은 제품입니다")

    # 재고 이동 흡수
    db.query(models.StockMovement).filter(
        models.StockMovement.product_id == remove_id
    ).update({"product_id": keep_id})

    # keep에 바코드가 없으면 remove 것을 가져옴
    if not keep.barcode and remove.barcode:
        keep.barcode = remove.barcode

    # keep에 vendor가 없으면 remove 것을 가져옴
    if not keep.vendor and remove.vendor:
        keep.vendor = remove.vendor

    # remove 비활성화 + 바코드 클리어 (unique constraint 해제)
    remove.barcode = None
    remove.is_active = False

    db.commit()
    db.refresh(keep)
    out = schemas.ProductOut.model_validate(keep)
    out.stock = get_current_stock(db, keep.id)
    return {"merged": True, "kept": out, "removed_id": remove_id}


@router.get("/by-barcode/{barcode}", response_model=schemas.ProductOut)
def get_by_barcode(barcode: str, db: Session = Depends(get_db)):
    """바코드로 제품 조회 (활성/비활성 모두)"""
    p = db.query(models.Product).filter(models.Product.barcode == barcode).first()
    if not p:
        raise HTTPException(404, "해당 바코드의 제품이 없습니다")
    out = schemas.ProductOut.model_validate(p)
    out.stock = get_current_stock(db, p.id)
    return out


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "제품을 찾을 수 없습니다")
    p.is_active = False
    db.commit()
