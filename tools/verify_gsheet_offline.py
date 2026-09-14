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

_HEAD = ["사업자", "상품명(클릭 이동)", "계정ID", "체험단 시작일", "체험단 종료일", "모니터링 종료일", "상태"]


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


def _R(acct, prod, key, status="예정"):
    return IndexRow(business=f"biz_{acct}", product=prod, account_id=acct, status=status, key=key)


def _touched_data_mkt(req) -> set:
    uc = req.get("updateCells")
    if not uc or uc["start"].get("rowIndex", 0) < DATA_START0:
        return set()
    start = uc["start"]["columnIndex"]; ncol = len(uc["rows"][0]["values"])
    return {c for c in range(start, start + ncol) if c in (3, 4, 5)}


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
    reqs = gi._build_requests_for_plan(99, plan, band_by_acct)
    ins = [r["insertDimension"]["range"]["startIndex"] for r in reqs if "insertDimension" in r]
    assert ins == sorted(ins) == [DATA_START0 + 2, DATA_START0 + 4], ins
    assert not [c for r in reqs for c in _touched_data_mkt(r)], "마케팅열 값 기록 침범"
    # 판매중지 행(kA2, DATA_START0+1)도 사업자 밴드색으로 행 전체(A~G) 배경만 칠함(값 보존)
    disc_row = DATA_START0 + 1
    fullrow_bg = [r for r in reqs if "repeatCell" in r
                  and r["repeatCell"]["range"].get("startRowIndex") == disc_row
                  and r["repeatCell"]["range"].get("startColumnIndex", 0) == 0
                  and r["repeatCell"]["range"].get("endColumnIndex") == gi.N_COLS]
    assert len(fullrow_bg) == 1, "판매중지 행 전체 밴드색 누락"
    assert fullrow_bg[0]["repeatCell"]["fields"] == "userEnteredFormat.backgroundColor"  # 값 미기록
    _ok("그룹내 삽입·새계정 맨아래·판매중지=상태+사업자밴드색(값보존)·삽입 오름차순·마케팅 D~F 값 미기록")


class _FakeClient:
    def __init__(self, values): self._v = values; self.batches = []
    def sheet_titles(self): return ["계정목록"] if self._v else []
    def ensure_sheet(self, name): return 7
    def read_grid(self, sheet, notes=False): return self._v, [[None] * len(r) for r in self._v]
    def batch_update(self, reqs): self.batches.append(reqs); return {}


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
        ["계정목록 · 상품 3개"], _HEAD,
        ["biz_A", "상품1", "A", "2026-09-01", "2026-09-30", "", "체험단중"],
        ["biz_A", "상품2", "A", "", "", "", "예정"],
        ["biz_B", "상품3", "B", "", "", "", "예정"],
    ]
    fc2 = _FakeClient(existing_vals)
    p2 = gi.sync_index(fc2, desired)
    assert len(p2.inserts) == 1 and p2.inserts[0][1].product == "상품4"
    assert len(p2.discontinue) == 1                          # 상품2 사라짐
    _ok("기존 시트 → 증분(상품4 신규 삽입, 상품2 판매중지)")


def t4_marketing_merge() -> None:
    print("[4] 마케팅 역방향 머지(read_marketing/apply_marketing)")
    values = [
        ["계정목록 · 상품 3개"], _HEAD,
        ["가게A", "텀블러", "idA", "2026-09-01", "2026-09-30", "2026-10-31", "체험단중"],
        ["가게A", "보온병", "idA", "", "", "", "예정"],        # 마케팅 없음 → 스킵
        ["가게B", "우산", "idB", "2026-09-10", "", "", "예정"],
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
    assert "#gid=7&range=A1" in flat and "계정 목록" in flat               # 복귀 링크 → 계정목록 gid
    _ok("전체교체 요청(병합해제·틀고정 H2·복귀 HYPERLINK) + 등록명 보존")


def t6_roster_from_workbook() -> None:
    print("[6] roster_from_workbook — 등록명 기반 안정키·노출명 표시·통계링크")
    wb = _sample_workbook()
    wb.set_display_name("가게A", "텀블러", "스텐 텀블러 500ml")
    roster = gi.roster_from_workbook(wb, {"가게A": 42})
    r0 = next(r for r in roster if r.product)
    assert r0.business == "가게A" and r0.account_id == "idA"
    assert r0.product == "스텐 텀블러 500ml"                              # B=노출명(표시)
    assert r0.key == gi.marketing_key("idA", "텀블러")                    # 안정키=계정ID+등록명(노출명 아님)
    assert r0.link_gid == 42 and r0.link_row is not None
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
    assert bg_cols == {0, 1, 2, 6}, bg_cols          # _auto_cells_request는 A·B·C·G 담당
    # D~F는 _mkt_fill_request가 같은 밴드색으로(행 전체 동일 바탕색) + 값은 안 건드림(repeatCell)
    mreq = gi._mkt_fill_request(1, DATA_START0, 1)
    rc = mreq["repeatCell"]
    assert rc["cell"]["userEnteredFormat"]["backgroundColor"] == gi._band_fill(1)
    assert "userEnteredValue" not in str(rc["fields"])   # 배경/정렬만 — 값 미기록(직원 입력 보존)
    _ok("노출명·안정키·통계링크 + 행 전체 사업자 밴드색(A~G, D~F는 값 보존한 채 배경만)")


def _grow(c="", g=""):
    """통계 시트 한 행(0-based 격자) — C(3열=index2)=이름, G(7열=index6)=지표."""
    r = [""] * 7
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
    _ok("직원 키워드 위치기반 파싱·1개 추가·기존 보존·재실행 idempotent(→그 상품 AI 선정 생략)")


def main() -> int:
    print("=== 구글 시트 통합 오프라인 검증 ===")
    for fn in (t1_ledger_rows, t1b_ledger_strike, t1c_real_ledger_shape, t2_file_regression, t3_index_sync, t3b_full_and_incremental,
               t4_marketing_merge, t5_stats_mirror, t6_roster_from_workbook, t7_staff_keywords_merge):
        fn()
    print("=== 전부 통과 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
