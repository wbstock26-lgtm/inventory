from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List

from ..database import get_db
from .. import models, schemas
from ..crud import get_current_stock

router = APIRouter()


@router.post("/receive", status_code=201)
def receive_stock(body: schemas.ReceiveRequest, db: Session = Depends(get_db)):
    """단일 제품 입고 처리"""
    p = db.query(models.Product).filter(models.Product.id == body.product_id).first()
    if not p:
        raise HTTPException(404, "제품을 찾을 수 없습니다")

    current = get_current_stock(db, body.product_id)
    movement = models.StockMovement(
        product_id=body.product_id,
        type="in",
        quantity=body.quantity,
        stock_before=current,
        stock_after=current + body.quantity,
        unit_cost=body.unit_cost or p.cost,
        note=body.note,
        supplier=body.supplier,
        order_no=body.order_no,
    )
    db.add(movement)
    if body.unit_cost and body.unit_cost > 0:
        p.cost = body.unit_cost   # 최신 단가 자동 업데이트
    db.commit(); db.refresh(movement)
    return {
        "movement_id":  movement.id,
        "stock_before": current,
        "stock_after":  current + body.quantity,
    }


@router.post("/adjust", status_code=201)
def adjust_stock(body: schemas.AdjustRequest, db: Session = Depends(get_db)):
    """재고 수동 조정 (+증가 / -감소)"""
    p = db.query(models.Product).filter(models.Product.id == body.product_id).first()
    if not p:
        raise HTTPException(404, "제품을 찾을 수 없습니다")

    current = get_current_stock(db, body.product_id)
    new_stock = current + body.quantity
    movement = models.StockMovement(
        product_id=body.product_id,
        type="adj",
        quantity=body.quantity,
        stock_before=current,
        stock_after=new_stock,
        unit_cost=p.cost,
        note=body.note,
    )
    db.add(movement); db.commit()
    return {"stock_before": current, "stock_after": new_stock}


@router.post("/bulk-set", response_model=schemas.BulkSetResult)
def bulk_set_stock(body: List[schemas.BulkSetItem], db: Session = Depends(get_db)):
    """GTI 보고서 기준 재고 일괄 세팅 (바코드로 매칭, delta 조정)"""
    result_items = []
    matched = not_found = unchanged = 0

    for item in body:
        bc = item.barcode.lstrip('0').zfill(12) if len(item.barcode) <= 13 else item.barcode
        p = (
            db.query(models.Product)
            .filter(models.Product.barcode == bc)
            .first()
        )
        if not p:
            # 앞 0 제거 없이 한 번 더 시도
            p = db.query(models.Product).filter(models.Product.barcode == item.barcode).first()
        if not p:
            not_found += 1
            result_items.append(schemas.BulkSetResultItem(
                barcode=item.barcode, name="", found=False
            ))
            continue

        current = get_current_stock(db, p.id)
        delta   = item.qty - current
        if delta == 0:
            unchanged += 1
            result_items.append(schemas.BulkSetResultItem(
                barcode=item.barcode, name=p.name, found=True,
                stock_before=current, stock_after=current, delta=0
            ))
            continue

        new_stock = current + delta
        movement = models.StockMovement(
            product_id=p.id,
            type="adj",
            quantity=delta,
            stock_before=current,
            stock_after=new_stock,
            unit_cost=p.cost,
            note="GTI 보고서 재고 대조",
        )
        db.add(movement)
        matched += 1
        result_items.append(schemas.BulkSetResultItem(
            barcode=item.barcode, name=p.name, found=True,
            stock_before=current, stock_after=new_stock, delta=delta
        ))

    db.commit()
    return schemas.BulkSetResult(
        matched=matched, not_found=not_found, unchanged=unchanged,
        items=result_items
    )


