"""구글 시트 URL/ID 파싱 — `sheet_id_from_url` 만 남음.

예전엔 공개(링크 공유) 시트를 export 엔드포인트로 xlsx 내려받는 `download_xlsx` 가 있었으나, 결과·대장 시트는
서비스계정 공유(비공개)라 401 — 백업(2026-10-02)·마스터 복원(E2, 2026-10-10) 모두 서비스계정(Sheets API) 경로로
옮기며 호출처가 없어져 삭제. 시트 읽기·쓰기는 `gsheet_api.GSheetClient`.
"""
from __future__ import annotations

import re

_ID_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


_SCHEME_WORDS = {"https", "http", "ftp"}   # 중복 붙여넣기 시 `/d/` 뒤에 잘못 잡히는 URL 스킴


def sheet_id_from_url(url: str) -> str:
    """구글 시트 URL(또는 순수 ID)에서 스프레드시트 ID 추출.

    ⚠ 중복 붙여넣기 방어(2026-10-03): 링크 칸에 URL이 두 번 겹쳐 들어가면(예 `…/d/https://…/d/<ID>/edit`)
    옛 코드는 첫 `/d/` 뒤의 **'https'** 를 ID로 잡아 API 404("ID/URL 확인: https")를 냈다(실측: 재고현황·원장).
    → `finditer` 로 모든 `/d/<id>` 후보를 뽑되 **뒤에 `://` 가 오는(=중첩 URL 스킴) 후보와 스킴 단어는 제외**,
    남은 유효 후보의 **마지막(=실제 ID)** 을 쓴다. 길이로 거르지 않으므로 짧은 테스트 ID도 지킨다. 유효 후보가
    전혀 없으면(중복/깨진 링크) **명확한 사유로 예외**(조용히 넘기지 않음·사용자 안내).
    """
    s = (url or "").strip()
    cands = [m.group(1) for m in _ID_RE.finditer(s)
             if s[m.end():m.end() + 3] != "://" and m.group(1).lower() not in _SCHEME_WORDS]
    if cands:
        return cands[-1]                             # 중복 붙여넣기면 마지막(실제) ID
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):       # 순수 ID 직접 입력도 허용
        return s
    if _ID_RE.search(s):                             # /d/ 는 있으나 유효 ID 없음 = 중복/깨진 링크
        raise ValueError(
            "구글 시트 링크가 올바르지 않습니다 - URL이 중복 입력된 것 같습니다. "
            "링크 칸을 비우고 주소(또는 ID)를 한 번만 넣어 주세요.")
    raise ValueError("구글 시트 URL/ID 를 인식하지 못했습니다.")


def sheet_link(doc_id: str, gid: int, row: int = 1) -> str:
    """같은 구글 시트 파일 안의 탭(gid)·행으로 가는 **전체 주소** 링크(구글 '시트 링크 복사' 형식 + 범위).

    상대 링크 `#gid=…` 는 PC 브라우저에선 같은 파일 안 이동이지만 **모바일 시트 앱에선 열리지 않음**(소유자
    2026-10-23 실측: 계정목록 상품명·'계정목록으로 이동' 클릭 무반응). 파일 ID 가 없으면 만들 수 없어 예외."""
    if not doc_id:
        raise ValueError("시트 링크를 만들 파일 ID 가 없음 — 상대 링크(#gid)는 모바일에서 안 열려 쓰지 않음")
    return f"https://docs.google.com/spreadsheets/d/{doc_id}/edit?gid={gid}#gid={gid}&range=A{row}"

