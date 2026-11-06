"""윙 할인쿠폰 목록 수집(읽기만) — 쿠폰과 쿠폰별 옵션을 그대로 날짜별로 쌓음 (소유자 승인 2026-11-06).

정산 전 옵션별 쿠폰 금액을 산식으로 계산하기 위한 입력. 쿠폰 목록은 '지나면 빠지는' 자료(화면 최근 90일)라 매일 남긴다.
①판매수집의 로그인된 윙 세션에서 화면과 같은 주소를 same-origin GET fetch 한다(collector 의 데이터 API 조회와 같은 방식).
사용 금액 0인 쿠폰도 전부 저장하고, 응답은 칸을 고르지 않고 **응답 전체**를 저장한다(정액이 수량 곱으로 적용되는 쿠폰을 가리는
칸을 아직 못 찾음 — 쿠폰 산식 검증 보고서 261106 §7).

실측(휴라엘 2026-11-06): 목록은 page 0부터·응답 content 에 쿠폰(23건 page 0~2). ⚠ 쿠폰별 옵션(items) 응답의 묶음 칸과
시작 페이지는 사양에 없어 목록과 같다고 두었고(content·0부터), 다르면 조용히 넘어가지 않고 부분본+로그로 드러난다.

저장(daily_snapshot) = output/쿠폰목록_일별/{계정}/{날짜}.json.gz.
**같은 날 다시 실행**: 그날 완료본이 있으면 쿠팡을 다시 부르지 않고 건너뜀(호출을 늘리지 않음·덮어쓰지 않음). 중간에 멈춘
부분본만 있으면 처음부터 다시 받아 완료본을 새로 쓰고 부분본은 그대로 둔다.
**실패**: 판매분석 부가 조회와 같은 수준 — 첫 실패에서 이 계정 조회만 멈추고 로그로 남기며 ① 수집은 계속. 받은 만큼은 부분본으로 저장.
"""
from __future__ import annotations

import json
import random
import time
from urllib.parse import quote

from . import daily_snapshot
from .collector import _GET_JSON_JS

_BASE = "https://wing.coupang.com/tenants/seller-promotion-platform/v2/seller-funding-coupon/coupons"
_LIST_URL = (_BASE + "/list?id=&couponType=&status=&name=&requestStartAt={start}&requestEndAt={end}"
             "&badDiscount=&beforeCouponStart=&page={page}&contractId=-1")
_ITEMS_URL = _BASE + "/{coupon_id}/items?page={page}&badDiscount="
_MAX_PAGES = 500   # 페이지가 끝나지 않는 응답 대비 상한(넘으면 실패로 남김)


class CouponFetchError(Exception):
    """쿠폰 조회 실패(비200·JSON 아님·응답 모양 다름·건수 모자람)."""


def _rows(data, what: str) -> list:
    rows = data.get("content") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        keys = list(data)[:8] if isinstance(data, dict) else type(data).__name__
        raise CouponFetchError(f"{what} 응답에 content 칸 없음(칸: {keys})")
    return rows


def _is_last(data: dict, n: int, seen: int) -> bool:
    """응답이 알려 주는 끝 판정. 끝을 안 알려 주면 False(빈 페이지까지 읽음)."""
    total, pages = data.get("totalElements"), data.get("totalPages")
    if isinstance(total, int):
        return seen >= total
    if isinstance(pages, int):
        return n + 1 >= pages
    return data.get("last") is True


def _read_pages(get, url_of, what: str, pages: list) -> None:
    """page 0부터 끝까지 응답 전체를 pages 에 추가. 새 줄이 없는 페이지(서버가 page 를 무시)에서 멈추고, 알려 준 건수보다
    모자라면 조용히 넘어가지 않고 실패로 남긴다. 응답은 검사 전에 담는다(모양이 달라도 원본이 파일에 남아 원인을 볼 수 있게)."""
    seen: set[str] = set()
    for n in range(_MAX_PAGES):
        data = get(url_of(n), f"{what} page {n}")
        pages.append(data)
        new = {json.dumps(r, ensure_ascii=False, sort_keys=True) for r in _rows(data, what)} - seen
        seen |= new
        if not new or _is_last(data, n, len(seen)):
            break
    else:
        raise CouponFetchError(f"{what} {_MAX_PAGES}페이지 넘음")
    total = data.get("totalElements")
    if isinstance(total, int) and len(seen) < total:
        raise CouponFetchError(f"{what} {total}건 중 {len(seen)}건만 읽음")


