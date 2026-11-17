from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import List
import re

router = APIRouter()


class OcrItem(BaseModel):
    upc: str
    name: str
    qty: int
    amount: float


class OcrResult(BaseModel):
    raw_text: str
    items: List[OcrItem]
    matched: int


async def _win_ocr_words(image_bytes: bytes):
    try:
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.globalization import Language
    except ImportError:
        raise HTTPException(500, "pip install winsdk 가 필요합니다.")

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(image_bytes)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap  = await decoder.get_software_bitmap_async()
    engine  = OcrEngine.try_create_from_language(Language("en-US"))
    if engine is None:
        raise HTTPException(500, "Windows 영어 OCR 엔진 초기화 실패")

    result = await engine.recognize_async(bitmap)

    words = []
    ocr_lines = []
    for line in result.lines:
        line_words = []
        for word in line.words:
            r = word.bounding_rect
            w = {"text": word.text, "x": r.x, "y": r.y, "h": r.height}
            words.append(w)
            line_words.append(w)
        if line_words:
            ocr_lines.append(sorted(line_words, key=lambda x: x["x"]))
    return result.text, words, ocr_lines


def _group_by_y_gap(words, y_gap=15):
    """y좌표 근접도 기반 행 그룹핑 (버킷 스냅보다 경계값에 강건함)"""
    if not words:
        return []
    swords = sorted(words, key=lambda w: (w["y"], w["x"]))
    rows = []
    cur_row = [swords[0]]
    row_min_y = swords[0]["y"]
    for w in swords[1:]:
        if w["y"] - row_min_y <= y_gap:
            cur_row.append(w)
        else:
            rows.append(sorted(cur_row, key=lambda x: x["x"]))
            cur_row = [w]
            row_min_y = w["y"]
    rows.append(sorted(cur_row, key=lambda x: x["x"]))
    return rows


def _reconstruct_rows(words, y_tol=8):
    if not words:
        return []
    rows_dict: dict = {}
    for w in words:
        key = round(w["y"] / y_tol) * y_tol
        rows_dict.setdefault(key, []).append(w)
    return [sorted(v, key=lambda x: x["x"]) for _, v in sorted(rows_dict.items())]


def _normalize(text: str) -> str:
    """OCR 오인식 정규화"""
    text = re.sub(r'\bS(\d{1,3}\.\d{2})\b', r'$\1', text)  # S17.51→$17.51 (가격 패턴만, UPC는 건드리지 않음)
    text = re.sub(r'["""‟]', '', text)
    text = text.replace('—', '-').replace('–', '-')
    # $ 뒤 숫자에서 O→0, l→1 보정
    text = re.sub(r'\$([0-9Ool.]+)', lambda m: '$' + m.group(1).replace('O','0').replace('o','0').replace('l','1'), text)
    return text


def _parse_rows(rows, include_zero: bool = False) -> List[OcrItem]:
    items = []
    for row in rows:
        raw_line  = " ".join(w["text"] for w in row)
        line      = _normalize(raw_line)

        # UPC: 10~13자리 숫자로 시작하는 행 (OCR 오인식 보정: O→0, l/I→1, S→5, B→8, Z→2)
        upc_m = re.match(r'^([0-9OolIiSBZ]{10,13})', line)
        if not upc_m:
            continue
        upc_raw = upc_m.group(1)
        upc_raw = (upc_raw
            .replace('O','0').replace('o','0')
            .replace('l','1').replace('I','1').replace('i','1')
            .replace('S','5').replace('B','8').replace('Z','2'))
        if not re.fullmatch(r'\d{10,13}', upc_raw):
            continue
        upc  = upc_raw.zfill(12)
        rest = line[upc_m.end():].lstrip(' -—')

        # 수량: 1~3자리 정수, 첫 번째 $금액 앞에 있는 경우
        qty   = 1       # 기본값 (qty=1은 OCR이 자주 놓침)
        amount = 0.0
        name   = rest

        # Pattern A: "... name   2   $54.12   ..."  (qty 명시)
        m = re.match(r'^(.+?)\s+(\d{1,3})\s+\$?([\d.]+)', rest)
        if m:
            name   = m.group(1).strip()
            qty    = int(m.group(2))
            try:    amount = float(m.group(3))
            except: amount = 0.0
        else:
            # Pattern B: "... name   $37.51   ..." (qty 없음 → 기본 1)
            m2 = re.match(r'^(.+?)\s+\$?([\d]{1,3}\.[\d]{2})', rest)
            if m2:
                name  = m2.group(1).strip()
                try:  amount = float(m2.group(2))
                except: amount = 0.0

        if qty < 0:
            continue
        if qty == 0 and not include_zero:
            continue
        # 소매점 현실: qty>20은 제품명 숫자 오인식 가능성 → 1로 보정 (include_zero 모드 제외)
        if qty > 20 and not include_zero:
            qty = 1
        items.append(OcrItem(upc=upc, name=name, qty=qty, amount=amount))
    return items


