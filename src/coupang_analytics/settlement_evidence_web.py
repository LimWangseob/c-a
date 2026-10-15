"""정산 증빙 원본 전체 받기 — 쿠팡 화면 단계(D-067). 2026-10-15 니코에이블에서 실제로 받힌 방식 그대로.

각 함수 = (T, b, …) → 단계 결과 dict {"결과": 정상|실패|없음, "내용": 설명, "파일": 개수}.
T = 정산다운로드 모듈(goto·api·log·_get_bytes — 차단 검사·재시도 포함), b = 로그인된 WingBrowser.
⚠ 쿠팡 화면 인쇄(PDF)는 구매자 정보가 없는 화면만: 윙 '미리보기'(주문·구매자 목록)는 누르지 않고, 인쇄 직전 화면에
구매자 낱말이 있으면 인쇄하지 않는다. 광고센터 마케팅 동의 창은 동의·비동의를 저장하지 않고 닫기만 한다.
"""
from __future__ import annotations

import base64
import json
import random
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

from . import settlement_evidence as EV
from . import settlement_wing_api as API

W = "https://wing.coupang.com"
REFUND_URL = f"{W}/tenants/finance/wing/contentsurl/favorablefee/refund/list"
RG_PAGES = {"광고비": f"{W}/tenants/rfm-portal-2/cmg/settlement", "밀크런": f"{W}/tenants/rfm-portal-2/milkrun/settlement"}
REFUND_EXCEL = "FAVORABLE_FEE_DETAIL"               # 정산관리 엑셀 다운로드 목록의 환급 엑셀 종류(실측)
PII_WORDS = ("주문자", "구매자명", "수취인")
CFS_KINDS = ("부가서비스비", "입출고/배송비", "보관비", "반품 회수/재입고 비용", "반출비")
SALES_MENUS = (("기간별 판매", "기간별판매"), ("상품별 판매", "상품별판매"))
GAP = (6, 12)
_SET_VALUE = """([sel, v]) => { const e = document.querySelector(sel); if (!e) return false;
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, v);
  e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); return e.value; }"""
_SHOW_DATES = """([f, t]) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  const ins = [...document.querySelectorAll('input')].filter(e => /^\\d{4}-\\d{2}-\\d{2}$/.test(e.value));
  if (ins.length >= 2) { set.call(ins[0], f); set.call(ins[1], t); } return ins.map(e => e.value); }"""
_CLOSE_POPUP = """() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const boxes = [...document.querySelectorAll('[role=dialog],[class*=modal],[class*=Modal]')]
    .filter(e => { const r = e.getBoundingClientRect(); return vis(e) && r.width > 300 && r.height > 150; });
  for (const d of boxes) { const r = d.getBoundingClientRect();
    const btn = [...d.querySelectorAll('button')].filter(x => vis(x) && !(x.innerText || '').trim())
      .map(x => [x, x.getBoundingClientRect()]).filter(([x, br]) => br.top < r.top + 90 && br.left > r.left + r.width * 0.6)
      .sort((u, v) => v[1].right - u[1].right)[0];
    if (btn) { btn[0].click(); return (d.innerText || '').trim().slice(0, 30); } }
  return null; }"""
_CLOSE_TITLED = """(title) => { const t = [...document.querySelectorAll('*')].find(e => e.childElementCount === 0
    && (e.textContent || '').trim() === title && e.getBoundingClientRect().width > 0);
  if (!t) return null; let box = t;
  while (box && !(box.getBoundingClientRect().width > 500 && box.getBoundingClientRect().height > 250)) box = box.parentElement;
  if (!box) return 'no-box'; const r = box.getBoundingClientRect();
  const c = [...box.querySelectorAll('button,[role=button],svg,i,span,img')].map(x => [x, x.getBoundingClientRect()])
    .filter(([x, q]) => q.width > 4 && q.width < 60 && q.top < r.top + 90 && q.left > r.left + r.width * 0.7 && !(x.textContent || '').trim())
    .sort((u, v) => v[1].right - u[1].right)[0];
  if (!c) return 'no-x'; const el = c[0].closest('button,[role=button]') || c[0];
  el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window})); return 'closed'; }"""