def _coupon_ids(list_pages: list) -> list[str]:
    ids = [str(r.get("couponId") or "") for p in list_pages for r in p["content"]]
    if "" in ids:
        raise CouponFetchError("쿠폰 목록에 couponId 없는 줄")
    return list(dict.fromkeys(ids))


def collect(page, *, start: str = "", end: str = "", rest=None) -> dict:
    """쿠폰 목록 전부 + 쿠폰별 옵션 전부를 읽음. 저장은 안 함(기간을 넓힌 라이브 확인도 이 함수로).

    start·end = 조회 주소의 requestStartAt·requestEndAt. 빈 값 = 화면과 같은 범위(최근 90일). 넣는 값의 형식은 아직 미확인.
    rest() = 조회 사이 쉼(첫 조회 전엔 안 부름). 실패해도 raise 하지 않고 '오류' 칸에 사유·그때까지 받은 응답을 돌려줌.
    반환 칸: 조회기간·쿠폰수·호출수·오류·목록(응답 전체 목록)·옵션({couponId: 응답 전체 목록})."""
    rec: dict = {"조회기간": {"requestStartAt": start, "requestEndAt": end}, "쿠폰수": 0, "호출수": 0, "오류": "",
                 "목록": [], "옵션": {}}

    def get(url: str, what: str):
        if rec["호출수"] and rest:
            rest()
        rec["호출수"] += 1
        res = page.evaluate(_GET_JSON_JS, url)
        status, body = res.get("status"), res.get("body", "")
        if status != 200:
            raise CouponFetchError(f"{what} 응답 status={status}"
                                   f"{' (XSRF 토큰 없음)' if not res.get('hasToken') else ''} · 응답본문: {str(body)[:300]}")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise CouponFetchError(f"{what} JSON 파싱 실패: {exc}") from exc

    q_start, q_end = quote(str(start), safe=""), quote(str(end), safe="")
    try:
        _read_pages(get, lambda n: _LIST_URL.format(start=q_start, end=q_end, page=n), "쿠폰 목록", rec["목록"])
        ids = _coupon_ids(rec["목록"])
        rec["쿠폰수"] = len(ids)
        for cid in ids:
            rec["옵션"][cid] = []
            _read_pages(get, lambda n: _ITEMS_URL.format(coupon_id=cid, page=n), f"쿠폰 {cid} 옵션", rec["옵션"][cid])
    except Exception as exc:   # 부가 기능 — 어떤 실패도 ① 수집을 막지 않음(브라우저 오류 포함·호출부가 로그로 명시)
        rec["오류"] = f"{exc.__class__.__name__}: {str(exc)[:400]}"
    return rec


def record_day(page, account_id: str, out_dir, log, gap=(0.0, 0.0), start: str = "", end: str = "") -> None:
    """그날 쿠폰을 읽어 계정·날짜 파일로 저장(동작 규칙 = 모듈 설명). 실패는 비치명(로그만·수집은 계속)."""
    dirname = daily_snapshot.COUPON_DIRNAME
    if daily_snapshot.has_day(out_dir, dirname, account_id):
        log(f"  [쿠폰] {account_id} 오늘 완료본 있음 — 다시 조회 안 함")
        return
    rec = collect(page, start=start, end=end, rest=lambda: time.sleep(random.uniform(*gap)))
    if rec["오류"]:
        log(f"  [쿠폰] ⚠ {account_id} 조회 실패 — 이 계정 쿠폰 조회 중단(다음 실행이 다시 받음) · {rec['오류'][:200]}")
    if not rec["목록"]:
        return
    try:
        path = daily_snapshot.save(out_dir, dirname, account_id, rec, partial=bool(rec["오류"]))
    except OSError as exc:
        log(f"  [쿠폰] ⚠ {account_id} 저장 실패(비치명) — {exc.__class__.__name__}: {str(exc)[:80]}")
        return
    log(f"  [쿠폰] {account_id} {'부분 저장' if rec['오류'] else '쿠폰'} {rec['쿠폰수']}건·조회 {rec['호출수']}회 → {path}")
