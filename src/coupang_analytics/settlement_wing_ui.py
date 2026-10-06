"""WING 정산 화면 조작 — 정산현황(윙)·로켓그로스 정산현황 표 읽기·'엑셀 다운로드 요청'·다운로드 목록에서 받기.

정산 엑셀은 **요청형**(실측 2026-10-06): 윙 [엑셀 다운로드 요청] → '정산관리 엑셀 다운로드 목록' WAIT→FINISHED,
로켓그로스 [엑셀 다운로드 ⋮]→리포트 선택 → 목록 '진행중'→완료. 그래서 N일 요청, N+1일 받기(settlement_jobs).

⚠ 화면 구조(표 머리글·버튼 글자)는 소유자 스크린샷 기준이고 **라이브 미확인**. 화면이 다르면 조용히 넘어가지 않고
UiChangedError(무엇을 찾았고 무엇이 없었는지)를 낸다. 사무실 첫 실행은 `tools/settlement_download.py probe`.
화면에서 글자를 정산 일정으로 바꾸는 부분은 순수 함수(parse_*)로 분리해 오프라인 검증한다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .settlement_jobs import DownloadRow, SettleEvent

WING_URL = "https://wing.coupang.com/tenants/msf/wing/view/payment-report-view"
RG_URL = "https://wing.coupang.com/tenants/rfm/settlements/status-new"
WING_HEADERS = ("정산일", "정산유형", "지급비율", "구매확정기간", "정산상태", "최종지급액")
RG_HEADERS = ("정산일", "정산유형", "지급비율", "매출인식일", "최종지급액")
WING_LIST_HEADERS = ("요청일시", "메뉴명", "검색조건", "상태")
RG_LIST_HEADERS = ("요청일시", "상태", "리포트")
BTN_WING_REQUEST = "엑셀 다운로드 요청"
BTN_RG_DOWNLOAD = "엑셀 다운로드"
BTN_SEARCH = "검색"
BTN_LIST = "정산관리 엑셀 다운로드 목록"
BTN_REFRESH = "새로 고침"
BTN_GET = "다운로드"
RG_REPORTS = ("판매수수료", "입출고/배송비", "보관비", "반품 회수/재입고 비용", "반출비", "반출 배송 서비스비",
              "재고 손실 보상", "부가서비스비", "리뷰 이벤트 비용")
_KIND = {"주정산": "주정산", "최종액정산": "최종액", "월정산": "월정산", "주별": "주정산", "월별": "월정산"}
ROW_KEY = "_행"                     # read_table 이 붙이는 화면 줄 번호
_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})")


class UiChangedError(Exception):
    """화면 구조가 예상과 다름 — 요청/받기 중단(추측으로 다른 버튼을 누르지 않음)."""


# ── 순수 변환(오프라인 검증) ──────────────────────────────────────
def parse_range(text: str) -> tuple[date, date]:
    m = _RANGE.search(str(text))
    if not m:
        raise UiChangedError(f"기간 글자를 읽지 못함: {text!r}")
    return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))


def _kind(text: str) -> str:
    k = _KIND.get(str(text).strip())
    if k is None:
        raise UiChangedError(f"모르는 정산유형: {text!r}")
    return k


def parse_wing_rows(rows: list[dict], account: str) -> list[tuple[SettleEvent, int]]:
    """윙 정산현황 표 줄({머리글: 글자}) → (정산 일정, 줄 번호). 정산확정만(예정·보류는 파일이 아직 확정 아님)."""
    out = []
    for i, r in enumerate(rows):
        if r.get("정산상태", "").strip() != "정산확정":
            continue
        ps, pe = parse_range(r["구매확정기간"])
        out.append((SettleEvent(account, "윙", _kind(r["정산유형"]), date.fromisoformat(r["정산일"].strip()), ps, pe),
                    r.get(ROW_KEY, i)))
    return out


def parse_rg_rows(rows: list[dict], account: str) -> list[tuple[SettleEvent, int]]:
    """로켓그로스 정산현황 표 줄 → (정산 일정, 줄 번호). 같은 매출 주가 70%·30% 두 줄로 나오지만 요청은 기간당 1번
    (settlement_jobs 키). 비용 리포트는 상세보기 금액 확인 전이라 판매수수료만(reports=())."""
    out = []
    for i, r in enumerate(rows):
        ps, pe = parse_range(r["매출인식일"])
        out.append((SettleEvent(account, "로켓그로스", _kind(r["정산유형"]), date.fromisoformat(r["정산일"].strip()),
                                ps, pe), r.get(ROW_KEY, i)))
    return out


def report_key(text: str) -> str:
    """'리포트 : 판매수수료 리포트' → '판매수수료'. 모르는 리포트면 UiChangedError."""
    t = re.sub(r"^\s*리포트\s*:\s*", "", str(text)).strip()
    t = re.sub(r"\s*리포트\s*$", "", t)
    if t not in RG_REPORTS:
        raise UiChangedError(f"모르는 로켓그로스 리포트: {text!r}")
    return t


def parse_list_rows(rows: list[dict], channel: str) -> list[DownloadRow]:
    """'정산관리 엑셀 다운로드 목록' 줄 → DownloadRow(handle = 목록 줄 번호). 윙=검색조건 기간, 로켓그로스=리포트."""
    out = []
    for i, r in enumerate(rows):
        at = datetime.fromisoformat(r["요청일시"].strip())
        if channel == "윙":
            if "주문 상세" not in r.get("메뉴명", ""):
                continue                                  # 부가세 신고 내역 등 다른 메뉴 요청은 무시
            ps, pe = parse_range(r["검색조건"].replace(" - ", " ~ "))
            out.append(DownloadRow("윙", at, r["상태"].strip(), "주문상세", ps, pe, handle=r.get(ROW_KEY, i)))
        else:
            out.append(DownloadRow("로켓그로스", at, r["상태"].strip(), report_key(r["리포트"]), handle=r.get(ROW_KEY, i)))
    return out


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end] 를 달 단위 조회 구간으로(화면 기간 검색 1회 = 1달)."""
    out, cur = [], start
    while cur <= end:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((cur, min(end, nxt - timedelta(days=1))))
        cur = nxt
    return out


