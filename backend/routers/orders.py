from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional

from ..database import get_db
from .. import models, schemas
from ..crud import get_current_stock, find_product, get_sku_mapping

router = APIRouter()


def _resolve_product(db: Session, supplier: str, item_no: Optional[str],
                     barcode: Optional[str], name: str) -> Optional[models.Product]:
    """SKU맵 → UPC 바코드 → 제품명 순으로 제품 조회"""
    # 1. 저장된 SKU 매핑 확인
    if item_no:
        mapping = get_sku_mapping(db, supplier, item_no)
        if mapping and mapping.barcode:
            barcode = mapping.barcode

    # 2. UPC 바코드 또는 제품명으로 검색
    return find_product(db, barcode=barcode, name=name)


def _get_or_create_product(db: Session, supplier: str, item_no: Optional[str],
                            barcode: Optional[str], name: str, unit_price: float) -> Optional[models.Product]:
    """기존 제품 조회, 없으면 바코드가 있을 때 자동 생성"""
    product = _resolve_product(db, supplier, item_no, barcode, name)
    if product:
        return product
    # 바코드 없으면 생성 불가 (중복 방지 불가)
    if not barcode:
        return None
    new_product = models.Product(
        barcode=barcode,
        name=name,
        vendor=supplier,
        cost=unit_price,
        price=0.0,
    )
    db.add(new_product)
    db.flush()
    # SKU 매핑 자동 저장
    if item_no:
        existing_map = db.query(models.SupplierSkuMap).filter(
            models.SupplierSkuMap.supplier == supplier,
            models.SupplierSkuMap.item_no == item_no
        ).first()
        if not existing_map:
            db.add(models.SupplierSkuMap(
                supplier=supplier, item_no=item_no,
                barcode=barcode, product_id=new_product.id
            ))
    return new_product


@router.post("", status_code=201)
def create_order(body: schemas.OrderCreate, db: Session = Depends(get_db)):
    """발주 파일 임포트 — 파싱된 주문 저장. 바코드 있는 신규 제품은 자동 등록."""
    existing = db.query(models.Order).filter(
        models.Order.order_no == body.order_no
    ).first()
    if existing:
        raise HTTPException(400, f"주문번호 {body.order_no} 이미 처리됨 (ID: {existing.id})")

    total = sum(i.qty_received * i.unit_price for i in body.items)
    order = models.Order(
        supplier=body.supplier,
        order_no=body.order_no,
        order_date=body.order_date,
        delivery_date=body.delivery_date,
        total_amount=round(total, 2),
        status="pending",
    )
    db.add(order); db.flush()

    matched = 0
    auto_created = 0
    for item_in in body.items:
        product = _get_or_create_product(
            db, body.supplier,
            item_in.supplier_sku, item_in.barcode, item_in.name, item_in.unit_price
        )
        if product and not _resolve_product(db, body.supplier, item_in.supplier_sku,
                                             item_in.barcode, item_in.name):
            auto_created += 1
        order_item = models.OrderItem(
            order_id=order.id,
            product_id=product.id if product else None,
            supplier_sku=item_in.supplier_sku,
            barcode=item_in.barcode or (product.barcode if product else None),
            name=item_in.name,
            qty_ordered=item_in.qty_ordered,
            qty_received=item_in.qty_received,
            unit_price=item_in.unit_price,
        )
        db.add(order_item)
        if product:
            matched += 1

    db.commit(); db.refresh(order)
    return {
        "order_id":      order.id,
        "order_no":      order.order_no,
        "total_items":   len(body.items),
        "matched":       matched,
        "auto_created":  auto_created,
        "unmatched":     len(body.items) - matched,
        "status":        "pending",
    }


