from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
import re, difflib

from ..database import get_db
from .. import models, schemas


def _parse_connect_file(text: str) -> list[tuple[str, str]]:
    """Connect 발주 텍스트에서 (SKU, Description) 쌍 추출"""
    items: list[tuple[str, str]] = []
    seen: set[str] = set()

    for line in text.splitlines():
        # 5~8자리 숫자(SKU) 뒤에 수량 2개 + UM + 설명이 오는 패턴
        m = re.search(
            r'\b(\d{5,8})\b'           # SKU
            r'\s+\d+\s+\d+'            # Order  Ship
            r'\s+\S+'                  # UM (CS, 4Pk …)
            r'\s+([A-Za-z].+?)$',      # Description (알파벳 시작)
            line,
        )
        if not m:
            continue
        sku  = m.group(1)
        desc = m.group(2).strip()
        # 뒤쪽 가격 열 제거 — 2개 이상 공백 뒤 숫자로 시작하는 부분 절삭
        desc = re.sub(r'\s{2,}\d.*$', '', desc).strip()
        if sku and desc and len(desc) > 2 and sku not in seen:
            seen.add(sku)
            items.append((sku, desc))
    return items


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'[^\w\s]', ' ', s)
    return s


def _best_match(desc: str, products: list) -> tuple:
    """description에 가장 유사한 제품 반환 (product, score)"""
    desc_n = _normalize(desc)
    best, best_score = None, 0.0
    for p in products:
        score = difflib.SequenceMatcher(None, desc_n, _normalize(p.name)).ratio()
        if score > best_score:
            best_score = score
            best = p
    return (best, round(best_score, 3)) if best_score >= 0.45 else (None, 0.0)

router = APIRouter()


@router.get("", response_model=List[schemas.SkuMapOut])
def list_sku_maps(
    supplier: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.SupplierSkuMap)
    if supplier:
        query = query.filter(models.SupplierSkuMap.supplier == supplier)
    return query.all()


@router.post("", response_model=schemas.SkuMapOut, status_code=201)
def upsert_sku_map(body: schemas.SkuMapCreate, db: Session = Depends(get_db)):
    """SKU 매핑 저장 (없으면 생성, 있으면 업데이트)"""
    existing = db.query(models.SupplierSkuMap).filter(
        models.SupplierSkuMap.supplier == body.supplier,
        models.SupplierSkuMap.item_no == body.item_no,
    ).first()
    if existing:
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(existing, k, v)
        db.commit(); db.refresh(existing)
        return existing
    mapping = models.SupplierSkuMap(**body.model_dump())
    db.add(mapping); db.commit(); db.refresh(mapping)
    return mapping


@router.get("/lookup")
def lookup_sku(
    supplier: str,
    item_no:  str,
    db: Session = Depends(get_db),
):
    """공급사 SKU로 UPC 바코드 조회"""
    mapping = db.query(models.SupplierSkuMap).filter(
        models.SupplierSkuMap.supplier == supplier,
        models.SupplierSkuMap.item_no == item_no,
    ).first()
    if not mapping:
        raise HTTPException(404, f"{supplier} SKU {item_no} 매핑 없음")
    return {"barcode": mapping.barcode, "product_id": mapping.product_id}


@router.post("/sync-connect", status_code=200)
def sync_connect_sku(db: Session = Depends(get_db)):
    """Connect/Sleeman 활성 제품을 barcode=item_no로 sku_map에 자동 등록"""
    suppliers = ["Connect", "Sleeman"]
    created = updated = skipped = 0
    for supplier in suppliers:
        products = (
            db.query(models.Product)
            .filter(
                models.Product.vendor == supplier,
                models.Product.is_active == True,
                models.Product.barcode != None,
            )
            .all()
        )
        for p in products:
            existing = db.query(models.SupplierSkuMap).filter(
                models.SupplierSkuMap.supplier == supplier,
                models.SupplierSkuMap.item_no  == p.barcode,
            ).first()
            if existing:
                if existing.product_id != p.id:
                    existing.product_id = p.id
                    updated += 1
                else:
                    skipped += 1
                continue
            db.add(models.SupplierSkuMap(
                supplier=supplier,
                item_no=p.barcode,
                barcode=p.barcode,
                product_id=p.id,
            ))
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


@router.post("/import-connect", status_code=200)
async def import_connect_sku(
    file: UploadFile = File(...),
    save: bool = Query(False, description="True이면 DB에 저장"),
    db: Session = Depends(get_db),
):
    """Connect 발주 텍스트 파일에서 SKU를 파싱해 sku_map에 등록"""
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")

    parsed = _parse_connect_file(text)
    if not parsed:
        return {"saved": False, "items": [], "message": "SKU를 찾을 수 없습니다. 파일 형식을 확인하세요."}

    # Connect 전체 제품 (비활성 포함)
    all_connect = db.query(models.Product).filter(models.Product.vendor == "Connect").all()

    results = []
    for sku, desc in parsed:
        # 이미 매핑 존재?
        existing = db.query(models.SupplierSkuMap).filter(
            models.SupplierSkuMap.supplier == "Connect",
            models.SupplierSkuMap.item_no == sku,
        ).first()
        if existing:
            prod = db.query(models.Product).get(existing.product_id) if existing.product_id else None
            results.append({
                "sku": sku, "description": desc,
                "product_id": existing.product_id,
                "product_name": prod.name if prod else None,
                "score": 1.0, "status": "existing",
            })
            continue

        prod, score = _best_match(desc, all_connect)
        status = "matched" if prod else "unmatched"

        if save and prod:
            db.add(models.SupplierSkuMap(
                supplier="Connect",
                item_no=sku,
                barcode=prod.barcode,
                product_id=prod.id,
            ))
            # 비활성 제품이면 활성화
            if not prod.is_active:
                prod.is_active = True

        results.append({
            "sku": sku, "description": desc,
            "product_id": prod.id if prod else None,
            "product_name": prod.name if prod else None,
            "score": score, "status": status,
        })

    if save:
        db.commit()

    matched   = sum(1 for r in results if r["status"] in ("matched","existing"))
    unmatched = sum(1 for r in results if r["status"] == "unmatched")
    return {"saved": save, "total": len(results), "matched": matched, "unmatched": unmatched, "items": results}


@router.delete("/{map_id}", status_code=204)
def delete_sku_map(map_id: int, db: Session = Depends(get_db)):
    m = db.query(models.SupplierSkuMap).filter(
        models.SupplierSkuMap.id == map_id
    ).first()
    if not m:
        raise HTTPException(404, "매핑을 찾을 수 없습니다")
    db.delete(m); db.commit()