@router.post("/pdf", response_model=OcrResult)
async def ocr_pdf(
    file: UploadFile = File(...),
    include_zero: bool = Query(False, description="qty=0 항목도 포함 (일괄등록용)"),
):
    """PDF 파일을 받아 각 페이지의 이미지를 추출한 뒤 Windows OCR로 처리"""
    data = await file.read()
    if not data:
        raise HTTPException(400, "빈 파일입니다.")

    try:
        from pypdf import PdfReader
        import io as _io
        reader = PdfReader(_io.BytesIO(data))
    except Exception as e:
        raise HTTPException(500, f"PDF 파싱 오류: {e}")

    all_words: list = []
    all_lines: list = []
    full_raw: list[str] = []

    for page_num, page in enumerate(reader.pages, 1):
        # 텍스트 추출 먼저 시도 (이미지 포함 여부 무관)
        text = page.extract_text() or ""
        if text.strip():
            full_raw.append(text)
            print(f"[OCR PDF] page {page_num}: text extracted ({len(text)} chars)")
            continue

        # 텍스트 없는 경우에만 이미지 OCR
        images = list(page.images)
        if not images:
            continue

        for img_idx, img_obj in enumerate(images):
            try:
                from PIL import Image
                import io as _io

                pil_img = img_obj.image
                if pil_img.mode in ('RGBA', 'P', 'LA'):
                    bg = Image.new('RGB', pil_img.size, (255, 255, 255))
                    rgba = pil_img.convert('RGBA')
                    bg.paste(rgba, mask=rgba.split()[-1])
                    pil_img = bg
                elif pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')

                # 이미지가 가로로 누워있으면 회전 시도 (rotation 0, 90, 270 순서로 가장 많은 단어 반환하는 방향 선택)
                best_words: list = []
                best_lines: list = []
                best_text = ""
                best_pil = pil_img
                for angle in [0, 90, 270, 180]:
                    rotated = pil_img.rotate(angle, expand=True) if angle != 0 else pil_img
                    buf_r = _io.BytesIO()
                    rotated.save(buf_r, format='PNG')
                    r_text, r_words, r_lines = await _win_ocr_words(buf_r.getvalue())
                    print(f"[OCR PDF] page {page_num} img {img_idx} angle={angle}: {len(r_words)} words")
                    if len(r_words) > len(best_words):
                        best_words = r_words
                        best_lines = r_lines
                        best_text  = r_text
                    # 충분히 많은 단어가 나오면 더 이상 회전 안 함
                    if len(r_words) >= 50:
                        break

                y_offset = (page_num - 1) * 100000
                for w in best_words:
                    all_words.append({**w, "y": w["y"] + y_offset})
                all_lines.extend(best_lines)
                full_raw.append(best_text)
                print(f"[OCR PDF] page {page_num} img {img_idx}: best={len(best_words)} words, text preview: {best_text[:100]}")
            except Exception as e:
                print(f"[OCR PDF] page {page_num} img {img_idx} error: {e}")

    rows = _group_by_y_gap(all_words, y_gap=15)
    items = _parse_rows(rows, include_zero=include_zero)
    return OcrResult(
        raw_text="\n".join(full_raw),
        items=items,
        matched=len(items),
    )


@router.post("/image", response_model=OcrResult)
async def ocr_image(
    file: UploadFile = File(...),
    include_zero: bool = Query(False, description="qty=0 항목도 포함 (일괄등록용)"),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "빈 파일입니다.")

    # PIL 전처리: 포맷 변환, RGB, 최소 크기 보장
    try:
        from PIL import Image
        import io as _io
        pil_img = Image.open(_io.BytesIO(data))
        print(f"[OCR image] format={pil_img.format}, size={pil_img.size}, mode={pil_img.mode}")

        if pil_img.mode in ('RGBA', 'P', 'LA'):
            bg = Image.new('RGB', pil_img.size, (255, 255, 255))
            rgba = pil_img.convert('RGBA')
            bg.paste(rgba, mask=rgba.split()[-1])
            pil_img = bg
        elif pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')

        # Windows OCR 감지율 향상: 2x 업스케일 + 대비 강화
        new_size = (pil_img.width * 2, pil_img.height * 2)
        pil_img = pil_img.resize(new_size, Image.LANCZOS)
        from PIL import ImageEnhance
        pil_img = ImageEnhance.Contrast(pil_img).enhance(1.5)
        print(f"[OCR image] upscaled to {new_size} + contrast 1.5x")

        buf = _io.BytesIO()
        pil_img.save(buf, format='PNG')
        data = buf.getvalue()
    except Exception as e:
        print(f"[OCR image] PIL 전처리 실패 (원본 사용): {e}")

    raw_text, words, ocr_lines = await _win_ocr_words(data)
    print(f"[OCR image] raw_text_len={len(raw_text)}, words={len(words)}, ocr_lines={len(ocr_lines)}")
    for i, ln in enumerate(ocr_lines):
        print(f"[OCR line {i:03d}] {repr(' '.join(w['text'] for w in ln))}")
    rows = _group_by_y_gap(words, y_gap=15)
    print(f"[OCR image] rows after y_gap grouping: {len(rows)}")
    for i, r in enumerate(rows):
        print(f"[OCR row  {i:03d}] {repr(' '.join(w['text'] for w in r))}")
    items = _parse_rows(rows, include_zero=include_zero)
    return OcrResult(raw_text=raw_text, items=items, matched=len(items))