@router.post("/{order_id}/receive")
def receive_order(order_id: int, db: Session = Depends(get_db)):
    """주문 전체 입고 확인 — stock_movements 생성"""
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "주문을 찾을 수 없습니다")
    if order.status == "received":
        raise HTTPException(400, "이미 입고 처리된 주문입니다")

    received_count = 0
    for item in order.items:
        if not item.product_id or item.qty_received == 0:
            continue
        current = get_current_stock(db, item.product_id)
        movement = models.StockMovement(
            product_id=item.product_id,
            type="in",
            quantity=item.qty_received,
            stock_before=current,
            stock_after=current + item.qty_received,
            unit_cost=item.unit_price,
            supplier=order.supplier,
            order_no=order.order_no,
            note=f"발주 입고 #{order.order_no}",
        )
        db.add(movement)
        # 최신 단가 업데이트
        p = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if p and item.unit_price > 0:
            p.cost = item.unit_price
        received_count += 1

    order.status = "received"
    db.commit()
    return {"received_items": received_count, "order_no": order.order_no}


@router.get("", response_model=List[schemas.OrderOut])
def list_orders(
    supplier: Optional[str] = None,
    status:   Optional[str] = None,
    limit:    int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(models.Order).order_by(desc(models.Order.created_at))
    if supplier:
        query = query.filter(models.Order.supplier == supplier)
    if status:
        query = query.filter(models.Order.status == status)

    result = []
    for o in query.limit(limit).all():
        out = schemas.OrderOut.model_validate(o)
        out.item_count = len(o.items)
        result.append(out)
    return result


@router.patch("/{order_id}/items/{item_id}")
def update_order_item(order_id: int, item_id: int, body: schemas.OrderItemUpdate, db: Session = Depends(get_db)):
    """주문 항목 수량/단가 수정 — 입고완료 주문이면 재고이동도 함께 수정"""
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "주문을 찾을 수 없습니다")

    item = db.query(models.OrderItem).filter(
        models.OrderItem.id == item_id,
        models.OrderItem.order_id == order_id
    ).first()
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다")

    old_qty   = item.qty_received
    old_price = item.unit_price
    new_qty   = body.qty_received if body.qty_received is not None else old_qty
    new_price = body.unit_price   if body.unit_price   is not None else old_price

    item.qty_received = new_qty
    item.unit_price   = new_price

    # 입고완료 주문이면 연결된 재고이동도 수정
    if order.status == "received" and item.product_id:
        movement = (
            db.query(models.StockMovement)
            .filter(
                models.StockMovement.product_id == item.product_id,
                models.StockMovement.type == "in",
                models.StockMovement.order_no == order.order_no,
            )
            .first()
        )
        if movement:
            delta = new_qty - old_qty
            movement.quantity    = new_qty
            movement.stock_after = movement.stock_before + new_qty
            movement.unit_cost   = new_price
            # 이후 재고이동의 stock_before/after는 단순히 현 delta만큼 조정
            if delta != 0:
                later = (
                    db.query(models.StockMovement)
                    .filter(
                        models.StockMovement.product_id == item.product_id,
                        models.StockMovement.id > movement.id,
                    )
                    .order_by(models.StockMovement.id)
                    .all()
                )
                for lm in later:
                    lm.stock_before += delta
                    lm.stock_after  += delta
        # 최신 단가 업데이트
        if new_price > 0:
            p = db.query(models.Product).filter(models.Product.id == item.product_id).first()
            if p:
                p.cost = new_price

    # 주문 합계 재계산
    order.total_amount = round(sum(i.qty_received * i.unit_price for i in order.items), 2)
    db.commit()
    return {"ok": True, "item_id": item_id, "qty_received": new_qty, "unit_price": new_price}


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "주문을 찾을 수 없습니다")
    return {
        "id":            order.id,
        "supplier":      order.supplier,
        "order_no":      order.order_no,
        "order_date":    order.order_date,
        "delivery_date": order.delivery_date,
        "status":        order.status,
        "total_amount":  order.total_amount,
        "created_at":    order.created_at,
        "items": [{
            "id":           i.id,
            "supplier_sku": i.supplier_sku,
            "barcode":      i.barcode,
            "name":         i.name,
            "qty_ordered":  i.qty_ordered,
            "qty_received": i.qty_received,
            "unit_price":   i.unit_price,
            "product_id":   i.product_id,
        } for i in order.items],
    }
