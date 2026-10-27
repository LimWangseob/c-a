"""관리대장 '체험단' 시트 → 체험단 시작일 자동 연결(D-086·소유자 2026-10-19).

체험단 내역은 관리대장 두 번째 시트('체험단 진행 명단')에만 있고, 결과 계정목록의 체험단 칸(직원 입력)은 비어 있어
'체험단효과'가 늘 공란이었다(실측 10-19: 계정목록 체험단 칸 0/88). 이 모듈이 시트의 '체험단시작일'·링크를 읽어
링크 속 상품번호(vendorItemId → productId 순)로 결과 상품 블록을 찾고, 그 블록(옵션 블록이면 같은 상품 대표 블록)에
**가장 최근 체험단시작일**을 체험단 시작일로 넣는다(D-122 — '요청일'은 업체에 의뢰한 날이라 시작일 아님·빈 칸 줄 제외). 저장 칸은 수집 주기와 무관한 자동 칸(`set_promo_start`)이라
3일 주기 게이팅(has_marketing)을 켜지 않는다. 직원이 계정목록에 시작일을 넣으면 그 값이 우선(promo_effect).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PROMO_SHEET = "체험단"
_START_COL = "체험단시작일"          # 옛 '진행여부' 칸 이름 변경(소유자 2026-10-27)
_HEADER_SCAN = 8
_VID_RE = re.compile(r"vendorItemId=(\d+)")
_PID_RE = re.compile(r"/products/(\d+)")


@dataclass(frozen=True)
class PromoRow:
    date_iso: str                  # 체험단시작일(YYYY-MM-DD·D-122)
    vid: str                       # 링크의 vendorItemId('' 가능)
    pid: str                       # 링크의 productId('' 가능)
    biz: str                       # 상호(로그·확인용)
    product: str                   # 제품명(로그·확인용)


def _date_iso(value) -> str:
    """'26.08.11'·'2026.08.11'·'2026-08-11' → '2026-08-11'. 못 읽으면 ''."""
    m = re.fullmatch(r"(\d{2}|\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(value or "").strip())
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{('20' + y) if len(y) == 2 else y}-{int(mo):02d}-{int(d):02d}"


def _start_iso(value, req_iso: str) -> str:
    """체험단시작일 칸 → ISO. '9.17'·'09.17 완료'(옛 진행여부 표기)·'26.09.17' 허용·빈 칸/'완료'만 = ''.
    년도 없는 '월.일' = 요청일의 해(시작이 요청보다 앞 날짜면 다음 해), 요청일도 없으면 오늘과 가까운 해."""
    m = re.match(r"\s*((?:\d{2,4}[.\-/])?\d{1,2}[.\-/]\d{1,2})(?!\d)", str(value or ""))
    if not m:
        return ""
    tok = m.group(1)
    if full := _date_iso(tok):
        return full
    mo, d = (int(x) for x in re.split(r"[.\-/]", tok))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    if req_iso:
        y = int(req_iso[:4]) + (1 if f"{mo:02d}-{d:02d}" < req_iso[5:] else 0)
        return f"{y}-{mo:02d}-{d:02d}"
    from .workbook_common import _parse_date
    got = _parse_date(f"{mo:02d}.{d:02d}")
    return got.isoformat() if got else ""


def parse_promo_rows(rows: list) -> list[PromoRow]:
    """체험단 시트 값 격자 → PromoRow 목록. 헤더 = '체험단시작일'·'링크' 가 있는 행(상단 몇 행 안·띄어쓰기 무시).
    체험단시작일이 빈 칸·못 읽는 줄, 링크에 상품번호가 없는 줄은 뺀다(D-122)."""
    for h in range(min(len(rows), _HEADER_SCAN)):
        hdr = [re.sub(r"\s+", "", str(c)) for c in rows[h]]
        if _START_COL in hdr and "링크" in hdr:
            break
    else:
        return []
    col = {name: hdr.index(name) for name in (_START_COL, "요청일", "링크", "상호", "제품명") if name in hdr}

    def cell(r, name):
        i = col.get(name)
        return str(r[i]).strip() if i is not None and i < len(r) and r[i] is not None else ""

    out: list[PromoRow] = []
    for r in rows[h + 1:]:
        d, url = _start_iso(cell(r, _START_COL), _date_iso(cell(r, "요청일"))), cell(r, "링크")
        mv, mp = _VID_RE.search(url), _PID_RE.search(url)
        vid, pid = (mv.group(1) if mv else ""), (mp.group(1) if mp else "")
        if d and (vid or pid):
            out.append(PromoRow(d, vid, pid, cell(r, "상호"), cell(r, "제품명")))
    return out


def read_promo_sheet(url_or_id: str, *, store=None) -> list[PromoRow] | None:
    """관리대장의 '체험단' 시트를 읽어 PromoRow 목록. 시트가 없으면 None(반영 안 함 — 기존 값 유지)."""
    from . import gsheet_api
    client = gsheet_api.GSheetClient(url_or_id, store=store)
    if PROMO_SHEET not in client.sheet_titles():
        return None
    return parse_promo_rows(client.read_values(PROMO_SHEET))


def _primary_block(wb, biz: str, product: str) -> str:
    """키워드가 있는 대표 블록 — 2차 옵션 블록(키워드 없음)이면 같은 등록명의 대표 블록."""
    if wb.has_keyword_section(biz, product):
        return product
    reg = wb.registered_name(biz, product)
    return next((p for p in wb.products_of(biz)
                 if reg and wb.registered_name(biz, p) == reg and wb.has_keyword_section(biz, p)), product)


def apply_promo_starts(wb, promo: list[PromoRow], log) -> tuple[int, list[PromoRow]]:
    """체험단 시작일을 결과 블록에 반영(매번 전부 다시 채움). 반환 = (시작일 넣은 블록 수, 못 찾은 줄)."""
    wb.clear_promo_starts()
    by_vid: dict[str, tuple[str, str]] = {}
    by_pid: dict[str, tuple[str, str]] = {}
    for biz in wb.account_sheets():
        for p in wb.products_of(biz):
            for v in wb.product_vids(biz, p):
                by_vid.setdefault(v, (biz, p))
            if wb.product_pid(biz, p):
                by_pid.setdefault(wb.product_pid(biz, p), (biz, p))
    latest: dict[tuple[str, str], str] = {}
    missed: list[PromoRow] = []
    for r in promo:
        hit = by_vid.get(r.vid) if r.vid else None
        hit = hit or (by_pid.get(r.pid) if r.pid else None)
        if not hit:
            missed.append(r)
            continue
        key = (hit[0], _primary_block(wb, *hit))
        latest[key] = max(latest.get(key, ""), r.date_iso)        # 같은 상품 여러 회차 = 가장 최근 시작일
    for (biz, p), d in latest.items():
        wb.set_promo_start(biz, p, d)
    log(f"  [체험단] 관리대장 체험단 시트 {len(promo)}줄 → 시작일 연결 {len(latest)}개 상품"
        + (f" · 결과에 없는 상품 {len(missed)}줄: " + ", ".join(f"{m.biz}/{m.product}" for m in missed[:10])
           if missed else ""))
    return len(latest), missed
