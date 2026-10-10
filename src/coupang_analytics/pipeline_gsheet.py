"""파이프라인 ↔ 구글시트 연동(입력 관리대장·결과 시트)·백업·마스터 복원.

pipeline.py 에서 분리(대형 파일 정비, 행동 불변). 구글 관련 모듈(gsheet·gsheet_api·gsheet_index·
gsheet_stats·input_list)은 **함수 내부 지연 import**(순환·초기화비용 회피, 기존 방식 유지).
pipeline.py 가 이 심볼들을 다시 import 해 `pipeline.X` 공개 API(UI·도구)를 그대로 유지한다.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .pipeline_paths import _load_latest_wb, _master_path
from .workbook import OutputWorkbook


def restore_master_from_gsheet(out_dir: str | Path, url: str | None, on_log=None) -> bool:
    """통계 마스터(_통계.xlsx)가 없을 때 **결과 구글시트(전체 미러)에서 통째로 내려받아 복원**.

    다른 PC·재설치로 마스터가 없으면 '첫 실행'으로 오판해 과거 날짜 컬럼(시계열)을 유실한다 → 결과
    구글시트가 있으면 **서비스계정(Sheets API)** 으로 값을 읽어 마스터를 복원해 이어쓴다(소유자 2026-09-20, fix ③).
    E2(2026-10-10): 예전 공개 export 는 결과시트가 SA 공유만(비공개)이라 401 — 백업과 같은 SA 경로로, 숫자가 글자로
    바뀌지 않게 저장 타입 그대로(UNFORMATTED) 읽는다.
    ⚠ 구글시트는 **가시 시트(계정목록·사업자별 통계)만** 미러라 숨김 메타(_상품ID/_마케팅 등)는 없다
    → 복원본은 과거 '값(시계열)'을 살리고, 숨김 메타는 다음 ①판매수집이 재구성(vid 재발견·대장 매칭).
    성공=True(이어쓰기), 실패=사유 로그 후 False(정상 첫 실행 — fallback 금지 원칙에 따라 조용히 넘기지 않음).
    """
    log = on_log or (lambda m: None)
    master = _master_path(out_dir)
    if master.exists() or not url:
        return False
    try:
        _download_gsheet_via_sa(url, master, log=log, unformatted=True)
        OutputWorkbook.load(master)          # 유효한 워크북인지 확인(빈/손상 파일이면 예외 → 첫 실행)
    except Exception as exc:
        if master.exists():
            try:
                master.unlink()              # 손상 파일 잔재 제거(다음 저장이 깨끗한 첫 실행으로)
            except OSError:
                pass
        log("== ⚠ 마스터가 없어 결과 구글시트에서 복원을 시도했으나 실패 — 새 통계로 시작합니다 "
            f"({exc.__class__.__name__}: {str(exc)[:120]}) ==")
        return False
    _strip_gsheet_index_tab(master, log)   # 복원본에 섞여온 인덱스 탭 '계정목록'(공백 없음) 제거(오염 방지)
    log(f"== 마스터 파일이 없어 결과 구글시트에서 복원했습니다 → {master.name} "
        "(과거 통계 이어쓰기 · 숨김 메타는 다음 판매수집이 재구성) ==")
    return True


def _strip_gsheet_index_tab(master: Path, log) -> None:
    """복원 마스터에서 **결과 구글시트의 인덱스 탭 '계정목록'(공백 없음)** 을 제거한다.

    결과 구글시트를 통째로 내려받으면 인덱스 탭 `계정목록`(gsheet_index.INDEX_SHEET_NAME, 공백 없음)까지 딸려온다.
    마스터 자체 인덱스는 `계정 목록`(공백 있음)이라, 이 탭을 두면 account_sheets 가 통계로 오인 → 미러링 중복 +
    계정목록 동기화 충돌(400). 복원 직후 지운다(마스터 인덱스는 다음 저장이 다시 만든다). 방어=account_sheets 도
    공백 무시로 제외하지만, 파일에 남겨두지 않는 게 깔끔하다."""
    import openpyxl
    from .gsheet_index import INDEX_SHEET_NAME   # '계정목록'(공백 없음)
    try:
        wb = openpyxl.load_workbook(master)
        if INDEX_SHEET_NAME in wb.sheetnames and len(wb.sheetnames) > 1:
            del wb[INDEX_SHEET_NAME]
            wb.save(master)
            log(f"  [복원] 구글시트 인덱스 탭 '{INDEX_SHEET_NAME}' 제거(마스터 자체 인덱스와 중복 방지)")
        wb.close()
    except Exception as exc:   # 실패해도 복원 자체는 유효(account_sheets 방어가 있음) — 조용히 넘기지 않고 로그
        log(f"  [복원] ⚠ 인덱스 탭 정리 건너뜀 — {exc.__class__.__name__}: {str(exc)[:80]}")


def _safe_sheet_name(title: str, used: set[str]) -> str:
    """openpyxl 시트명 제약(31자·금지문자 []:*?/\\)에 맞춰 안전화 + 중복 회피."""
    import re
    name = re.sub(r"[\[\]:*?/\\]", "_", (title or "시트").strip()) or "시트"
    name = name[:31]
    base, i = name, 1
    while name in used:
        suffix = f"_{i}"
        name = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(name)
    return name


def _download_gsheet_via_sa(url: str, dest: Path, *, log, unformatted: bool = False) -> None:
    """결과 구글시트를 **서비스계정(Sheets API)** 으로 읽어 로컬 xlsx(값 스냅샷)로 저장한다.

    공개 export(gsheet.download_xlsx)는 시트를 '링크 공유(공개)'해야 하는데, 결과시트는 SA 공유만(비공개)이라
    401 로 실패했다(2026-10-02 실측). SA 로 각 시트 값을 읽어 openpyxl 로 쓴다(서식·수식 없는 **값 스냅샷** =
    작업 전 원본 보존이라는 백업 목적엔 충분). SA 미등록·권한없음(403)·없음(404)은 GSheetClient 가 GSheetError
    로 올린다(호출부가 로그로 명시). ⚠ 비밀번호 평문이 있는 관리대장에는 쓰지 않는다(결과시트 전용 — 호출부 참조).
    unformatted=True = 저장 타입 그대로(마스터 복원용 — 숫자 칸이 글자가 되지 않게). 백업은 표시값.
    """
    import openpyxl
    from . import gsheet_api
    client = gsheet_api.GSheetClient(url, on_log=log)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)                 # 기본 빈 시트 제거(각 구글 시트로 다시 채움)
    used: set[str] = set()
    for title in client.sheet_titles():
        ws = wb.create_sheet(_safe_sheet_name(title, used))
        for row in client.read_values(title, unformatted=unformatted):
            ws.append(list(row))
    if not wb.sheetnames:                # 시트가 하나도 없으면(이례) 빈 파일 저장 방지
        wb.create_sheet("빈")
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def backup_sources(out_dir: str | Path = "output", *, input_url: str | None = None,
                   output_url: str | None = None, on_log=None) -> list[Path]:
    """작업 시작 전 원본 백업 — **로컬 통계 마스터 + 결과 구글시트(SA 값 스냅샷)**를 타임스탬프 로컬 xlsx 로
    `output/백업/` 에 저장한다(소유자 2026-09-20: 항상 작업 전 별도 백업 후 진행).

    실패는 **로그로 명시**하되 작업을 막지 않는다(백업 실패 ≠ 작업 중단, 하지만 조용히 넘기지 않음).
    결과시트 백업은 **서비스계정(Sheets API)** 으로 한다(공개 export 폐기 — 결과시트는 SA 공유만이라 401,
    2026-10-02 실측). **관리대장(입력)은 평문 비밀번호가 있어 로컬 백업하지 않는다**(출력물 평문 금지,
    CLAUDE.md 보안규칙 — 복구는 구글 시트 버전기록으로 충분). 반환=저장된 백업 파일 목록.
    """
    log = on_log or (lambda m: None)
    out = Path(out_dir)
    bdir = out / "백업"
    ts = datetime.now().strftime("%y%m%d_%H%M%S")
    saved: list[Path] = []
    try:
        bdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"== [백업] ⚠ 백업 폴더 생성 실패 — 백업 없이 진행: {exc} ==")
        return saved
    # 1) 로컬 통계 마스터(있으면)
    master = _master_path(out)
    if master.exists():
        dest = bdir / f"통계마스터_{ts}.xlsx"
        try:
            shutil.copy(master, dest)
            saved.append(dest)
            log(f"== [백업] 통계 마스터 → 백업/{dest.name} ==")
        except OSError as exc:
            log(f"== [백업] ⚠ 통계 마스터 백업 실패(진행): {exc} ==")
    # 2) 결과 구글시트(있으면) — 서비스계정(Sheets API)으로 값 스냅샷 백업(공개 export 401 폐기)
    if output_url:
        dest = bdir / f"결과시트_{ts}.xlsx"
        try:
            _download_gsheet_via_sa(output_url, dest, log=log)
            saved.append(dest)
            log(f"== [백업] 결과시트 구글시트(SA) → 백업/{dest.name} ==")
        except Exception as exc:   # SA 미등록·권한없음(403/404)·네트워크 등 → 명시 후 진행(작업은 계속)
            log(f"== [백업] ⚠ 결과시트 구글시트 백업 실패(진행): {exc.__class__.__name__}: {str(exc)[:120]} ==")
    # 3) 관리대장(입력)은 **평문 비밀번호**가 있어 로컬 백업 파일로 내려받지 않는다(출력물 평문 금지).
    #    앱이 수정하는 건 재고 2개 열뿐이라 복구는 구글 시트 버전기록으로 충분하다(보안 > 로컬 백업 편의).
    if input_url:
        log("== [백업] 관리대장은 평문 비밀번호가 있어 로컬 백업 생략(보안규칙) — 복구는 구글시트 버전기록 사용 ==")
    if saved:
        log(f"== [백업] 작업 전 원본 {len(saved)}개 백업 완료(output/백업/) ==")
    return saved


def pull_gsheet_keywords(wb, output_url: str | None, log) -> None:
    """실행 시작 시 결과 통계 시트의 **직원 입력 키워드**를 워크북으로 역머지(그 상품은 AI 선정 대신 동결).

    output_url 없거나 SA 미등록이면 조용히 생략(정상 — 구글 통합 미사용). 실패는 로그로 명시하되 실행을
    막지 않는다(읽기 실패 시 AI 선정으로 진행). 첫 실행엔 통계 시트가 아직 없어 no-op(정상)."""
    if not output_url:
        return
    try:
        from . import gsheet_api, gsheet_stats
        if not gsheet_api.load_sa_info():
            return
        client = gsheet_api.GSheetClient(output_url, on_log=log)
        n = gsheet_stats.merge_staff_keywords(client, wb, on_log=log)
        if n:
            log(f"== [구글시트] 직원 입력 키워드 반영 {n}개 상품 → 해당 상품 AI 선정 생략(동결) ==")
    except Exception as exc:
        log(f"== [구글시트] 직원 키워드 읽기 실패: {exc.__class__.__name__}: {exc} (AI 선정으로 진행) ==")


def push_ledger_inventory(input_url: str | None, log, out_dir: str = "output") -> None:
    """관리대장(**입력** 구글시트)의 '그로스 재고' 컬럼을 최신 마스터 재고로 역기록(전체실행·무인 종료 시).

    최신 마스터 워크북을 직접 로드해 재고를 뽑는다(단계들이 이미 저장 완료한 뒤 호출). 입력 URL 없거나 SA
    미등록이면 조용히 생략(정상). SA에 관리대장 편집권한 없으면 403 → **로그로 명시**하고 비치명(수집·결과시트는
    이미 저장됨). 직원 입력 다른 컬럼은 미접촉(그로스재고 셀만 갱신·미매칭·개인상품은 기존값 보존).
    """
    if not input_url:
        return
    try:
        from . import gsheet_api, input_list
        wb, _ = _load_latest_wb(Path(out_dir))
        if wb is None:
            return
        if not gsheet_api.load_sa_info():
            return
        client = gsheet_api.GSheetClient(input_url, on_log=log)
        n = input_list.write_ledger_inventory(client, wb, on_log=log)
        if n:
            log(f"== [관리대장] 그로스 재고 역기록 완료 — {n}개 상품(입력 대장 AD컬럼) ==")
    except Exception as exc:
        log(f"== [관리대장] 그로스 재고 역기록 실패(비치명 — SA 편집권한 확인): "
            f"{exc.__class__.__name__}: {str(exc)[:120]} ==")


def push_company_stock(stock_url: str | None, input_url: str | None, log) -> None:
    """재고현황(stock_url) → 관리대장(input_url) '회사보유재고' 열 역기록(전체실행·무인 종료 시, **그로스 재고 다음**).

    판매자배송용 회사 자체 재고(로켓그로스 '그로스 재고'와 별개·소유자 2026-09-29). stock_url/input_url 없거나
    SA 미등록이면 조용히 생략(정상). run_company_stock 은 폴백 없이 예외를 올리므로 여기서 try/로그로 감싼다
    (비치명 — 수집·결과시트·그로스 재고 역기록은 이미 완료). 무인(--auto)에서도 호출(대장 한 열만 갱신 = 그로스
    재고 역기록과 동급). 미리보기/반영은 UI 가 run_company_stock 을 직접(dry_run) 호출."""
    if not stock_url or not input_url:              # 미설정 = 오류 아닌 '생략' — 단, 조용히 넘기지 않고 알린다
        missing = [n for n, v in (("재고현황 링크(stock/url)", stock_url), ("관리대장 링크(gsheet/input_url)", input_url))
                   if not v]
        log(f"== [회사재고] {'·'.join(missing)} 미설정 — 회사보유재고 반영 생략 ==")
        return
    try:
        from . import company_stock, gsheet_api
        if not gsheet_api.load_sa_info():
            log("== [회사재고] 구글 서비스계정 키 미등록 — 회사보유재고 반영 생략 ==")
            return
        company_stock.run_company_stock(stock_url, input_url, on_log=log)
    except Exception as exc:
        log(f"== [회사재고] 실패(진행 — SA 권한·링크 확인): "
            f"{exc.__class__.__name__}: {str(exc)[:120]} ==")


def inject_company_stock(wb, stock_url: str | None, log) -> None:
    """재고현황 시트 → 워크북 **회사보유재고** 주입(계정목록 5열 표기용). apply_style(계정목록 렌더) 전에 호출.

    관리대장 역기록(push_company_stock)과 **별개**로, 계정목록에 보여주려 매 실행 재고현황을 읽어 워크북 인메모리에
    넣는다(마스터 미저장·다음 실행 재주입). stock_url 없거나 SA 미등록이면 no-op(정상 — 계정목록 공란). 실패는
    로그·비치명(계정목록·통계는 그대로 렌더). 읽기 전용(재고현황 시트를 쓰지 않음)."""
    if not stock_url:                                # 미설정 = '생략' 안내(오류 아님) — 계정목록 회사보유재고 공란
        log("== [회사재고] 재고현황 링크(stock/url) 미설정 — 계정목록 회사보유재고 표기 생략(공란) ==")
        return
    try:
        from . import company_stock, gsheet_api
        if not gsheet_api.load_sa_info():
            log("== [회사재고] 구글 서비스계정 키 미등록 — 계정목록 회사보유재고 표기 생략(공란) ==")
            return
        client = gsheet_api.GSheetClient(stock_url, on_log=log)
        tab = company_stock.resolve_tab(client, stock_url)
        stock, _warnings = company_stock.read_stock(client.read_values(tab))
        n = company_stock.apply_to_workbook(wb, stock)
        log(f"== [회사재고] 계정목록 표기 — 재고현황 '{tab}' {len(stock)}품목 → {n}개 상품 주입 ==")
    except Exception as exc:
        log(f"== [회사재고] ⚠ 계정목록 표기 생략(진행): {exc.__class__.__name__}: {str(exc)[:120]} ==")


def push_coupang_checks(registry_url: str | None, checks: dict, log) -> None:
    """2-2(§10-1): ①판매수집에서 산출한 쿠팡확인을 셀독등록원장에 **1회** 기록(비치명).

    registry_url 없거나 checks 비면 no-op(원장 미사용·②③·수집 0). write_coupang_check 는 폴백 없이
    예외를 올리므로 여기서 try/로그로 감싼다(원장 실패해도 xlsx·수집은 진행). 무인(--auto)에서도 호출됨
    (쿠팡확인=이력 없는 상태 열·그로스 재고 역기록과 동급, 소유자 2026-09-28)."""
    if not registry_url or not checks:
        return
    try:
        from . import gsheet_api, registry_gsheet   # 지연 import(순환 회피)
        client = gsheet_api.GSheetClient(registry_url, on_log=log)
        n = registry_gsheet.write_coupang_check(client, checks, on_log=log)
        log(f"== [원장] 쿠팡확인 {n}줄 기록 ==")
    except Exception as exc:
        log(f"== [원장] ⚠ 쿠팡확인 기록 실패(진행): {exc.__class__.__name__}: {str(exc)[:120]} ==")


def push_gsheet(wb, output_url: str | None, log, removed_accounts=None, renamed_accounts=None) -> None:
    """완성된 openpyxl 마스터를 결과 구글시트로 반영 — 통계 시트 미러링 + 계정목록 증분 동기화.

    output_url 없거나 서비스계정 미등록이면 조용히 생략(정상 — 구글 통합 미사용). 반영 실패는 **로그로 명시**
    (조용한 무시 아님)하되 파이프라인을 죽이지 않는다: xlsx 마스터·스냅샷은 이미 저장됐다(오프라인 백업).
    removed_accounts=[(사업자, 계정ID)…]: 관리대장에서 **줄이 사라진** 계정 → 결과 구글시트에서도 완전 삭제
    (계정목록 행 + 통계 시트). '판매중지'로 남은 건 여기 없음(유지+경고).
    renamed_accounts=[(옛사업자명, 계정ID)…]: 시트명 변경으로 **일원화**된 계정의 옛 이름 잔재 → 계정목록 옛
    이름 행·옛 통계 시트를 **이름 기준**으로 제거(계정ID는 새 이름과 공유하므로 이름 매칭). 새 이름은 미러링/동기화.
    """
    # ⚠ 조용한 스킵 금지 — 반영 안 된 이유를 **항상 로그로** 남긴다(정상종료인데 반영 안 됨을 추적 가능하게).
    if not output_url:
        log("== [구글시트] ⚠ 반영 생략 — **결과(출력) 시트 URL 미설정**. "
            "설정 탭 '구글 시트 연동'에 결과 시트 링크를 넣어야 반영됩니다(이 PC 설정, xlsx는 저장됨) ==")
        return
    _phase = "초기화"
    try:
        from . import gsheet_api, gsheet_index, gsheet_stats
        if not gsheet_api.load_sa_info():
            log("== [구글시트] ⚠ 반영 생략 — **서비스계정(SA) 키 미등록**(설정 탭에서 SA 키 입력 필요·이 PC 설정, xlsx는 저장됨) ==")
            return
        log(f"== [구글시트] 결과 반영 시작 — 출력시트 …{str(output_url)[-24:]} ==")
        _phase = "클라이언트 연결"
        client = gsheet_api.GSheetClient(output_url, on_log=log)
        if removed_accounts:   # 삭제된 계정 먼저 제거(행+시트) → 이후 미러링/동기화는 남은 것만 대상
            _phase = "삭제계정 정리"
            d = gsheet_index.delete_accounts(client, removed_accounts, on_log=log)
            if d:
                log(f"== [구글시트] 삭제된 계정 정리 — {len(removed_accounts)}개(계정목록 행·통계 시트 제거) ==")
        if renamed_accounts:   # 일원화된 옛 이름 잔재 제거(이름 기준) → 새 이름은 아래 미러링/동기화
            _phase = "일원화 옛이름 정리"
            r = gsheet_index.delete_renamed_accounts(client, renamed_accounts, on_log=log)
            if r:
                log(f"== [구글시트] 일원화 옛 이름 정리 — {len(renamed_accounts)}개"
                    f"({', '.join(nm for nm, _a in renamed_accounts)} 계정목록 행·옛 통계 시트 제거) ==")
        _phase = "통계 시트 미러링"
        log("== [구글시트] 통계 시트 미러링 중… ==")
        gids = gsheet_stats.push_statistics(client, wb, on_log=log)          # 사업자별 통계 시트 전체 미러링
        _phase = "계정목록 동기화"
        log(f"== [구글시트] 통계 {len(gids)}시트 미러링 완료 → 계정목록 동기화 중… ==")
        roster = gsheet_index.roster_from_workbook(wb, gids)                 # 계정목록 로스터(등록명 기반 안정키)
        plan = gsheet_index.sync_index(client, roster, on_log=log,          # 계정목록 증분(마케팅 G~I 보존)
                                       growth_asof=wb.growth_asof())          # 그로스재고 헤더 자동갱신일자

        log(f"== [구글시트] ✅ 결과 반영 완료 — 통계 {len(gids)}시트 · 계정목록 "
            f"갱신 {len(plan.updates)}·신규 {len(plan.inserts)}·판매중지 {len(plan.discontinue)} ==")
    except Exception as exc:
        # ⚠ 조용한 실패 금지 — 계정목록/통계가 최신이 아닐 수 있음을 **눈에 띄게** 경고(과거 이 실패를
        # 한 줄로 삼켜 계정목록이 옛 상태로 방치됨, 라이브 2026-09-23). 실행은 계속(xlsx 는 보존).
        log("== [구글시트] ❌❌ 결과 반영 실패 — **계정목록/통계가 최신이 아닐 수 있습니다(확인 필요)** ==")
        # ⚠ 잘림 금지(2026-09-28): 옛 `str(exc)[:200]` 은 긴 URL 뒤의 **Google 실제 사유**(returned "Invalid …")를
        # 잘라 원인 규명을 막았다(output(9) mergeCells 400 미확인). 사유 문구를 따로 뽑아 온전히 남긴다.
        _msg = str(exc)
        _reason = _msg.split("returned ", 1)[-1] if "returned " in _msg else _msg
        log(f"==   단계='{_phase}' · {exc.__class__.__name__}: {_msg[:150]} ==")
        log(f"==   Google 응답 사유: {_reason[:600]} ==")
        log("==   xlsx 마스터·스냅샷은 정상 저장됨. SA 편집권한·시트 공유·URL 확인 후 재실행하면 반영됩니다 ==")
