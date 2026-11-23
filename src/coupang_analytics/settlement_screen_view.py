"""윙 화면 보기 + 화면이 스스로 받은 응답 기록(T-122 · D-334 · D-340 · D-296 방식) — 정산 미확정 항목 자료 받기 틀.

규칙(D-273·D-276·D-277·D-296·D-340): 소유자가 로그인한 세션에서 **주소 이동 + 조회 전용 버튼만** · 화면이 받은 응답을
`page.on("response")` 로 옆에서 기록(페이지 안 스크립트·fetch·API 직접 호출 없음) · 동의·신청·저장·'보고서 만들기'·상품 수정 화면 금지 ·
조회 전용인지 애매한 버튼은 누르지 않음(NotViewOnly = 확인 필요) · 프록시 없음 · 첫 실제 시험 = 소유자 로그인 한 계정 1회.

칸 모양이 기록된 적 없는 응답(지금 전부 · T122_자료16종_화면근거_1118.md)은 **칸 이름·형만** 남긴다(값 없음 → 구매자 정보 등
개인정보를 저장하지 않음 · D-171). 첫 시험에서 칸 목록을 보고 '저장칸'을 정한 뒤(시험 기대값 = 그 실제 칸) 값 저장으로 바꾼다.
화면 주소·버튼 글자가 기록에 없는 출처는 NeedLive(사유) — 지어내지 않음.
저장 = output/정산/자료출처/화면응답/{출처ID}/{계정}/{YYYY-MM-DD}.json.gz (daily_snapshot · 덮어쓰지 않음).
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from . import daily_snapshot as DS

WING = "https://wing.coupang.com"
DIRNAME = "화면응답"
WAIT_MS = 5000                     # 보기 전환 뒤 화면이 표를 채우는 시간(S4 실측 2~5초)
VIEW_ONLY = frozenset({"검색", "조회", "구독 관리", "구독 내역 보기",
                       "검색 열기"})   # D-340 조회 전용(화면만 바꿈 · 근거표 7·12·13·17 · '검색 열기' = 검색 조건 펼치기 nicoable 11-23)
FORBIDDEN = ("동의", "신청", "저장", "보고서", "만들기", "해지", "변경", "가입", "구독하기", "삭제", "수정", "등록", "취소",
             "확인", "적용", "다운로드", "요청", "결제", "충전")
# 공지 팝업 닫기 글자 — 일반 버튼에는 쓰지 않음(check_button 은 그대로 거부). 출처 '팝업' 의 표지 글자가 전부 든 팝업 1개 안에서만,
# 그 팝업에 금지 낱말(닫기 글자 자신 빼고)이 없을 때만 누른다(nicoable 11-23 BI 공지 팝업 · Esc 로 안 닫힘 · '다시 보지 않기' 안 누름).
POPUP_CLOSE = frozenset({"확인"})
# 출처ID → 화면(None = 기록 없음) · 버튼(조회 전용 · 순서대로) · 응답(주소 경로 조각 — 이 조각이 든 응답만 기록) · 저장칸(None = 칸 이름만) ·
# 팝업(있으면 = 화면 열자마자 덮는 공지 팝업 {표지: 팝업에 든 글자들, 닫기: POPUP_CLOSE 글자}) ·
# ②번 = 정산자료_수집진행률_1118.md 2절 ②표 번호 · 없음 = 그 조각 기록 없음(NeedLive 사유).
SPECS: dict = {
    "SV-RG-HOME": {"②": 6, "화면": f"{WING}/tenants/rfm/settlements/home", "버튼": (), "응답": ("/tenants/rfm/",),
                   "저장칸": None, "설명": "로켓그로스 정산현황 홈 띠 '무료 체험 종료일'(이용권 관리·지금 가입 버튼 금지)"},
    "SV-NOTICES": {"②": 5, "화면": f"{WING}/tenants/wing-account/partner/notices?page=0&keyword=", "버튼": (),
                   "응답": ("/tenants/wing-account/",), "저장칸": None, "설명": "윙 공지 목록(본문 주소 = 기록 없음 · 첫 시험 뒤)"},
    "SV-RETURN-CHANNEL": {"②": 7, "화면": f"{WING}/tenants/sfl-portal/return-delivery/list", "버튼": ("검색 열기", "검색"),
                          "응답": ("/tenants/sfl-portal/return-delivery/search",), "저장칸": None,
                          "설명": "반품 접수채널(T-118 · D-333) — 응답 칸(접수채널 칸 이름) 기록 없음 · 구매자 정보 = 값 저장 안 함"},
    "SV-RETURN-BOX": {"②": 12, "화면": None, "버튼": (), "응답": (), "저장칸": None,
                      "없음": "반출/과잉재고 관리 화면 주소 기록 없음(메뉴 이름만) · 반출 '신청' 단계는 신청 흐름 — 조회 화면 위치부터",
                      "설명": "반출 박스 유형(지난 반출 = 반출 배송 서비스비 리포트 원문에 있음)"},
    "SV-SALES-F": {"②": 13, "화면": f"{WING}/tenants/finance/wing/contentsurl/sales-report", "버튼": (), "응답": (),
                   "저장칸": None, "없음": "정산차감액(F) 클릭 대상 글자·응답 주소 기록 없음(seankim137 로그인 막힘 T-5)",
                   "설명": "매출내역 F(정산차감) 상세 팝업(T-39)"},
    "SV-BI-SUB": {"②": 17, "화면": f"{WING}/tenants/business-insight/sales-analysis", "버튼": ("구독 관리", "구독 내역 보기"),
                  "응답": ("/tenants/rfm-ss/api/subscription/",), "저장칸": None,
                  "팝업": {"표지": ("베타 버전 출시", "다시 보지 않기"), "닫기": "확인"},
                  "설명": "비즈니스 인사이트 플랜·유료 시작일(T-121·T-116 · 구독 해지하기·카테고리 변경·다시 구독하기 금지)"},
    "SV-REVIEW-DETAIL": {"②": 15, "화면": f"{WING}/tenants/rfm-ss/manage-review-campaign/landing", "버튼": (), "응답": (),
                         "저장칸": None, "없음": "캠페인 상세(리뷰별) 화면 주소·여는 글자 기록 없음(목록만 받음)",
                         "설명": "리뷰별 생성일(리뷰 이벤트 관리 상세)"},
    "SV-AD-UNPAID": {"②": 16, "화면": None, "버튼": (), "응답": (), "저장칸": None,
                     "없음": "광고센터 미납·청구 화면 주소 기록 없음(광고센터 = 윙 메뉴 클릭으로만 로그인 없이 열림)",
                     "설명": "광고센터 미납·청구"},
    "SV-EXCHANGE": {"②": 18, "화면": None, "버튼": (), "응답": (), "저장칸": None,
                    "없음": "교환 관리 전체 주소 기록 없음(조각 /exchange/list) · 구매자 정보 화면(T-80 뒤 · D-291 ⑧)",
                    "설명": "교환 관리(산식 '해당 없음 · 감지용')"},
}


class NeedLive(Exception):
    """기록이 모자라 이 출처를 아직 못 받음 — 소유자 로그인 첫 시험(화면 구조 기록)이 먼저."""


class NotViewOnly(Exception):
    """조회 전용이 아니거나 애매한 버튼 — 누르지 않음(D-340 · 확인 필요)."""


def check_button(text: str) -> None:
    hit = [w for w in FORBIDDEN if w in text]
    if hit:
        raise NotViewOnly(f"'{text}' = 금지 낱말 {hit} — 누르지 않음")
    if text not in VIEW_ONLY:
        raise NotViewOnly(f"'{text}' = 조회 전용 목록 밖(애매) — 누르지 않음 · 확인 필요")


def check_popup(pop: dict) -> None:
    """공지 팝업 정의 판정(화면 열기 전) — 닫기 = POPUP_CLOSE 글자만 · 표지 1개 이상 · 표지에 금지 낱말 없음."""
    if pop.get("닫기") not in POPUP_CLOSE:
        raise NotViewOnly(f"팝업 닫기 '{pop.get('닫기')}' = 닫기 허용 목록 밖 — 누르지 않음")
    if not pop.get("표지"):
        raise NotViewOnly("팝업 표지 글자 없음 — 어느 팝업인지 몰라 누르지 않음")
    hit = [w for t in pop["표지"] for w in FORBIDDEN if w in t]
    if hit:
        raise NotViewOnly(f"팝업 표지 {list(pop['표지'])} 에 금지 낱말 {hit} — 누르지 않음")


def ready(spec: dict) -> None:
    """받을 수 있는 출처인지(누르기 전·화면 열기 전에 판정) — 아니면 NeedLive/NotViewOnly."""
    if not spec.get("화면") or not spec.get("응답"):
        raise NeedLive(spec.get("없음") or "화면 주소·응답 주소 기록 없음")
    for t in spec.get("버튼") or ():
        check_button(t)
    if spec.get("팝업"):
        check_popup(spec["팝업"])


def close_popup(page, pop: dict, wait_ms: int) -> str:
    """화면을 덮은 공지 팝업 닫기 — 표지 첫 글자가 안 보이면 '없음'. 보이면 표지 전부 든 dialog 1개 · 그 안 금지 낱말 0(닫기 글자 빼고) ·
    닫기 버튼 1개일 때만 누르고, 닫혔는지 다시 본다. 어긋나면 NeedLive/NotViewOnly(누르지 않음 · '다시 보지 않기' 는 안 누름)."""
    if page.get_by_text(pop["표지"][0]).count() == 0:
        return "없음"
    dlg = page.get_by_role("dialog")
    for t in pop["표지"]:
        dlg = dlg.filter(has_text=t)
    if dlg.count() != 1:
        raise NeedLive(f"팝업 표지 {list(pop['표지'])} 든 dialog {dlg.count()}개 — 팝업 구조 확인 필요(누르지 않음)")
    hit = [w for w in FORBIDDEN if w != pop["닫기"] and dlg.filter(has_text=w).count()]
    if hit:
        raise NotViewOnly(f"팝업에 금지 낱말 {hit} — '{pop['닫기']}' 누르지 않음 · 확인 필요")
    btn = dlg.get_by_role("button", name=pop["닫기"], exact=True)
    if btn.count() != 1:
        raise NeedLive(f"팝업 '{pop['닫기']}' 버튼 {btn.count()}개 — 팝업 구조 확인 필요(누르지 않음)")
    btn.click()
    page.wait_for_timeout(wait_ms)
    if dlg.count():
        raise NeedLive(f"팝업 '{pop['닫기']}' 눌렀는데 안 닫힘 — 확인 필요")
    return "닫음"


def schema(obj, path: str = "") -> list[str]:
    """응답 칸 이름·형만(값 없음) — 목록은 첫 원소 모양 + '[]'."""
    if isinstance(obj, dict):
        out = [f"{path}:object"] if path else []
        for k, v in obj.items():
            out += schema(v, f"{path}.{k}" if path else str(k))
        return out
    if isinstance(obj, list):
        return [f"{path}:list[{len(obj)}]"] + (schema(obj[0], f"{path}[]") if obj else [])
    return [f"{path}:{type(obj).__name__}"]


def _pick(obj, keys: tuple):
    return {k: obj.get(k) for k in keys} if isinstance(obj, dict) else None


def _entry(resp, keep) -> dict:
    u = urlsplit(resp.url)
    rec: dict = {"주소": u.path, "상태": resp.status}           # 쿼리(검색어·기간 등)는 남기지 않음
    try:
        body = resp.json()
    except Exception as exc:  # noqa: BLE001 — JSON 아닌 응답(HTML 등) = 형만 남김(조용히 버리지 않음)
        rec["JSON 아님"] = exc.__class__.__name__
        return rec
    rec["칸"] = schema(body)
    if keep:
        rec["값"] = _pick(body, keep)
    return rec


def capture(page, spec: dict, wait_ms: int = WAIT_MS) -> dict:
    """화면 열기 → 조회 전용 버튼 차례로 → 화면이 받은 응답(spec 조각) 기록. 페이지 안 스크립트 없음.
    반환 = {'화면': 주소 경로, '버튼': [...], '응답': [_entry…]} · 응답 0 = NeedLive(그 화면이 그 응답을 안 부름 — 기록 정정 필요)."""
    ready(spec)
    got: list = []
    frags = tuple(spec["응답"])

    def on_response(resp):
        if any(f in urlsplit(resp.url).path for f in frags):
            got.append(resp)
    page.on("response", on_response)
    popup = None
    try:
        page.goto(spec["화면"])
        page.wait_for_timeout(wait_ms)
        if spec.get("팝업"):
            popup = close_popup(page, spec["팝업"], wait_ms)
        for t in spec.get("버튼") or ():
            btn = page.get_by_role("button", name=t, exact=True)
            if btn.count() != 1:
                raise NeedLive(f"버튼 '{t}' {btn.count()}개 — 화면 구조 확인 필요(누르지 않음)")
            btn.click()
            page.wait_for_timeout(wait_ms)
    finally:
        page.remove_listener("response", on_response)
    if not got:
        raise NeedLive(f"화면이 {list(frags)} 응답을 부르지 않음 — 화면·응답 기록 정정 필요")
    rec = {"화면": urlsplit(spec["화면"]).path, "버튼": list(spec.get("버튼") or ()),
           "응답": [_entry(r, spec.get("저장칸")) for r in got]}
    if popup:
        rec["팝업"] = popup
    return rec


def save(base: Path, sid: str, account_id: str, rec: dict) -> Path:
    return DS.save(Path(base) / "자료출처" / DIRNAME, sid, account_id, rec)