_HIDE_FLOAT = """() => { for (const e of document.querySelectorAll('div,section,aside')) { const t = (e.innerText || '');
  if (t.startsWith('페이지 별점을 주세요')) e.style.display = 'none'; } }"""


def _res(result: str, note: str, n: int = 0) -> dict:
    return {"결과": result, "내용": note, "파일": n}


def _pdf(b, page, dst: Path, wide: bool = True) -> None:
    body = page.locator("body").inner_text()
    if any(w in body for w in PII_WORDS):
        raise RuntimeError(f"화면에 구매자 정보 낱말 — 인쇄 안 함: {dst.name}")
    opts = {"printBackground": True, **({"paperWidth": 17, "paperHeight": 24} if wide else {})}
    res = b.context.new_cdp_session(page).send("Page.printToPDF", opts)
    dst.write_bytes(base64.b64decode(res["data"]))


def _rows(p: Path) -> list[list]:
    ws = openpyxl.load_workbook(p, read_only=True, data_only=True).worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True) if r and any(c not in (None, "") for c in r)]


# ── 판매분석 월별 원본 ───────────────────────────────────────────
def _sales_one(T, b, ws: date, we: date, menu: str, tag: str, out: Path) -> Path:
    from . import collector as C
    last = None
    for attempt in range(1, 4):                       # 메뉴 미노출·다운로드 지연 = 화면 다시 열어 최대 3번(실측)
        try:
            got = C.download_report(b.page, ws.isoformat(), we.isoformat(), out_dir=out / "_받는중", log=T.log, menu=menu)
            dst = out / f"쿠팡_판매분석_{tag}_{ws:%Y%m%d}-{we:%Y%m%d}.xlsx"
            shutil.copyfile(got, dst)
            shutil.rmtree(got.parent, ignore_errors=True)
            return dst
        except Exception as exc:                      # 그 창만 다시(3번 다 실패하면 올림 — 호출부가 실패 기록)
            last = exc
            T.log(f"  ⚠ 판매분석 {ws}~{we} {menu} 받기 실패({attempt}/3) — {exc.__class__.__name__}")
            time.sleep(random.uniform(*GAP))
    raise RuntimeError(f"판매분석 {ws}~{we} {menu} 3번 실패: {last}")