# ── 화면 조작(라이브 전용·사무실) ─────────────────────────────────
_TABLES_JS = """
(must) => {
  const norm = s => (s || '').replace(/\\s+/g, '');
  const res = [];
  document.querySelectorAll('table').forEach((t, ti) => {
    const ths = [...t.querySelectorAll('thead th')].map(th => norm(th.innerText));
    const ok = must.every(m => ths.includes(norm(m)));
    if (!ok) return;
    const rows = [...t.querySelectorAll('tbody tr')].map(tr =>
      [...tr.querySelectorAll('td')].map(td => (td.innerText || '').trim()));
    res.push({ti, ths, rows});
  });
  return res;
}
"""
_HEADS_JS = "() => [...document.querySelectorAll('table thead')].map(h => (h.innerText||'').replace(/\\s+/g,' ').trim())"


def read_table(page, must: tuple) -> tuple[int, list[dict]]:
    """머리글이 must 를 모두 포함하는 표 → (표 번호, [{머리글: 글자}]). 없거나 둘 이상이면 UiChangedError."""
    found = page.evaluate(_TABLES_JS, list(must))
    if len(found) != 1:
        heads = page.evaluate(_HEADS_JS)
        raise UiChangedError(f"머리글 {must} 표를 {len(found)}개 찾음(1개여야 함) — 화면의 표 머리글: {heads}")
    t = found[0]
    cols = [re.sub(r"\s+", "", h) for h in t["ths"]]
    rows = [{**dict(zip(cols, cells)), ROW_KEY: i}                    # 화면 원래 줄 번호(클릭 위치)
            for i, cells in enumerate(t["rows"]) if len(cells) >= len(must)]   # 합계 줄 등은 제외
    return t["ti"], rows


def _row(page, table_index: int, row_index: int):
    return page.locator("table").nth(table_index).locator("tbody tr").nth(row_index)


def click_in_row(page, table_index: int, row_index: int, text: str, *, timeout: float = 8000) -> None:
    btn = _row(page, table_index, row_index).get_by_text(text, exact=True)
    if btn.count() != 1:
        raise UiChangedError(f"표 {table_index} {row_index}번째 줄에서 '{text}' 버튼을 {btn.count()}개 찾음(1개여야 함)")
    btn.click(timeout=timeout)


def choose_menu_item(page, text: str, *, timeout: float = 8000) -> None:
    item = page.get_by_text(re.compile(rf"^\s*{re.escape(text)}\s*리포트\s*$"))
    if item.count() != 1:
        raise UiChangedError(f"'{text} 리포트' 메뉴 항목을 {item.count()}개 찾음(1개여야 함)")
    item.click(timeout=timeout)


def click_button(page, text: str, *, timeout: float = 8000) -> None:
    btn = page.get_by_role("button", name=text, exact=True)
    if btn.count() < 1:
        raise UiChangedError(f"'{text}' 버튼을 찾지 못함")
    btn.first.click(timeout=timeout)


_DATE_INPUTS_JS = """
() => [...document.querySelectorAll('input')].map((el, i) => ({i, v: el.value || ''}))
      .filter(x => /^\\d{4}(-\\d{2}-\\d{2}|\\.\\s?\\d{1,2}\\.\\s?\\d{1,2}\\.?)$/.test(x.v.trim()))
"""


def set_period(page, start: date, end: date) -> None:
    """기간 입력칸 2개(시작·끝)를 같은 글자 형식으로 바꿔 넣고 [검색]. 입력칸이 2개가 아니면 UiChangedError."""
    found = page.evaluate(_DATE_INPUTS_JS)
    if len(found) != 2:
        raise UiChangedError(f"기간 입력칸을 {len(found)}개 찾음(2개여야 함): {[f['v'] for f in found]}")
    for f, d in zip(found, (start, end)):
        v = f["v"].strip()
        text = d.isoformat() if "-" in v else f"{d.year}. {d.month}. {d.day}."
        box = page.locator("input").nth(f["i"])
        box.click()
        box.fill(text)
        box.press("Enter")
    click_button(page, BTN_SEARCH)
    page.wait_for_load_state("networkidle", timeout=30000)