@router.get("/movements", response_model=List[schemas.MovementOut])
def get_movements(
    product_id: Optional[int] = None,
    supplier:   Optional[str] = None,
    type:       Optional[str] = Query(None, description="in / out / adj"),
    limit:      int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(models.StockMovement).order_by(desc(models.StockMovement.created_at))
    if product_id:
        query = query.filter(models.StockMovement.product_id == product_id)
    if supplier:
        query = query.filter(models.StockMovement.supplier == supplier)
    if type:
        query = query.filter(models.StockMovement.type == type)

    result = []
    for m in query.limit(limit).all():
        out = schemas.MovementOut.model_validate(m)
        out.product_name = m.product.name if m.product else ""
        result.append(out)
    return result


@router.post("/sales", status_code=201)
def record_sales(body: schemas.SaleCreate, db: Session = Depends(get_db)):
    """전일 판매 입력 — UPC로 제품 매칭 후 out 이동 기록"""
    results = []
    for item in body.items:
        # UPC 또는 product_id로 제품 조회
        product = None
        if item.product_id:
            product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        elif item.barcode:
            # 정확한 UPC 매칭 (비활성 포함 — 발견 시 재활성화)
            product = db.query(models.Product).filter(models.Product.barcode == item.barcode).first()
            if product and not product.is_active:
                product.is_active = True
            # 퍼지 매칭: OCR 오인식(1자리 오류) 보완 — 끝 11자리 또는 앞 11자리로 시도
            if not product and len(item.barcode) >= 11:
                suffix = item.barcode[-11:]
                product = db.query(models.Product).filter(
                    models.Product.barcode.like(f"%{suffix}")
                ).first()
                if product and not product.is_active:
                    product.is_active = True
            if not product and len(item.barcode) >= 11:
                prefix = item.barcode[:11]
                product = db.query(models.Product).filter(
                    models.Product.barcode.like(f"{prefix}%")
                ).first()
                if product and not product.is_active:
                    product.is_active = True

        if not product:
            # 바코드와 이름이 있으면 신규 제품으로 자동 등록
            if item.barcode and item.name:
                product = models.Product(
                    barcode=item.barcode,
                    name=item.name,
                    category="Alcohol",
                    vendor=None,
                    cost=0.0,
                    price=0.0,
                    min_stock=0,
                    is_active=True,
                )
                db.add(product)
                db.flush()  # product.id 확보 (commit 전)
                new_stock = -item.qty_sold  # 마이너스 허용
                unit_cost = round(item.sale_amount / item.qty_sold, 4) if item.sale_amount and item.qty_sold else 0.0
                movement = models.StockMovement(
                    product_id=product.id,
                    type="out",
                    quantity=item.qty_sold,
                    stock_before=0,
                    stock_after=new_stock,
                    unit_cost=unit_cost,
                    note=f"판매 {body.sale_date} [신규등록]" + (f" / {body.note}" if body.note else ""),
                    order_no=body.sale_date,
                )
                db.add(movement)
                results.append(schemas.SaleItemResult(
                    barcode=product.barcode, name=product.name,
                    qty_sold=item.qty_sold, stock_before=0, stock_after=new_stock,
                    matched=True, created=True
                ))
            else:
                results.append(schemas.SaleItemResult(
                    barcode=item.barcode, name=item.name or item.barcode or "미매칭",
                    qty_sold=item.qty_sold, stock_before=0, stock_after=0,
                    matched=False
                ))
            continue

        current = get_current_stock(db, product.id)
        new_stock = current - item.qty_sold  # 마이너스 허용
        movement = models.StockMovement(
            product_id=product.id,
            type="out",
            quantity=item.qty_sold,
            stock_before=current,
            stock_after=new_stock,
            unit_cost=product.price if product.price > 0 else (
                product.cost if product.cost > 0 else
                (round(item.sale_amount / item.qty_sold, 4) if item.sale_amount and item.qty_sold else 0.0)
            ),
            note=f"판매 {body.sale_date}" + (f" / {body.note}" if body.note else ""),
            order_no=body.sale_date,
        )
        db.add(movement)
        results.append(schemas.SaleItemResult(
            barcode=product.barcode, name=product.name,
            qty_sold=item.qty_sold, stock_before=current, stock_after=new_stock, matched=True
        ))

    db.commit()
    matched = sum(1 for r in results if r.matched)
    return schemas.SaleResult(
        sale_date=body.sale_date,
        total_items=len(results),
        matched=matched,
        unmatched=len(results) - matched,
        items=results,
    )


@router.get("/sales")
def get_sales_history(
    limit: int = Query(30, le=2000),
    db: Session = Depends(get_db),
):
    """판매 이력 조회 (out 타입 이동 기준)"""
    movements = (
        db.query(models.StockMovement)
        .filter(models.StockMovement.type == "out")
        .order_by(desc(models.StockMovement.created_at))
        .limit(limit).all()
    )
    result = []
    for m in movements:
        out = schemas.MovementOut.model_validate(m)
        out.product_name = m.product.name if m.product else ""
        result.append(out)
    return result


@router.delete("/sales/{sale_date}", status_code=200)
def delete_sales_by_date(sale_date: str, db: Session = Depends(get_db)):
    """특정 날짜 판매 내역 전체 삭제 (out 이동 중 order_no 일치)"""
    rows = (
        db.query(models.StockMovement)
        .filter(
            models.StockMovement.type == "out",
            models.StockMovement.order_no == sale_date,
        )
        .all()
    )
    count = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": count, "sale_date": sale_date}


@router.patch("/movements/{movement_id}", response_model=schemas.MovementOut)
def update_movement(movement_id: int, body: schemas.MovementUpdate, db: Session = Depends(get_db)):
    """개별 이동 수정 (수량/단가/메모)"""
    m = db.query(models.StockMovement).filter(models.StockMovement.id == movement_id).first()
    if not m:
        raise HTTPException(404, "이동 내역을 찾을 수 없습니다")
    if body.quantity is not None:
        if body.quantity <= 0:
            raise HTTPException(400, "수량은 1 이상이어야 합니다")
        m.quantity = body.quantity
    if body.unit_cost is not None:
        m.unit_cost = body.unit_cost
    if body.note is not None:
        m.note = body.note
    db.commit(); db.refresh(m)
    out = schemas.MovementOut.model_validate(m)
    out.product_name = m.product.name if m.product else ""
    return out


@router.delete("/movements/{movement_id}", status_code=200)
def delete_movement(movement_id: int, db: Session = Depends(get_db)):
    """개별 이동 삭제"""
    m = db.query(models.StockMovement).filter(models.StockMovement.id == movement_id).first()
    if not m:
        raise HTTPException(404, "이동 내역을 찾을 수 없습니다")
    db.delete(m); db.commit()
    return {"deleted": movement_id}


@router.get("/low")
def get_low_stock(db: Session = Depends(get_db)):
    """최소 재고 미달 품목"""
    products = db.query(models.Product).filter(models.Product.is_active == True).all()
    result = []
    for p in products:
        stock = get_current_stock(db, p.id)
        if stock <= p.min_stock:
            result.append({
                "id": p.id, "barcode": p.barcode, "name": p.name,
                "stock": stock, "min_stock": p.min_stock, "vendor": p.vendor,
            })
    return result