def sales_originals(T, b, start: date, end: date, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    bad, n = [], 0
    for _, ws, we in EV.month_windows(start, end):
        daily = _sales_one(T, b, ws, we, *SALES_MENUS[0], out)
        time.sleep(random.uniform(*GAP))
        items = _sales_one(T, b, ws, we, *SALES_MENUS[1], out)
        n += 2
        dr, ir = _rows(daily), _rows(items)
        if len(dr) == 1 and len(ir) == 1:              # 두 파일 모두 머리글뿐 = 그 달 활동 없음
            continue
        ok_d, note_d, q, m = EV.check_daily(dr, ws, we)
        ok_i, note_i = EV.check_items(ir, q, m)
        if not (ok_d and ok_i):
            bad.append(f"{ws:%Y-%m} {note_d} / {note_i}")
        time.sleep(random.uniform(*GAP))
    shutil.rmtree(out / "_받는중", ignore_errors=True)
    return _res(EV.FAIL if bad else EV.OK, "; ".join(bad) or f"{n}개·누락 검사 통과", n)


# ── 우대수수료 환급 엑셀(요청 → 정산관리 엑셀 다운로드 목록) ─────────────────
def _refund_request_month(p, ws: date, we: date) -> bool:
    p.evaluate(_SET_VALUE, ["input[name=from]", ws.isoformat()])
    p.evaluate(_SET_VALUE, ["input[name=to]", we.isoformat()])
    p.get_by_role("button", name="검색").first.click()
    time.sleep(6)
    if p.locator("text=조회된 정보가 없습니다").count():
        return False
    p.get_by_text("엑셀 다운로드", exact=True).first.click()
    time.sleep(2)
    p.locator(".modal.in").last.locator("button", has_text="확인").first.click(timeout=10000)
    time.sleep(3)
    for k in range(p.locator(".modal.in").count()):   # '목록으로 이동?' 창 = 취소(이동 안 함)
        m = p.locator(".modal.in").nth(k)
        if m.is_visible():
            m.locator("button", has_text="취소").first.click(timeout=10000)
    return True


def refund_request(T, b, label: str, start: date, end: date) -> dict:
    """조회 기간 한 달 제한(실측) → 지급일 기준 달마다 엑셀 요청. 생성이 10분 넘게 걸려(실측) 받기는 다른 단계 뒤(refund_fetch)."""
    p, t0, asked = b.page, datetime.now() - timedelta(minutes=1), 0
    T.goto(b, REFUND_URL, label)
    time.sleep(4)
    p.check("input[name=dateType][value=TRANSFER]")
    for _, ws, we in EV.month_windows(start, end - timedelta(days=1)):
        asked += _refund_request_month(p, ws, we)
        time.sleep(random.uniform(*GAP))
    res = _res(EV.OK if asked else EV.NONE, f"요청 {asked}개월" if asked else "환급 내역 없음(전 기간 '조회된 정보가 없습니다')")
    return {**res, "요청": asked, "t0": t0.isoformat()}


def refund_fetch(T, b, label: str, req: dict, out: Path, wait_min: int = 20) -> dict:
    """정산관리 엑셀 다운로드 목록에서 이번에 요청한 환급 엑셀이 모두 FINISHED 가 되면 받기(그 전에 받으면 400 — 실측)."""
    if not req.get("요청"):
        return _res(EV.NONE, req.get("내용", "요청 없음"))
    out.mkdir(parents=True, exist_ok=True)
    t0, asked = datetime.fromisoformat(req["t0"]), req["요청"]
    T.goto(b, API.WING_URL, label)
    mine: list = []
    for k in range(wait_min):
        mine = [it for it in T.api(b, label, "GET", API.WING_LIST)
                if it.get("excelType") == REFUND_EXCEL and datetime.fromisoformat(it["startedAt"]) >= t0]
        if len(mine) >= asked and all(it.get("status") == "FINISHED" for it in mine):
            break
        time.sleep(60)
    got = 0
    for it in mine:
        if it.get("status") == "FINISHED":
            (out / EV.refund_file_name(it.get("jsonItems"), it["startedAt"])).write_bytes(T._get_bytes(b, it["downloadUrl"]))
            got += 1
    return _res(EV.OK if got >= asked else EV.FAIL, f"요청 {asked}개월 · 받음 {got}개", got)


# ── 윙 정산현황 지급 명세(금액 클릭 → 매출 상세내역) PDF ─────────────────
def wing_statements(T, b, label: str, start: date, end: date, out: Path) -> dict:
    """기간 칸 = 쿠팡 달력 부품(입력 안 됨·실측) → 화면이 보내는 조회 요청의 날짜만 달마다 바꾸고(조회 전용)
    기간 칸 표시도 같은 날짜로 맞춘 뒤 지급 줄을 모두 펼쳐 인쇄."""
    out.mkdir(parents=True, exist_ok=True)
    want: dict = {}

    def route(rt):
        body = json.loads(rt.request.post_data or "{}")
        body.update(want)
        rt.continue_(post_data=json.dumps(body))
    p, n_pay, n_pdf = b.page, 0, 0
    p.route("**/msf/wing/api/payment-report/list", route)
    try:
        T.goto(b, API.WING_URL, label)
        p.locator("button:visible", has_text="검색").first.wait_for(timeout=30000)
        for ym, ws, we in EV.month_windows(start, end):
            want.update({"searchDateType": "PAY_DATE", "fromDate": ws.isoformat(), "toDate": we.isoformat()})
            p.evaluate(_SHOW_DATES, [ws.isoformat(), we.isoformat()])
            p.get_by_role("button", name="검색").first.click()
            time.sleep(6)
            links = p.locator("table tbody tr td a.external-link")
            if not links.count():
                continue
            for k in range(links.count()):
                links.nth(k).click()
                time.sleep(2.5)
            p.evaluate(_HIDE_FLOAT)
            _pdf(b, p, out / f"쿠팡_윙_정산현황_지급명세_지급일_{ws:%Y%m%d}-{we:%Y%m%d}_{links.count()}건.pdf")
            n_pay += links.count()
            n_pdf += 1
            time.sleep(random.uniform(*GAP))
    finally:
        p.unroute("**/msf/wing/api/payment-report/list")
    return _res(EV.OK if n_pdf else EV.NONE, f"지급 {n_pay}건 · PDF {n_pdf}개", n_pdf)


# ── 로켓그로스 월렛·광고비·밀크런 ─────────────────────────────────
def _close_rg_notice(p) -> None:
    p.keyboard.press("Escape")
    time.sleep(1)
    for _ in range(4):                               # 일반 안내 창(오른쪽 위 X)
        if not p.evaluate(_CLOSE_POPUP):
            break
        time.sleep(1)
    modal = p.locator("div.wing-web-component[data-wuic-props*='name:modal']")
    for k in range(modal.count()):
        if modal.nth(k).is_visible():
            btn = modal.nth(k).locator("button", has_text="닫기")
            if btn.count():
                btn.first.click(timeout=5000)
                time.sleep(1)


def wallet(T, b, label: str, out: Path) -> dict:
    """가상계좌 내역보기(엑셀 없음) → 기간 '전체' → 쪽마다 인쇄."""
    out.mkdir(parents=True, exist_ok=True)
    p = b.page
    T.goto(b, API.RG_URL, label)
    time.sleep(6)
    _close_rg_notice(p)
    if not p.get_by_text("내역보기", exact=True).count():
        return _res(EV.NONE, "로켓그로스 월렛 없음(내역보기 버튼 없음)")
    for attempt in range(3):                         # 안내 창이 버튼을 가리면 닫고 다시(실측 1/3회)
        try:
            p.get_by_text("내역보기", exact=True).first.click(timeout=10000)
            break
        except Exception:
            if attempt == 2:
                raise
            _close_rg_notice(p)
    time.sleep(5)
    sel = p.locator("select").filter(has=p.locator("option", has_text="개월")).first
    opts = sel.locator("option").all_inner_texts()
    sel.select_option(label="전체" if "전체" in opts else opts[-1])
    time.sleep(4)
    pages = [t for t in p.locator("[class*=modal]").locator("button, a, li").all_inner_texts() if t.strip().isdigit()]
    n = max([int(x) for x in pages] or [1])
    for k in range(1, n + 1):
        if k > 1:
            p.locator(f"xpath=//*[self::button or self::a or self::li or self::span][normalize-space(text())='{k}']").first.click()
            time.sleep(3)
        _pdf(b, p, out / f"쿠팡_로켓그로스_가상계좌거래내역_전체_{k}쪽_인쇄{date.today():%Y%m%d}.pdf", wide=False)
    return _res(EV.OK, f"{n}쪽", n)


def rg_ad_milkrun(T, b, label: str, start: date, end: date, out: Path) -> dict:
    """로켓그로스 광고비 내역·밀크런 내역 — 달마다 조회 → 화면 인쇄(엑셀 버튼은 파일이 안 내려옴·실측)."""
    out.mkdir(parents=True, exist_ok=True)
    p, n = b.page, 0
    for kind, url in RG_PAGES.items():
        T.goto(b, url, label)
        time.sleep(4)
        for ym, _, _ in EV.month_windows(start, end):
            p.select_option("select[name=searchYear]", ym[:4])
            p.select_option("select[name=searchMonth]", str(int(ym[4:])))
            p.get_by_role("button", name="검색").first.click()
            time.sleep(5)
            if p.locator("text=/검색\\s?결과가 없습니다/").count() >= 2:   # 요약·상세 둘 다 비면 그 달 없음
                continue
            _pdf(b, p, out / f"쿠팡_로켓그로스_{kind}내역_{ym}_화면인쇄.pdf")
            n += 1
            time.sleep(random.uniform(*GAP))
    return _res(EV.OK if n else EV.NONE, f"PDF {n}개", n)


# ── 광고센터 월별 광고비 정산내역 보고서 ─────────────────────────────
def _open_adcenter(T, b, label: str):
    T.goto(b, API.WING_URL, label)
    with b.context.expect_page(timeout=20000) as np:
        b.page.locator("a", has_text="광고센터").first.click()
    q = np.value
    q.wait_for_load_state("domcontentloaded")
    time.sleep(8)
    for _ in range(6):                               # 안내·동의 창 = 오른쪽 위 글자 없는 닫기(X)만(동의·이동 버튼 안 누름)
        closed = q.evaluate(_CLOSE_POPUP)
        if not closed:
            break
        T.log(f"  광고센터 안내 창 닫음: {closed}")
        time.sleep(1.5)
    title = q.get_by_text("마케팅 활용 및 광고 수신", exact=True)   # 창 제목(배너 문장 안의 같은 말은 제외 — 실측 오인)
    if title.count() and title.first.is_visible():
        T.log(f"  광고센터 동의 창 닫기: {q.evaluate(_CLOSE_TITLED, '마케팅 활용 및 광고 수신')}")
        time.sleep(1.5)
    if title.count() and title.first.is_visible():
        raise RuntimeError("광고센터 마케팅 동의 창이 닫히지 않음 — 동의는 누르지 않고 중단")
    q.get_by_text("광고보고서", exact=True).first.click()
    time.sleep(6)
    q.get_by_text("광고비 정산 보고서", exact=True).first.click()
    time.sleep(2)
    q.get_by_text("월별 광고비 정산내역 보고서").first.click()
    time.sleep(4)
    return q


def adcenter_monthly(T, b, label: str, start: date, end: date, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    q, n, skipped = _open_adcenter(T, b, label), 0, []
    try:
        for ym, _, _ in EV.month_windows(start, end):
            q.locator("text=/\\d{4}년 \\d{2}월/").first.click()
            time.sleep(1.5)
            opt = q.get_by_text(f"{ym[:4]}년 {ym[4:]}월", exact=True)
            if not opt.count():                       # 이번 달은 아직 선택지 없음(지난달까지)
                q.keyboard.press("Escape")
                skipped.append(ym)
                continue
            opt.last.click()
            time.sleep(1)
            q.get_by_role("button", name="보고서 만들기").first.click()
            time.sleep(10)
            _pdf(b, q, out / f"쿠팡광고센터_월별광고비정산내역보고서_{ym}_화면인쇄.pdf")
            n += 1
            time.sleep(random.uniform(*GAP))
    finally:
        q.close()
    return _res(EV.OK if n else EV.NONE, f"PDF {n}개" + (f" · 선택지 없음 {skipped}" if skipped else ""), n)


# ── 정산 줄 없는 주의 비용 리포트(묶음 키로 요청) ─────────────────────────
def _rg_reports(T, b, label: str, start: date, end: date) -> list:
    T.goto(b, API.RG_URL, label)
    out: list = []
    for ws, we in API.month_windows(start, end):
        out += T.api(b, label, "POST", API.RG_EVENTS, API.rg_events_body(ws, we)).get("settlementStatusReports") or []
        time.sleep(random.uniform(3, 8))
    return out


def missing_week_costs(T, b, label: str, start: date, end: date, out: Path) -> dict:
    keys = EV.missing_cost_weeks(_rg_reports(T, b, label, start, end))
    if not keys:
        return _res(EV.NONE, "정산 줄 없는 주의 물류비 없음")
    t0, asked = datetime.now() - timedelta(minutes=1), {}
    for key in keys:
        for kind in CFS_KINDS:
            body = {"sellerReportType": API._RG_REPORT[kind], "requestTime": str(int(time.time() * 1000)),
                    "settlementGroupKeys": [key], "locale": "ko"}
            asked[API.rg_request_id(T.api(b, label, "POST", API.RG_REQUEST, body))] = (key, kind)
            time.sleep(random.uniform(*T.GAP_SEC))
    time.sleep(90)
    got = 0
    for it in T.api(b, label, "POST", API.RG_LIST, API.rg_list_body(t0, datetime.now())):
        if it.get("requestId") not in asked or it.get("downloadStatus") != "COMPLETED":
            continue
        key, kind = asked[it["requestId"]]
        url = T.api(b, label, "POST", API.RG_GET, {"requestTime": it["requestTime"], "locale": "ko"}).get("url")
        s, e = key.split("-", 1)[1][:10].replace("-", ""), key.split("-", 1)[1][11:].replace("-", "")
        dst = out / f"{label}_정산줄없음_로켓그로스_주정산_{kind.replace('/', '-').replace(' ', '-')}_{s}-{e}.xlsx"
        dst.write_bytes(T._get_bytes(b, url))
        got += 1
    return _res(EV.OK if got == len(asked) else EV.FAIL, f"주 {keys} · 요청 {len(asked)} · 받음 {got}", got)
