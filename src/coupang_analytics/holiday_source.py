"""공휴일 실 소스 — 한국천문연구원 특일정보 API(data.go.kr `getRestDeInfo`). SSOT=designs/SETTLEMENT_MODULE.md §2.

`holiday_kr.holidays(year, fetch=make_fetch(key))` 로 주입한다(연 단위 1회 조회 → holiday_kr 가 캐시).
- 공휴일 = 응답 항목 중 `isHoliday == 'Y'`. 대체공휴일·임시공휴일도 API 가 항목으로 준다(설계 §2 해석 = 결과 그대로 사용).
- 서비스키 = credstore `__holiday_kr__`(비밀·DPAPI). 키 등록은 설정 화면(UI 레인). 로그에 키를 남기지 않는다.
- **실패는 전부 예외**(키 없음·HTTP 오류·서비스 오류 코드·JSON 아닌 응답·건수 불일치) → holiday_kr 가
  HolidaySourceError 로 감싸 지급일 계산을 멈춘다(0일 가정 금지).
응답 특이점(공공데이터 공통): 항목 1개면 list 가 아니라 dict, 0개면 items 가 빈 문자열, 인증 오류는 `_type=json` 이어도
XML(`OpenAPI_ServiceResponse`)로 온다.
"""
from __future__ import annotations

import re
from datetime import date

ENDPOINT = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
CRED_KEY = "__holiday_kr__"
_ROWS = 100                                   # 한 해 공휴일(대체·임시 포함) < 100 → 한 쪽이면 충분(건수로 확인)
_TIMEOUT = 15


class HolidayApiError(Exception):
    """특일정보 API 가 정상 결과를 주지 않음(원인 문구 포함·키 값은 넣지 않음)."""


def _xml_reason(text: str) -> str:
    m = re.search(r"<returnAuthMsg>([^<]*)</returnAuthMsg>", text) or \
        re.search(r"<resultMsg>([^<]*)</resultMsg>", text)
    code = re.search(r"<returnReasonCode>([^<]*)</returnReasonCode>", text) or \
        re.search(r"<resultCode>([^<]*)</resultCode>", text)
    return f"{m.group(1) if m else '알 수 없음'} (코드 {code.group(1) if code else '?'})"


def _items(body: dict) -> list:
    items = body.get("items")
    if items in ("", None):
        return []
    item = items.get("item") if isinstance(items, dict) else None
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def parse_rest_days(payload: dict, year: int) -> set[date]:
    """응답 JSON → 그 해 공휴일 날짜 집합. 결과코드 이상·건수 불일치·형식 오류 = HolidayApiError."""
    try:
        header, body = payload["response"]["header"], payload["response"]["body"]
    except (KeyError, TypeError) as exc:
        raise HolidayApiError(f"특일정보 응답 형식이 예상과 다름: {str(payload)[:200]}") from exc
    if str(header.get("resultCode")) != "00":
        raise HolidayApiError(f"특일정보 서비스 오류: {header.get('resultMsg')} (코드 {header.get('resultCode')})")
    items = _items(body)
    total = int(body.get("totalCount") or 0)
    if total != len(items):
        raise HolidayApiError(f"특일정보 건수 불일치: 전체 {total}건 중 {len(items)}건만 받음(한 쪽 {_ROWS}건 초과?)")
    days = set()
    for it in items:
        if str(it.get("isHoliday", "")).upper() != "Y":
            continue
        s = str(it.get("locdate", ""))
        if not re.fullmatch(r"\d{8}", s):
            raise HolidayApiError(f"특일정보 날짜 형식 오류: {it!r}")
        d = date(int(s[:4]), int(s[4:6]), int(s[6:]))
        if d.year != year:
            raise HolidayApiError(f"{year}년 조회에 다른 해 날짜: {d}")
        days.add(d)
    return days


def make_fetch(service_key: str, *, http_get=None, timeout: float = _TIMEOUT):
    """holiday_kr.holidays(fetch=) 에 넣을 조회 함수. http_get = requests.get 호환(테스트 주입용)."""
    if not service_key or not str(service_key).strip():
        raise HolidayApiError("공휴일 API 서비스키가 없음 — 설정에서 data.go.kr 특일정보 키를 등록하세요")
    if http_get is None:
        import requests                           # 지연 import(순수 파싱과 분리)
        http_get = requests.get

    def fetch(year: int) -> set[date]:
        params = {"solYear": str(year), "numOfRows": str(_ROWS), "pageNo": "1", "_type": "json",
                  "ServiceKey": str(service_key).strip()}
        resp = http_get(ENDPOINT, params=params, timeout=timeout)
        text = resp.text or ""
        if resp.status_code != 200:
            raise HolidayApiError(f"특일정보 HTTP {resp.status_code}: {_xml_reason(text) if '<' in text else text[:120]}")
        if text.lstrip().startswith("<"):
            raise HolidayApiError(f"특일정보 인증/서비스 오류: {_xml_reason(text)}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise HolidayApiError(f"특일정보 응답이 JSON 이 아님: {text[:120]}") from exc
        return parse_rest_days(payload, year)
    return fetch


def fetch_from_store(store=None, **kw):
    """credstore 의 서비스키로 조회 함수 생성(없으면 HolidayApiError). 라이브 경로 전용."""
    if store is None:
        from .credstore import CredStore
        store = CredStore()
    return make_fetch(store.get_password(CRED_KEY) or "", **kw)
