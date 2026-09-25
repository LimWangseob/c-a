"""구글 시트 통합(Phase 1·2·3a·3c) 오프라인 회귀 검증 — 네트워크·구글 인증 없이 실제 로직 실행.

검증 범위(가짜 아님, 실제 함수 호출):
  1) 관리대장 rows 파싱(`parse_input_rows`) + **상태 컬럼**으로 삭제/판매중지 감지 + 비번 rows 추출.
  2) PC 엑셀 파싱(`parse_input_list`) 회귀 — 취소선 + 상태 컬럼 동시 감지.
  3) `계정목록` 동기화 계획(`plan_sync`) — 그룹 내 신규 삽입·새 계정 맨아래·삭제=상태만·마케팅열 값 미기록.
  4) 마케팅 역방향 머지(`read_marketing`/`apply_marketing`) — 직원 입력 우선, 미입력 스킵, 시트 없으면 빈 dict.

라이브(서비스계정+실제 시트) 검증은 사무실에서만. 실행: python tools/verify_gsheet_offline.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import openpyxl  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

from coupang_analytics import config, gsheet_index as gi, gsheet_stats  # noqa: E402
from coupang_analytics.gsheet_index import DATA_START0, ExistingRow, IndexRow  # noqa: E402
from coupang_analytics.input_list import (Account, Product,  # noqa: E402
                                          parse_input_list, parse_input_rows, parse_password_rows)
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

_HEAD = ["대표자", "사업자", "계정ID", "상품명(클릭 이동)",
         "체험단 시작일", "체험단 종료일", "모니터링 종료일", "상태"]   # 항목④(2026-09-25): 계정ID를 상품명 왼쪽으로
_HEAD_OLD7 = ["사업자", "상품명(클릭 이동)", "계정ID",
              "체험단 시작일", "체험단 종료일", "모니터링 종료일", "상태"]   # 마이그레이션 대상 옛 7열(상품·계정ID 순)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def t1_ledger_rows() -> None:
    print("[1] 관리대장 rows 파싱 + 상태 컬럼 감지")
    rows = [
        ["old", "pw", "대표A", "사업A", "acc1", "상품X"],                       # 잔여 예시행(무시)
        ["대표자명", "비밀번호", "대표자명", "사업자명", "계정아이디", "상품명", "상태",
         "마케팅시작일", "마케팅종료일", "모니터링종료일"],
        ["홍길동", "pass1", "홍길동", "가게1", "id_a", "텀블러", "정상", "2026-09-01", "2026-09-30", "2026-10-31"],
        ["", "", "", "", "", "보온병", "판매중지"],                              # 상태=판매중지 → 상품 제외
        ["김철수", "pass2", "김철수", "가게2", "id_b", "우산", "판매중"],          # '판매중'=유지
        ["이영희", "sec9", "이영희", "가게3", "id_c", "장갑", "삭제"],            # 계정행 상태=삭제 → 계정 제외
    ]
    il = parse_input_rows(rows)
    assert [a.account_id for a in il.accounts] == ["id_a", "id_b"], [a.account_id for a in il.accounts]
    # 줄이 존재하는 계정ID는 모두 ledger_account_ids(삭제/판매중지 상태여도 '줄은 있음' → 완전삭제 대상 아님)
    assert il.ledger_account_ids >= {"id_a", "id_b", "id_c"}, il.ledger_account_ids
    assert il.accounts[0].products[0].mkt_mon == "2026-10-31"
    assert any("보온병" in s for s in il.struck) and any("id_c" in s for s in il.struck)
    pw = parse_password_rows(rows)
    assert pw["id_a"] == "pass1" and pw["id_b"] == "pass2"
    _ok("계정 2개(id_c 삭제·보온병 판매중지 제외), '판매중' 유지, 비번 추출")


def t1b_ledger_strike() -> None:
    print("[1b] 관리대장 취소선(Sheets API strike_grid) 감지 — 상태 컬럼 없이도 제외")
    from coupang_analytics.gsheet_api import _cell_strikethrough
    # 셀 dict 파싱: 셀 전체 취소선 / 부분(run) 취소선 / 없음
    assert _cell_strikethrough({"effectiveFormat": {"textFormat": {"strikethrough": True}}}) is True
    assert _cell_strikethrough({"textFormatRuns": [{"format": {"strikethrough": True}}]}) is True
    assert _cell_strikethrough({"formattedValue": "정상"}) is False
    # 상태 컬럼이 아예 없는 대장 — 취소선만으로 제외 판정
    rows = [
        ["대표자명", "사업자명", "계정아이디", "상품명"],
        ["홍길동", "가게1", "id_a", "텀블러"],
        ["", "", "", "보온병"],                 # 상품명 취소선 → 상품 제외
        ["이영희", "가게3", "id_c", "장갑"],     # 계정ID 취소선 → 계정 제외
    ]
    W = len(rows[0])
    strike = [[False] * W for _ in rows]
    strike[2][3] = True                          # '보온병' 상품명 칸(col 3) 취소선
    strike[3][2] = True                          # 'id_c' 계정ID 칸(col 2) 취소선
    il = parse_input_rows(rows, strike)
    assert [a.account_id for a in il.accounts] == ["id_a"], [a.account_id for a in il.accounts]
    assert any("보온병" in s for s in il.struck) and any("id_c" in s for s in il.struck)
    # strike_grid 미제공(None)이면 취소선 무시 → 전부 유지(하위호환)
    il2 = parse_input_rows(rows)
    assert [a.account_id for a in il2.accounts] == ["id_a", "id_c"]
    _ok("셀/부분 취소선 파싱 + 취소선-only 제외(상태 컬럼 없음) + None이면 하위호환")


def t1c_real_ledger_shape() -> None:
    print("[1c] 실제 셀독리스트 구조 재현 — 행1 잔여값·행2 헤더·식별열 세로병합(상속)·우측 컬럼·취소선·판매상태")
    # 실측 구조(토탈셀러_셀독 관리 대장): 좌측에 관리열들, 우측에 대표자명/사업자명/계정아이디/비밀번호/상품명/판매상태.
    # 계정 식별열(대표자명·사업자명·계정아이디·비밀번호)은 그 계정의 여러 상품 행에 걸쳐 **세로 병합** →
    # 다운로드 xlsx/Sheets API 모두 **상단 행에만 값**, 아래 행은 빈칸 → 파서의 '빈 계정칸=상속'이 그룹핑.
    H = ["구분", "담당자", "대표자명", "사업자명", "계정아이디", "비밀번호", "상품명", "판매상태"]
    rows = [
        ["0", "박명진", "totalseller@x", "", "id@stray", "pw@stray", "", ""],   # 행1 잔여 예시값(무시)
        H,                                                                       # 행2 헤더
        ["0", "박명진", "송창호", "웰빙곳간", "wellbing", "pw1", "볶은맥문동환", ""],   # 계정A 첫 상품(식별열 값)
        ["",  "",     "",     "",       "",         "",    "알부민맥스",   ""],   # 병합 상속(빈 계정칸)
        ["",  "",     "",     "",       "",         "",    "커큐민플러스", "판매중지"],  # 상태=판매중지 → 상품 제외
        ["",  "",     "",     "",       "",         "",    "퀘르세틴",     ""],   # 취소선 → 상품 제외
        ["0", "박명진", "이재필", "커스텀존", "unipang",  "pw2", "불멍화로",     ""],   # 계정B 첫 상품
        ["",  "",     "",     "",       "",         "",    "NMN정",       ""],   # 병합 상속
    ]
    W = len(H)
    strike = [[False] * W for _ in rows]
    strike[5][6] = True                              # '퀘르세틴' 상품명 취소선(col 6)
    il = parse_input_rows(rows, strike)
    got = {a.account_id: [p.name for p in a.products] for a in il.accounts}
    assert list(got.keys()) == ["wellbing", "unipang"], list(got.keys())
    assert got["wellbing"] == ["볶은맥문동환", "알부민맥스"], got["wellbing"]   # 판매중지·취소선 2개 제외
    assert got["unipang"] == ["불멍화로", "NMN정"], got["unipang"]
    assert il.accounts[0].business_name == "웰빙곳간" and il.accounts[0].representative == "송창호"
    assert any("커큐민플러스" in s for s in il.struck) and any("퀘르세틴" in s for s in il.struck)
    pw = parse_password_rows(rows)
    assert pw.get("wellbing") == "pw1" and pw.get("unipang") == "pw2", pw
    _ok("행2 헤더·세로병합 상속·취소선+판매상태 동시제외·계정식별·비번(우측 컬럼)까지 실구조 재현 통과")


def t2_file_regression() -> None:
    print("[2] PC 엑셀 파싱 회귀(취소선 + 상태)")
    p = os.path.join(tempfile.gettempdir(), "verify_ledger.xlsx")
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["대표자명", "사업자명", "계정아이디", "비밀번호", "상품명", "상태"])
    ws.append(["홍길동", "가게1", "id1", "pw1", "텀블러", "정상"])
    ws.append(["", "", "", "", "해지상품", "판매중지"])            # 상태 제외
    ws.append(["김철수", "가게2", "id2", "pw2", "우산", "정상"])
    ws.append(["이영", "가게3", "id3", "pw3", "장갑", "정상"])     # 계정ID 취소선 → 계정 제외
    ws.cell(5, 3).font = Font(strike=True)
    wb.save(p)
    il = parse_input_list(p)
    os.remove(p)
    assert [a.account_id for a in il.accounts] == ["id1", "id2"], [a.account_id for a in il.accounts]
    assert any("해지상품" in s for s in il.struck) and any("id3" in s for s in il.struck)
    _ok("취소선(id3)·상태(해지상품) 동시 감지, 계정 2개")


def _R(acct, prod, key, status="예정", rep=None):
    return IndexRow(business=f"biz_{acct}", product=prod, account_id=acct, status=status, key=key,
                    representative=(rep if rep is not None else f"대표_{acct}"))


def _touched_data_mkt(req) -> set:
    uc = req.get("updateCells")
    if not uc or uc["start"].get("rowIndex", 0) < DATA_START0:
        return set()
    start = uc["start"]["columnIndex"]; ncol = len(uc["rows"][0]["values"])
    mkt = (gi.COL_MKT_START, gi.COL_MKT_END, gi.COL_MKT_MON)   # 마케팅(체험단) 직원 입력 열
    return {c for c in range(start, start + ncol) if c in mkt}


def t3_index_sync() -> None:
    print("[3] 계정목록 동기화 계획(plan_sync) + 마케팅열 값 미기록")
    existing = [ExistingRow(2, "A", "kA1"), ExistingRow(3, "A", "kA2"), ExistingRow(4, "B", "kB3")]
    desired = [_R("A", "상품1", "kA1", "체험단중"), _R("A", "상품4", "kA4"),
               _R("B", "상품3", "kB3"), _R("C", "상품5", "kC5")]
    plan = gi.plan_sync(existing, desired)
    kinds = {}
    for g, r in plan.updates: kinds[g] = ("upd", r.key)
    for g, r in plan.inserts: kinds[g] = ("new", r.key)
    for g, _acct in plan.discontinue: kinds[g] = ("disc", None)
    assert kinds[DATA_START0 + 0] == ("upd", "kA1")
    assert kinds[DATA_START0 + 1] == ("disc", None)          # kA2 사라짐 → 판매중지(행 보존)
    assert kinds[DATA_START0 + 2] == ("new", "kA4")          # A 그룹 끝 삽입
    assert kinds[DATA_START0 + 3] == ("upd", "kB3")
    assert kinds[DATA_START0 + 4] == ("new", "kC5")          # 새 계정 맨 아래
    band_by_acct = {r.account_id: r.band for r in desired}
    rep_by_acct = {r.account_id: r.representative for r in desired}
    reqs = gi._build_requests_for_plan(99, plan, band_by_acct, rep_by_acct)
    ins = [r["insertDimension"]["range"]["startIndex"] for r in reqs if "insertDimension" in r]
    assert ins == sorted(ins) == [DATA_START0 + 2, DATA_START0 + 4], ins
    assert not [c for r in reqs for c in _touched_data_mkt(r)], "마케팅열 값 기록 침범"
    # 판매중지 행(kA2, DATA_START0+1)도 계정 밴드색으로 행 전체(A~H) 배경만 칠함(값 보존)
    disc_row = DATA_START0 + 1
    fullrow_bg = [r for r in reqs if "repeatCell" in r
                  and r["repeatCell"]["range"].get("startRowIndex") == disc_row
                  and r["repeatCell"]["range"].get("startColumnIndex", 0) == 0
                  and r["repeatCell"]["range"].get("endColumnIndex") == gi.N_COLS]
    assert len(fullrow_bg) == 1, "판매중지 행 전체 밴드색 누락"
    assert fullrow_bg[0]["repeatCell"]["fields"] == "userEnteredFormat.backgroundColor"  # 값 미기록
    # 판매중지 행 A(대표자) 셀은 그 계정 대표자로 채워짐(공란 방지) — 값+밴드색만
    rep_cells = [r for r in reqs if "updateCells" in r
                 and r["updateCells"]["start"].get("rowIndex") == disc_row
                 and r["updateCells"]["start"].get("columnIndex") == gi.COL_REP]
    assert len(rep_cells) == 1, "판매중지 행 대표자 채움 누락"
    assert rep_cells[0]["updateCells"]["rows"][0]["values"][0]["userEnteredValue"]["stringValue"] == "대표_A"
    _ok("그룹내 삽입·새계정 맨아래·판매중지=상태+계정밴드색+대표자채움(공란방지)·마케팅 E~G 값 미기록")


class _FakeClient:
    def __init__(self, values, titles=None, row_count=1000, col_count=26):
        self._v = values; self.batches = []
        self._row_count = row_count   # 그리드 행수(확장 판단용) — 기본 넉넉히
        self._col_count = col_count   # 그리드 열수(확장 판단용) — 기본 넉넉히(신규 시트 26열)
        self._titles = titles if titles is not None else (["계정목록"] if values else [])
        self._ids = {t: 100 + i for i, t in enumerate(self._titles)}
    def sheet_titles(self): return list(self._titles)
    def sheet_id(self, title): return self._ids.get(title)
    def grid_row_count(self, title): return self._row_count
    def grid_col_count(self, title): return self._col_count
    def ensure_sheet(self, name): return self._ids.get(name, 7)
    def read_grid(self, sheet, notes=False): return self._v, [[None] * len(r) for r in self._v]
    def batch_update(self, reqs):
        self.batches.append(reqs)
        for r in reqs:   # 마이그레이션 재현: A열(0) 컬럼 삽입 → 모든 행 오른쪽으로 밀림(값 유지)
            ins = r.get("insertDimension")
            if ins and ins["range"].get("dimension") == "COLUMNS" and ins["range"].get("startIndex") == 0:
                self._v = [[""] + list(row) for row in self._v]
            mv = r.get("moveDimension")   # 항목④ 열 이동 재현: source 열을 destinationIndex 로(값 유지)
            if mv and mv["source"].get("dimension") == "COLUMNS":
                s = mv["source"]["startIndex"]; dest = mv["destinationIndex"]
                new_v = []
                for row in self._v:
                    row = list(row)
                    if s < len(row):
                        col = row.pop(s)
                        row.insert(dest if dest < s else dest - 1, col)
                    new_v.append(row)
                self._v = new_v
        return {}


def t3b_full_and_incremental() -> None:
    print("[3b] sync_index 전체빌드 + 증분(FakeClient)")
    desired = [_R("A", "상품1", gi.marketing_key("A", "상품1"), "체험단중"),
               _R("A", "상품4", gi.marketing_key("A", "상품4")),
               _R("B", "상품3", gi.marketing_key("B", "상품3"))]
    fc = _FakeClient([])
    p = gi.sync_index(fc, desired)
    assert p.inserts and not p.updates and any("mergeCells" in r for r in fc.batches[0])
    assert not [c for r in fc.batches[0] for c in _touched_data_mkt(r)]
    # 구글 API 계약 방어(라이브에서 400으로 드러났던 버그 재발 방지):
    valid_merge = {"MERGE_ALL", "MERGE_ROWS", "MERGE_COLUMNS"}
    for r in fc.batches[0]:
        if "mergeCells" in r:
            assert r["mergeCells"]["mergeType"] in valid_merge, r["mergeCells"]["mergeType"]
        if "updateSheetProperties" in r:   # 제목 A1:G1 병합과 충돌하는 열 고정 금지(부분 병합 틀고정=400)
            gp = r["updateSheetProperties"]["properties"].get("gridProperties", {})
            assert gp.get("frozenColumnCount", 0) == 0, gp
    _ok("빈 시트 → 전체 생성(제목 병합=MERGE_ALL·열 고정 없음·마케팅 값 미기록)")

    existing_vals = [
        ["계정목록 · 상품 3개"], list(_HEAD),
        ["대표A", "biz_A", "A", "상품1", "2026-09-01", "2026-09-30", "", "체험단중"],
        ["대표A", "biz_A", "A", "상품2", "", "", "", "예정"],
        ["대표B", "biz_B", "B", "상품3", "", "", "", "예정"],
    ]
    fc2 = _FakeClient(existing_vals)
    p2 = gi.sync_index(fc2, desired)
    assert len(p2.inserts) == 1 and p2.inserts[0][1].product == "상품4"
    assert len(p2.discontinue) == 1                          # 상품2 사라짐
    _ok("기존 시트(8열) → 증분(상품4 신규 삽입, 상품2 판매중지)")

    # 옛 7열 시트 → 대표자 컬럼 자동 마이그레이션(A에 빈 열 삽입 후 증분)
    old_vals = [
        ["계정목록 · 상품 3개"], list(_HEAD_OLD7),
        ["biz_A", "상품1", "A", "2026-09-01", "2026-09-30", "", "체험단중"],
        ["biz_A", "상품2", "A", "", "", "", "예정"],
        ["biz_B", "상품3", "B", "", "", "", "예정"],
    ]
    fc3 = _FakeClient(old_vals)
    p3 = gi.sync_index(fc3, desired)
    inserted_col = any("insertDimension" in r and r["insertDimension"]["range"].get("dimension") == "COLUMNS"
                       for batch in fc3.batches for r in batch)
    assert inserted_col, "옛 7열 → 대표자 열 삽입(마이그레이션) 누락"
    assert len(p3.inserts) == 1 and p3.inserts[0][1].product == "상품4"
    assert len(p3.discontinue) == 1

    # 항목④: 옛 열순서(상품 C·계정ID D) 8열 시트 → moveDimension 으로 계정ID 를 C 로 물리 이전 후 정상 매칭
    old_order = [
        ["계정목록 · 상품 3개"],
        ["대표자", "사업자", "상품명(클릭 이동)", "계정ID", "체험단 시작일", "체험단 종료일", "모니터링 종료일", "상태"],
        ["대표A", "biz_A", "상품1", "A", "", "", "", "예정"],       # 옛 순서: C=상품·D=계정ID
        ["대표B", "biz_B", "상품3", "B", "", "", "", "예정"],
    ]
    fc4 = _FakeClient(old_order)
    p4 = gi.sync_index(fc4, desired)
    moved = any("moveDimension" in r and r["moveDimension"]["source"].get("dimension") == "COLUMNS"
                for batch in fc4.batches for r in batch)
    assert moved, "옛 열순서(상품 C·계정ID D) → 계정ID 를 C 로 moveDimension 마이그레이션 누락"
    assert len(p4.inserts) == 1 and p4.inserts[0][1].product == "상품4"   # 이전 후 상품1/3 매칭·상품4만 신규
    assert len(p4.discontinue) == 0
    _ok("항목④ 옛 열순서(상품C·계정ID D) → moveDimension 으로 계정ID를 C로 이전·매칭 정상")
    assert len(p3.inserts) == 1 and p3.inserts[0][1].product == "상품4"   # 삽입 후 위치 매칭 정상
    assert len(p3.discontinue) == 1
    _ok("옛 7열 시트 → 대표자 열 자동 삽입(마이그레이션) 후 증분 정상")


def t3d_grid_autogrow() -> None:
    print("[3d] 그리드 자동 확장 — 여유 없으면 삽입 전 appendDimension(라이브 400 방지), 있으면 안 함")
    desired = [_R("A", "상품1", gi.marketing_key("A", "상품1")),
               _R("A", "상품9", gi.marketing_key("A", "상품9")),        # 신규 → 삽입
               _R("B", "상품3", gi.marketing_key("B", "상품3"))]
    existing_vals = [
        ["계정목록 · 상품 2개"], list(_HEAD),
        ["대표A", "biz_A", "A", "상품1", "", "", "", "예정"],
        ["대표B", "biz_B", "B", "상품3", "", "", "", "예정"],
    ]
    # 그리드가 데이터로 꽉 참(rowCount=4=헤더2+데이터2) → 신규 삽입이 그리드 끝을 넘어 400 위험 → 확장 필요
    fc = _FakeClient(existing_vals, row_count=4)
    gi.sync_index(fc, desired)
    grow = [r for b in fc.batches for r in b if "appendDimension" in r]
    assert grow, "여유 없는 그리드인데 appendDimension(행 확장) 누락 — insertDimension 400 재발 위험"
    assert grow[0]["appendDimension"]["dimension"] == "ROWS" and grow[0]["appendDimension"]["length"] > 0
    _ok("여유 없는 그리드 → 삽입 전 행 자동 확장(appendDimension)")

    fc2 = _FakeClient(existing_vals, row_count=1000)          # 여유 충분 → 확장 불필요
    gi.sync_index(fc2, desired)
    grow2 = [r for b in fc2.batches for r in b if "appendDimension" in r]
    assert not grow2, "여유 충분한데 불필요한 그리드 확장(멱등성 위반)"
    _ok("여유 충분한 그리드 → 확장 안 함")

    # 열 확장: 옛 계정목록이 N_COLS(체험단효과 I열=9) 보다 좁으면 기록 전 COLUMNS 확장(라이브 400 방지)
    fc3 = _FakeClient(existing_vals, row_count=1000, col_count=8)
    gi.sync_index(fc3, desired)
    cgrow = [r for b in fc3.batches for r in b
             if r.get("appendDimension", {}).get("dimension") == "COLUMNS"]
    assert cgrow and cgrow[0]["appendDimension"]["length"] == gi.N_COLS - 8, "좁은 그리드 열 확장 누락(400 재발)"
    fc4 = _FakeClient(existing_vals, row_count=1000, col_count=gi.N_COLS)   # 이미 충분
    gi.sync_index(fc4, desired)
    assert not [r for b in fc4.batches for r in b
                if r.get("appendDimension", {}).get("dimension") == "COLUMNS"], "충분한 열인데 불필요 확장"
    _ok("좁은 열 그리드 → 체험단효과 I열 기록 전 열 자동 확장(넓으면 안 함)")


def t3e_delete_renamed() -> None:
    print("[3e] 일원화 옛 이름 정리(delete_renamed_accounts) — 같은 계정ID 공유해도 옛 이름 행만 삭제")
    vals = [
        ["계정목록 · 상품 3개"], list(_HEAD),
        ["이종훈", "이종훈", "oopean", "옛상품", "체험", "", "", "판매중지"],   # 옛 이름(삭제 대상)
        ["이종훈", "원더폴리", "oopean", "신상품", "체험", "", "", "예정"],     # 새 이름(계정ID·대표자 동일·보존)
        ["대표B", "가게B", "idB", "상품3", "", "", "", "예정"],
    ]
    fc = _FakeClient(vals, titles=["계정목록", "이종훈", "원더폴리", "가게B"])
    n = gi.delete_renamed_accounts(fc, [("이종훈", "oopean")])
    del_rows = [r for b in fc.batches for r in b
               if "deleteDimension" in r and r["deleteDimension"]["range"]["dimension"] == "ROWS"]
    del_sheets = [r for b in fc.batches for r in b if "deleteSheet" in r]
    assert len(del_rows) == 1, del_rows                                   # 이종훈 행 1개만(원더폴리 아님)
    assert del_rows[0]["deleteDimension"]["range"]["startIndex"] == 2     # 0-based 격자행(옛 이름 행)
    assert len(del_sheets) == 1 and del_sheets[0]["deleteSheet"]["sheetId"] == fc._ids["이종훈"]
    # 새 이름(원더폴리)·타 계정 통계 시트 미접촉
    assert not any(r for b in fc.batches for r in b if "deleteSheet" in r
                   and r["deleteSheet"]["sheetId"] in (fc._ids["원더폴리"], fc._ids["가게B"]))
    assert n == 2
    _ok("계정ID(oopean) 공유해도 사업자명(B)로 옛 이름 '이종훈' 행·통계 시트만 삭제·원더폴리 보존")


def t3c_delete_accounts() -> None:
    print("[3c] 삭제된 계정 완전 제거(delete_accounts) — 계정목록 행 + 통계 시트")
    vals = [
        ["계정목록 · 상품 3개"], list(_HEAD),
        ["대표A", "가게A", "idA", "상품1", "", "", "", "예정"],
        ["대표X", "가게X", "idX", "상품9", "", "", "", "예정"],     # 삭제 대상
        ["대표B", "가게B", "idB", "상품3", "", "", "", "예정"],
    ]
    fc = _FakeClient(vals, titles=["계정목록", "가게A", "가게X", "가게B"])
    n = gi.delete_accounts(fc, [("가게X", "idX")])
    # 계정목록 행 삭제 요청 + 통계 시트 삭제 요청
    del_rows = [r for b in fc.batches for r in b
               if "deleteDimension" in r and r["deleteDimension"]["range"]["dimension"] == "ROWS"]
    del_sheets = [r for b in fc.batches for r in b if "deleteSheet" in r]
    assert len(del_rows) == 1, del_rows                                   # idX 행 1개
    assert del_rows[0]["deleteDimension"]["range"]["startIndex"] == 3     # 0-based 격자행(가게X)
    assert len(del_sheets) == 1 and del_sheets[0]["deleteSheet"]["sheetId"] == fc._ids["가게X"]
    assert n == 2
    # 삭제 안 할 계정은 안 건드림
    assert not any(r for b in fc.batches for r in b if "deleteSheet" in r
                   and r["deleteSheet"]["sheetId"] in (fc._ids["가게A"], fc._ids["가게B"]))
    _ok("계정목록 idX 행 1개 + 통계 시트 '가게X' 삭제·타 계정 미접촉")


def t4_marketing_merge() -> None:
    print("[4] 마케팅 역방향 머지(read_marketing/apply_marketing)")
    values = [
        ["계정목록 · 상품 3개"], list(_HEAD),
        ["대표A", "가게A", "idA", "텀블러", "2026-09-01", "2026-09-30", "2026-10-31", "체험단중"],
        ["대표A", "가게A", "idA", "보온병", "", "", "", "예정"],        # 마케팅 없음 → 스킵
        ["대표B", "가게B", "idB", "우산", "2026-09-10", "", "", "예정"],
    ]
    fc = _FakeClient(values)
    m = gi.read_marketing(fc)
    assert gi.marketing_key("idA", "텀블러") in m and gi.marketing_key("idA", "보온병") not in m
    accts = [Account("idA", "대표A", "가게A", products=[Product("텀블러"), Product("보온병")]),
             Account("idB", "대표B", "가게B", products=[Product("우산")])]
    n = gi.apply_marketing(accts, m)
    assert n == 2
    assert accts[0].products[0].mkt_start == "2026-09-01" and accts[0].products[0].mkt_mon == "2026-10-31"
    assert accts[0].products[1].mkt_start == "" and accts[1].products[0].mkt_start == "2026-09-10"
    assert gi.read_marketing(_FakeClient([])) == {}          # 시트 없으면 빈 dict
    _ok("직원 입력 우선 반영(2개), 미입력 스킵, 시트 없으면 빈 dict")


def _sample_workbook() -> OutputWorkbook:
    """작은 실제 OutputWorkbook — 계정 1·상품 1(계약)·키워드 2·값 채움 후 서식 적용."""
    wb = OutputWorkbook.empty()
    wb.set_account_id("가게A", "idA")
    wb.set_representative("가게A", "홍길동")
    wb.ensure_product_block("가게A", "텀블러", config.KIND_CONTRACT, ["텀블러", "보온 텀블러"])
    wb.set_product_vids("가게A", "텀블러", ["111", "222"])
    wb.set_product_metric("가게A", "텀블러", config.CONTRACT_METRICS[0], "2026-09-12", 5)
    wb.set_keyword_rank("가게A", "텀블러", "텀블러", "2026-09-12", 3)
    wb.apply_style()
    return wb


def t5_stats_mirror() -> None:
    print("[5] 통계 시트 미러링(worksheet_to_requests) + 등록명 보존")
    wb = _sample_workbook()
    assert wb.registered_name("가게A", "텀블러") == "텀블러"
    assert wb.set_display_name("가게A", "텀블러", "스텐 텀블러 500ml")
    assert wb.registered_name("가게A", "스텐 텀블러 500ml") == "텀블러"   # 노출명 변경에도 등록명 보존

    ws = wb.wb["가게A"]
    reqs = gsheet_stats.worksheet_to_requests(ws, 42, index_gid=7)
    kinds = [next(iter(r)) for r in reqs]
    for need in ("unmergeCells", "updateSheetProperties", "updateCells", "mergeCells"):
        assert need in kinds, (need, kinds)
    gp = next(r for r in reqs if "updateSheetProperties" in r)["updateSheetProperties"]["properties"]["gridProperties"]
    assert gp["frozenRowCount"] == 1 and gp["frozenColumnCount"] == 7, gp   # freeze_panes 'H2'
    for r in reqs:                       # 병합 타입 유효값(라이브 400 방지) — 통계는 7열 전체 고정이라 병합 안 잘림
        if "mergeCells" in r:
            assert r["mergeCells"]["mergeType"] in {"MERGE_ALL", "MERGE_ROWS", "MERGE_COLUMNS"}
    flat = str(next(r for r in reqs if "updateCells" in r))
    assert "#gid=7&range=A1" in flat and "계정목록으로 이동" in flat        # 복귀 링크 문구 → 계정목록 gid
    _ok("전체교체 요청(병합해제·틀고정 H2·복귀 HYPERLINK) + 등록명 보존")


def t6_roster_from_workbook() -> None:
    print("[6] roster_from_workbook — 등록명 기반 안정키·노출명 표시·통계링크")
    wb = _sample_workbook()
    wb.set_display_name("가게A", "텀블러", "스텐 텀블러 500ml")
    roster = gi.roster_from_workbook(wb, {"가게A": 42})
    r0 = next(r for r in roster if r.product)
    assert r0.business == "가게A" and r0.account_id == "idA"
    assert r0.representative == "홍길동"                                  # A=대표자(관리대장)
    assert r0.product == "스텐 텀블러 500ml"                              # C=노출명(표시)
    assert r0.key == gi.marketing_key("idA", "텀블러")                    # 안정키=계정ID+등록명(노출명 아님)
    assert r0.link_gid == 42 and r0.link_row is not None
    # 상품 링크 수식 = 사업자 통계시트(#gid)+블록 헤더행. ⚠ '계정목록!A1' 자가참조 아님(어제 gsheet 버그).
    _cell = gi._product_cell(r0)
    _fml = _cell["userEnteredValue"]["formulaValue"]
    assert _fml == f'=HYPERLINK("#gid=42&range=A{r0.link_row}","{r0.product}")', _fml
    assert "!A1" not in _fml and "계정목록" not in _fml, _fml   # 자기 탭 A1 자가참조(버그) 아님
    # 사업자별 바탕색 밴딩: 인접 사업자는 다른 색 + 팔레트 길이마다 순환(행 전체 A~G 동일색)
    assert gi._band_fill(0) != gi._band_fill(1) != gi._band_fill(2)          # 인접 밴드는 서로 다름
    assert gi._band_fill(0) == gi._band_fill(len(gi._BAND_FILLS))            # 팔레트 길이마다 순환
    reqs = gi._auto_cells_request(1, DATA_START0, IndexRow("사업B", "상품", "idB", "예정", "k", band=1))
    bg_cols = set()
    for rq in reqs:
        uc = rq["updateCells"]; start = uc["start"]["columnIndex"]
        for j, cell in enumerate(uc["rows"][0]["values"]):
            if cell.get("userEnteredFormat", {}).get("backgroundColor"):
                bg_cols.add(start + j)
    assert bg_cols == {0, 1, 2, 3, 7, 8}, bg_cols    # A·B·C·D·H + I(체험단효과) 담당(E~G 미접촉)
    # I열 체험단효과 색: 개선=연초록·악화=연적색·그외=밴드색(값도 기록)
    def _promo_cell(verdict):
        rq = gi._auto_cells_request(1, DATA_START0,
                                    IndexRow("s", "p", "id", "예정", "k", band=2,
                                             promo_effect="판매 +38% · 순위 32→18 ↑", promo_verdict=verdict))
        pc = next(r for r in rq if r["updateCells"]["start"]["columnIndex"] == gi.COL_PROMO)
        v = pc["updateCells"]["rows"][0]["values"][0]
        return v["userEnteredValue"]["stringValue"], v["userEnteredFormat"]["backgroundColor"]
    txt, up_bg = _promo_cell("up")
    assert txt == "판매 +38% · 순위 32→18 ↑" and up_bg == gi._PROMO_UP_FILL
    assert _promo_cell("down")[1] == gi._PROMO_DOWN_FILL
    assert _promo_cell("")[1] == gi._band_fill(2)    # 무판정 → 사업자 밴드색
    # E~G는 _mkt_fill_request가 같은 밴드색으로(행 전체 동일 바탕색) + 값은 안 건드림(repeatCell)
    mreq = gi._mkt_fill_request(1, DATA_START0, 1)
    rc = mreq["repeatCell"]
    assert rc["cell"]["userEnteredFormat"]["backgroundColor"] == gi._band_fill(1)
    assert "userEnteredValue" not in str(rc["fields"])   # 배경/정렬만 — 값 미기록(직원 입력 보존)
    _ok("노출명·안정키·통계링크 + 행 전체 사업자 밴드색(A~G, D~F는 값 보존한 채 배경만)")


def t6c_content_col_widths() -> None:
    print("[6c] 셀 폭 내용길이 자동맞춤(_col_width_requests) — 긴 상품명=넓게(상한)·짧은 계정ID=좁게·마케팅 고정 (항목④)")
    short = IndexRow(business="가", product="짧", account_id="id1", status="예정", key="k")
    long_prod = "아주아주기이이인상품명" * 4                      # 매우 긴 노출명
    longr = IndexRow(business="사업자명아주긴것", product=long_prod, account_id="acct_아주_긴_계정ID_1234567890",
                     status="예정", key="k", representative="대표자아주긴이름",
                     promo_effect="판매 +38% · 순위 32→18 ↑")
    reqs = gi._col_width_requests(7, [short, longr])
    px = {r["updateDimensionProperties"]["range"]["startIndex"]:
          r["updateDimensionProperties"]["properties"]["pixelSize"] for r in reqs}
    # 상품명(D=COL_PRODUCT)=긴 내용 → 최대 클램프, 계정ID(C=COL_ACCOUNT)=상한 클램프(긴 것도 max 이하)
    assert px[gi.COL_PRODUCT] == gi._COL_W_MAX[gi.COL_PRODUCT], f"긴 상품명 폭 상한 아님: {px[gi.COL_PRODUCT]}"
    assert px[gi.COL_ACCOUNT] <= gi._COL_W_MAX[gi.COL_ACCOUNT], "계정ID 폭 상한 초과"
    assert px[gi.COL_PRODUCT] > px[gi.COL_ACCOUNT], "상품명이 계정ID보다 넓어야(내용 기반)"
    # 마케팅 E~G=고정
    assert px[gi.COL_MKT_START] == gi._COL_W_MKT[gi.COL_MKT_START], "마케팅 열은 고정 폭"
    # 짧은 내용만이면 최소 클램프
    reqs2 = gi._col_width_requests(7, [short])
    px2 = {r["updateDimensionProperties"]["range"]["startIndex"]:
           r["updateDimensionProperties"]["properties"]["pixelSize"] for r in reqs2}
    assert px2[gi.COL_ACCOUNT] >= gi._COL_W_MIN[gi.COL_ACCOUNT], "짧은 내용 최소 폭 미달"
    _ok("긴 상품명=상한·계정ID 좁게·상품명>계정ID·마케팅 고정·짧은 내용=최소 클램프")


def t6b_multi_account_roster() -> None:
    print("[6b] roster 다계정ID — 상품별 계정ID·사업자명 기준 밴드(한 사업자=한 밴드, 항목5)")
    BIZ = "로움컨설팅"
    wb = OutputWorkbook.empty()
    wb.set_representative(BIZ, "김대표")
    for aid, prod in (("loum1", "상품1"), ("loum2", "상품2")):
        wb.set_account_id(BIZ, aid)
        wb.ensure_product_block(BIZ, prod, config.KIND_CONTRACT, ["kw"], registered=prod)
        wb.set_product_vids(BIZ, prod, ["v_" + aid])
        wb.set_product_account_id(BIZ, prod, aid)
        wb.set_keyword_rank(BIZ, prod, "kw", "2026-09-25", 3)
    # 다른 사업자 하나 더(밴드가 사업자별로 달라지는지)
    wb.set_account_id("다른상사", "other1")
    wb.ensure_product_block("다른상사", "상품X", config.KIND_CONTRACT, ["kw"], registered="상품X")
    wb.set_product_account_id("다른상사", "상품X", "other1")
    wb.set_keyword_rank("다른상사", "상품X", "kw", "2026-09-25", 1)
    wb.apply_style()
    roster = gi.roster_from_workbook(wb, {})
    loum = [r for r in roster if r.business == BIZ and r.product]
    other = [r for r in roster if r.business == "다른상사" and r.product]
    # ① 상품별 계정ID = 각자 소속(덮어쓰기 아님)
    by_prod = {r.product: r.account_id for r in loum}
    assert by_prod == {"상품1": "loum1", "상품2": "loum2"}, by_prod
    # ② 같은 사업자 다계정ID = 한 밴드(색), 상품 2줄 동일 밴드
    loum_bands = {r.band for r in loum}
    assert len(loum_bands) == 1, f"다계정ID가 한 밴드로 안 묶임: {loum_bands}"
    # ③ 다른 사업자는 다른 밴드
    assert other[0].band != loum[0].band, "다른 사업자인데 같은 밴드"
    # ④ 안정키 = 상품별 계정ID + 등록명(상품마다 구분)
    assert by_prod["상품1"] != by_prod["상품2"]
    assert loum[0].key == gi.marketing_key("loum1", "상품1"), loum[0].key
    _ok("상품별 계정ID·같은 사업자 다계정ID=한 밴드·다른 사업자=다른 밴드·안정키 계정ID별 구분")


def _grow(c="", g=""):
    """통계 시트 한 행(0-based 격자) — C(3열=index2)=이름, G(7열=index6)=지표."""
    r = [""] * 7
    r[2] = c
    r[6] = g
    return r


def _growA(a="", c="", g=""):
    """레이아웃 v4 격자 행 — A(1열=index0)=키워드명/소헤더, C(index2)=상품명, G(index6)=지표."""
    r = [""] * 7
    r[0] = a
    r[2] = c
    r[6] = g
    return r


class _StatsFake:
    """사업자 시트명→격자 매핑을 돌려주는 최소 클라이언트(merge_staff_keywords 용)."""
    def __init__(self, grids): self._g = grids
    def sheet_titles(self): return list(self._g)
    def read_grid(self, sheet, notes=False):
        v = self._g.get(sheet, [])
        return v, [[None] * len(r) for r in v]


def t7_staff_keywords_merge() -> None:
    print("[7] 직원 입력 키워드 역머지(merge_staff_keywords)")
    wb = _sample_workbook()   # 가게A/텀블러, 키워드 [텀블러, 보온 텀블러]
    assert set(wb.product_keywords("가게A", "텀블러")) == {"텀블러", "보온 텀블러"}
    grid = {"가게A": [
        _grow(),                                          # 제목행
        _grow("텀블러", "날짜"),                           # 상품 헤더
        _grow("", config.CONTRACT_METRICS[0]), _grow("", config.CONTRACT_METRICS[1]),  # 지표행(C 병합=빈칸)
        _grow("키워드", "비고"),                           # 키워드 소헤더
        _grow("텀블러", "노출 순위"), _grow("보온 텀블러", "노출 순위"),  # 프로그램 기록
        _grow("국산 텀블러", ""),                          # 직원 직접 입력(G 없음)
    ]}
    n = gsheet_stats.merge_staff_keywords(_StatsFake(grid), wb)
    assert n == 1, n
    kws = wb.product_keywords("가게A", "텀블러")
    assert kws[:2] == ["텀블러", "보온 텀블러"] and "국산 텀블러" in kws, kws   # 기존 보존 + 직원분 추가
    assert gsheet_stats.merge_staff_keywords(_StatsFake(grid), wb) == 0        # 재실행 무증가(idempotent)
    _ok("직원 키워드(옛 C열 폴백) 위치기반 파싱·1개 추가·기존 보존·재실행 idempotent")
    # 레이아웃 v4: 키워드명·소헤더가 **A열**인 결과시트도 정확히 읽어야(2026-09-25 read_staff_keywords A열 수정)
    wb2 = _sample_workbook()   # 가게A/텀블러, 키워드 [텀블러, 보온 텀블러]
    grid4 = {"가게A": [
        _growA(),                                                  # 제목행
        _growA(c="텀블러", g="날짜"),                               # 상품 헤더(상품명=C)
        _growA(a="상품명"), _growA(a="VID"),                        # v4 좌측 라벨(A) — 키워드 아님(소헤더 전)
        _growA(a="키워드", g="비고"),                               # 키워드 소헤더(A열)
        _growA(a="텀블러", g="노출 순위"), _growA(a="보온 텀블러", g="노출 순위"),
        _growA(a="v4직원키워드", g=""),                             # 직원 직접 입력(A열)
    ]}
    staff4 = gsheet_stats.read_staff_keywords(_StatsFake(grid4), wb2)
    assert staff4.get(("가게A", "텀블러")) == ["텀블러", "보온 텀블러", "v4직원키워드"], staff4
    n4 = gsheet_stats.merge_staff_keywords(_StatsFake(grid4), wb2)
    assert n4 == 1 and "v4직원키워드" in wb2.product_keywords("가게A", "텀블러"), wb2.product_keywords("가게A", "텀블러")
    # v4 A열 라벨(상품명/VID)은 키워드로 오인하지 않아야(소헤더 전이라 in_kw=False)
    assert "상품명" not in staff4.get(("가게A", "텀블러"), []) and "VID" not in staff4.get(("가게A", "텀블러"), [])
    _ok("직원 키워드 v4 A열 레이아웃 정확 파싱·좌측 라벨(상품명/VID) 오인 안 함·머지 반영")


def t8_exec_retry() -> None:
    """공통 재시도(_exec) — 일시적 오류(read timeout·429·5xx)는 지수백오프 재시도로 흡수,
    영구오류는 즉시 실패. 판매수집·키워드·순위 등 모든 구글시트 반영이 이 경로를 거친다."""
    import socket
    import time as _t
    from coupang_analytics.gsheet_api import GSheetClient, GSheetError

    class _Req:
        def __init__(self, fail_n, exc):
            self.n = 0
            self.fail_n = fail_n
            self.exc = exc

        def execute(self):
            self.n += 1
            if self.n <= self.fail_n:
                raise self.exc
            return {"ok": True, "tries": self.n}

    logs: list[str] = []
    c = GSheetClient("https://docs.google.com/spreadsheets/d/ABC123def456/edit",
                     sa_info={"client_email": "x@y.z"}, on_log=logs.append)
    orig_sleep = _t.sleep
    _t.sleep = lambda s: None                      # 테스트 즉시 실행(백오프 대기 제거)
    try:
        # (A) read timeout 2회 후 성공 → 재시도로 흡수
        r = c._exec(_Req(2, socket.timeout("The read operation timed out")), "통계 미러링")
        assert r["ok"] and r["tries"] == 3, f"재시도 후 성공 실패: {r}"
        assert sum("재시도" in m for m in logs) >= 2, f"재시도 로그 부족: {logs}"
        # (B) 계속 timeout → 재시도 소진 후 GSheetError
        try:
            c._exec(_Req(99, socket.timeout("timed out")), "영구타임아웃")
            raise AssertionError("영구 timeout인데 예외 안 남")
        except GSheetError:
            pass
        # (C) 비일시적 오류(400류)는 재시도 없이 즉시 실패
        logs.clear()
        try:
            c._exec(_Req(99, ValueError("invalid range 400")), "영구오류")
            raise AssertionError("비일시적인데 예외 안 남")
        except GSheetError:
            pass
        assert not any("재시도" in m for m in logs), f"비일시적인데 재시도함: {logs}"
    finally:
        _t.sleep = orig_sleep
    _ok("공통 재시도(_exec): 일시적 timeout 흡수·영구 timeout 소진 실패·비일시적 즉시 실패")


def main() -> int:
    print("=== 구글 시트 통합 오프라인 검증 ===")
    for fn in (t1_ledger_rows, t1b_ledger_strike, t1c_real_ledger_shape, t2_file_regression, t3_index_sync, t3b_full_and_incremental,
               t3d_grid_autogrow, t3c_delete_accounts, t3e_delete_renamed, t4_marketing_merge, t5_stats_mirror, t6_roster_from_workbook,
               t6b_multi_account_roster, t6c_content_col_widths, t7_staff_keywords_merge,
               t8_exec_retry):
        fn()
    print("=== 전부 통과 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
