"""구글 스프레드시트 읽기/쓰기 — **서비스계정 인증**(Sheets API v4).

용도(구글시트 완전 통합, designs/GSHEET_UNIFIED.md):
- **입력** = 「토탈셀러_셀독 관리 대장」(구글시트 원본)을 서비스계정으로 **직접 읽기**(다운로드 불필요).
  대장에 비번 평문이 있으므로 대장은 **서비스계정에만 공유**해 '링크가 있는 모든 사용자'를 끌 수 있다.
- **출력** = 결과 구글시트(`계정목록` + 사업자별 통계)를 서비스계정으로 **쓰기/서식**.

인증 키 출처(둘 중 하나, 설정 탭에서 1회 등록):
- credstore(DPAPI) 키 `__gsheet_sa__` 에 서비스계정 JSON **본문**을 저장(권장 — 이 PC 전용 암호화), 또는
- 로컬 JSON 파일 경로(git·공유 금지).

정책(CLAUDE.md): **fallback 금지.** 인증실패·권한없음(403)·없음(404)·쿼터초과(429)는 조용히 넘기지 않고
사유가 담긴 한국어 예외(`GSheetError`)로 올린다. 서비스계정 JSON 본문은 이 모듈이 디스크에 남기지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .credstore import CredStore
from .gsheet import sheet_id_from_url  # URL/ID 파서 재사용

# 읽기+쓰기(서식 포함) 모두 필요 → spreadsheets 전체 스코프.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CRED_KEY = "__gsheet_sa__"   # credstore 에 서비스계정 JSON 본문을 담는 키


class GSheetError(Exception):
    """구글 시트 API 사용 중 사용자에게 보여줄 명확한 사유가 있는 오류."""


def _require_libs():
    """google API 라이브러리 지연 임포트 — 미설치 시 설치 안내(조용한 실패 금지)."""
    try:
        from google.oauth2 import service_account          # noqa: F401
        from googleapiclient.discovery import build        # noqa: F401
        from googleapiclient.errors import HttpError       # noqa: F401
    except ImportError as exc:
        raise GSheetError(
            "구글 시트 라이브러리가 없습니다. 다음을 설치하세요: "
            "pip install google-api-python-client google-auth") from exc
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    return service_account, build, HttpError


def load_sa_info(store: CredStore | None = None, path: str | Path | None = None) -> dict[str, Any] | None:
    """서비스계정 정보(dict)를 얻는다 — 파일 경로 우선, 없으면 credstore(`__gsheet_sa__`).

    반환 None = 아직 등록 안 됨(호출부가 안내). JSON 파싱 실패는 예외로 올린다(조용한 무시 금지).
    """
    raw: str | None = None
    if path:
        p = Path(path)
        if not p.exists():
            raise GSheetError(f"서비스계정 키 파일을 찾을 수 없습니다: {p}")
        raw = p.read_text(encoding="utf-8")
    else:
        raw = (store or CredStore()).get_password(CRED_KEY)
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GSheetError("서비스계정 키 JSON 형식이 올바르지 않습니다.") from exc
    if info.get("type") != "service_account" or "client_email" not in info:
        raise GSheetError("올바른 '서비스계정' JSON 키가 아닙니다(type=service_account 필요).")
    return info


def store_sa_json(raw_json: str, store: CredStore | None = None) -> str:
    """서비스계정 JSON **본문**을 credstore(DPAPI)에 저장하고 서비스계정 이메일을 반환.

    저장 전 유효성 검증(서비스계정 JSON 인지). 이 함수만이 등록 경로 — 평문 파일을 앱이 따로 남기지 않는다.
    """
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise GSheetError("붙여넣은 내용이 올바른 JSON 이 아닙니다.") from exc
    if info.get("type") != "service_account" or "client_email" not in info:
        raise GSheetError("올바른 '서비스계정' JSON 키가 아닙니다(type=service_account 필요).")
    (store or CredStore()).set_password(CRED_KEY, raw_json)
    return info["client_email"]


def service_account_email(store: CredStore | None = None) -> str | None:
    """등록된 서비스계정 이메일(대상 시트를 이 주소에 공유해야 함). 미등록이면 None."""
    info = load_sa_info(store)
    return info.get("client_email") if info else None


def _cell_strikethrough(cell: dict) -> bool:
    """Sheets API 셀(dict)에 취소선이 있으면 True — 셀 전체(effectiveFormat) 또는 일부(textFormatRuns)."""
    ef = (cell.get("effectiveFormat") or {}).get("textFormat") or {}
    if ef.get("strikethrough"):
        return True
    for run in cell.get("textFormatRuns") or []:
        if (run.get("format") or {}).get("strikethrough"):
            return True
    return False


class GSheetClient:
    """서비스계정으로 인증된 Sheets API v4 클라이언트(스프레드시트 1개 대상).

    사용: `GSheetClient(url_or_id, sa_info=...).read_values("계정목록")`.
    지연 인증 — 첫 API 호출 때 build. 인증/권한 오류는 GSheetError 로 변환.
    """

    def __init__(self, url_or_id: str, *, sa_info: dict | None = None,
                 store: CredStore | None = None, sa_path: str | Path | None = None):
        self.spreadsheet_id = sheet_id_from_url(url_or_id)
        self._sa_info = sa_info if sa_info is not None else load_sa_info(store, sa_path)
        if not self._sa_info:
            raise GSheetError("서비스계정 키가 등록되지 않았습니다(설정 탭에서 1회 등록 필요).")
        self._svc = None                 # googleapiclient sheets service (지연 생성)
        self._HttpError = None
        self._meta: dict | None = None   # 스프레드시트 메타(시트 목록) 캐시

    # ── 내부 ────────────────────────────────────────────────────
    def _sheets(self):
        if self._svc is None:
            service_account, build, HttpError = _require_libs()
            self._HttpError = HttpError
            try:
                creds = service_account.Credentials.from_service_account_info(
                    self._sa_info, scopes=SCOPES)
            except Exception as exc:
                raise GSheetError(f"서비스계정 인증 실패: {exc}") from exc
            # static_discovery=True → 번들된 디스커버리 문서 사용(런타임 네트워크·PyInstaller 안전).
            self._svc = build("sheets", "v4", credentials=creds,
                              cache_discovery=False, static_discovery=True)
        return self._svc.spreadsheets()

    def _wrap(self, exc: Exception) -> GSheetError:
        """google HttpError → 한국어 GSheetError. 상태코드별 명확한 사유."""
        HttpError = self._HttpError
        if HttpError is not None and isinstance(exc, HttpError):
            status = getattr(getattr(exc, "resp", None), "status", None)
            email = self._sa_info.get("client_email", "(서비스계정)")
            if status == 403:
                return GSheetError(
                    f"접근 권한이 없습니다(403). 대상 스프레드시트를 서비스계정 '{email}' 에 "
                    "'편집자'로 공유했는지, Sheets API 가 사용 설정됐는지 확인하세요.")
            if status == 404:
                return GSheetError(f"스프레드시트를 찾을 수 없습니다(404). ID/URL 확인: {self.spreadsheet_id}")
            if status == 429:
                return GSheetError("구글 API 쿼터 초과(429). 잠시 후 다시 시도하세요(요청을 batch로 묶어 호출 최소화).")
            return GSheetError(f"구글 시트 API 오류(status={status}): {exc}")
        return GSheetError(f"구글 시트 처리 중 오류: {exc}")

    # ── 메타/시트 ────────────────────────────────────────────────
    def meta(self, refresh: bool = False) -> dict:
        """스프레드시트 메타(제목·시트목록). 시트 gid/이름 조회용. 캐시."""
        if self._meta is None or refresh:
            try:
                self._meta = self._sheets().get(
                    spreadsheetId=self.spreadsheet_id,
                    fields="properties.title,sheets.properties(sheetId,title,index)").execute()
            except Exception as exc:
                raise self._wrap(exc)
        return self._meta

    def title(self) -> str:
        return self.meta().get("properties", {}).get("title", "")

    def sheet_titles(self) -> list[str]:
        return [s["properties"]["title"] for s in self.meta().get("sheets", [])]

    def sheet_id(self, title: str) -> int | None:
        """시트명 → gid(정수). 없으면 None."""
        for s in self.meta().get("sheets", []):
            if s["properties"]["title"] == title:
                return s["properties"]["sheetId"]
        return None

    def ensure_sheet(self, title: str) -> int:
        """시트가 없으면 만들고 gid 반환. 있으면 기존 gid."""
        gid = self.sheet_id(title)
        if gid is not None:
            return gid
        try:
            resp = self._sheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": title}}}]}).execute()
        except Exception as exc:
            raise self._wrap(exc)
        self._meta = None   # 캐시 무효화(새 시트 반영)
        return resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    def ensure_sheets(self, titles: list[str]) -> dict[str, int]:
        """여러 시트를 **한 번의 batchUpdate**로 생성(없는 것만)하고 {제목: gid} 반환.

        대량 최초 생성(사업자 수십 개)에서 addSheet 를 연달아 보내면 쿼터(429)에 걸리므로 묶는다.
        생성 후 메타를 한 번만 새로 읽어 gid 를 채운다. 이미 있는 시트는 기존 gid.
        """
        existing = {t: self.sheet_id(t) for t in titles}   # 첫 조회에서 meta() 캐시
        missing = [t for t in titles if existing[t] is None]
        if missing:
            try:
                self._sheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": t}}} for t in missing]}
                ).execute()
            except Exception as exc:
                raise self._wrap(exc)
            self._meta = None
            for t in missing:
                existing[t] = self.sheet_id(t)             # 새 메타 1회 재조회 후 gid 채움
        return existing

    # ── 값 읽기/쓰기 ─────────────────────────────────────────────
    def read_values(self, sheet: str, cell_range: str | None = None) -> list[list[Any]]:
        """시트(또는 'Sheet!A1:D')의 값 격자 반환. 빈 뒤쪽 셀은 잘려 행 길이가 다를 수 있다.

        UNFORMATTED_VALUE + 직렬 날짜 문자열 회피를 위해 표시값(FORMATTED_VALUE) 기준으로 읽는다
        (관리대장 파싱은 사람이 보는 문자열 기준이 안전 — 마케팅 날짜 등).
        """
        rng = f"'{sheet}'" if cell_range is None else (
            cell_range if "!" in cell_range else f"'{sheet}'!{cell_range}")
        try:
            resp = self._sheets().values().get(
                spreadsheetId=self.spreadsheet_id, range=rng,
                valueRenderOption="FORMATTED_VALUE",
                dateTimeRenderOption="FORMATTED_STRING").execute()
        except Exception as exc:
            raise self._wrap(exc)
        return resp.get("values", [])

    def write_values(self, sheet: str, rows: list[list[Any]], start: str = "A1") -> None:
        """rows 를 start(예 'A1')부터 덮어쓴다(USER_ENTERED — 수식/하이퍼링크 반영)."""
        rng = f"'{sheet}'!{start}"
        try:
            self._sheets().values().update(
                spreadsheetId=self.spreadsheet_id, range=rng,
                valueInputOption="USER_ENTERED", body={"values": rows}).execute()
        except Exception as exc:
            raise self._wrap(exc)

    def clear_values(self, sheet: str, cell_range: str | None = None) -> None:
        """시트(또는 범위)의 값 지우기(서식은 유지)."""
        rng = f"'{sheet}'" if cell_range is None else (
            cell_range if "!" in cell_range else f"'{sheet}'!{cell_range}")
        try:
            self._sheets().values().clear(spreadsheetId=self.spreadsheet_id, range=rng).execute()
        except Exception as exc:
            raise self._wrap(exc)

    def read_grid(self, sheet: str, *, notes: bool = False) -> tuple[list[list[str]], list[list[str | None]]]:
        """시트의 (표시값 격자, 메모 격자)를 한 번에 읽는다.

        메모(note)는 계정목록 행의 **안정 키**(vid 앵커) 저장·매칭에 쓴다(사람에겐 거의 안 보이는 마커).
        notes=False면 메모 격자는 빈 리스트들. 시트가 비어 있으면 ([], []).
        """
        fields = "sheets.data.rowData.values(formattedValue" + (",note" if notes else "") + ")"
        try:
            resp = self._sheets().get(
                spreadsheetId=self.spreadsheet_id, ranges=[f"'{sheet}'"],
                includeGridData=True, fields=fields).execute()
        except Exception as exc:
            raise self._wrap(exc)
        data = resp.get("sheets", [{}])[0].get("data", [{}])
        row_data = (data[0] if data else {}).get("rowData", [])
        values: list[list[str]] = []
        note_grid: list[list[str | None]] = []
        for row in row_data:
            cells = row.get("values", [])
            values.append([c.get("formattedValue", "") for c in cells])
            note_grid.append([c.get("note") for c in cells] if notes else [])
        return values, note_grid

    def read_grid_struck(self, sheet: str) -> tuple[list[list[str]], list[list[bool]]]:
        """시트의 (표시값 격자, 취소선 격자)를 한 번에 읽는다 — 관리대장 해지/판매중지 감지용.

        취소선(strikethrough)은 Sheets API로 **읽을 수 있다**(effectiveFormat.textFormat.strikethrough =
        셀 전체 취소선, textFormatRuns = 셀 텍스트 일부 취소선). 한 셀이라도 취소선 신호가 있으면 True.
        표시값 격자는 read_grid 와 동일(전 컬럼 formattedValue → 비밀번호 컬럼도 포함해 파싱 호환).
        두 격자는 같은 rowData 에서 나오므로 [행][열] 인덱스가 서로 정렬된다. 빈 시트면 ([], []).
        """
        fields = ("sheets.data.rowData.values(formattedValue,"
                  "effectiveFormat.textFormat.strikethrough,textFormatRuns.format.strikethrough)")
        try:
            resp = self._sheets().get(
                spreadsheetId=self.spreadsheet_id, ranges=[f"'{sheet}'"],
                includeGridData=True, fields=fields).execute()
        except Exception as exc:
            raise self._wrap(exc)
        data = resp.get("sheets", [{}])[0].get("data", [{}])
        row_data = (data[0] if data else {}).get("rowData", [])
        values: list[list[str]] = []
        strike_grid: list[list[bool]] = []
        for row in row_data:
            cells = row.get("values", [])
            values.append([c.get("formattedValue", "") for c in cells])
            strike_grid.append([_cell_strikethrough(c) for c in cells])
        return values, strike_grid

    def batch_update(self, requests: list[dict]) -> dict:
        """서식·구조 변경 요청 묶음(병합·색·테두리·틀고정·하이퍼링크 등)을 한 번에 적용.

        Phase 3(서식 재현)의 기반 — 호출 횟수를 줄여 쿼터(429)를 아낀다. 빈 리스트면 무시.
        """
        if not requests:
            return {}
        try:
            return self._sheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id, body={"requests": requests}).execute()
        except Exception as exc:
            raise self._wrap(exc)


def check_access(url_or_id: str, *, store: CredStore | None = None,
                 sa_path: str | Path | None = None) -> tuple[str, list[str]]:
    """등록 검증용 — 스프레드시트를 열어 (제목, 시트목록) 반환. 실패 시 GSheetError.

    설정 탭에서 링크 등록 직후 '연결 확인' 버튼이 호출해 권한/공유 상태를 즉시 알려주기 위한 것.
    """
    info = load_sa_info(store, sa_path)
    if not info:
        raise GSheetError("서비스계정 키가 등록되지 않았습니다(먼저 서비스계정 키를 등록하세요).")
    client = GSheetClient(url_or_id, sa_info=info)
    return client.title(), client.sheet_titles()
