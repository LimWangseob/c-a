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
    구글시트가 있으면 export(xlsx)로 마스터를 복원해 이어쓴다(소유자 2026-09-20, fix ③).
    ⚠ 구글시트는 **가시 시트(계정목록·사업자별 통계)만** 미러라 숨김 메타(_상품ID/_마케팅 등)는 없다
    → 복원본은 과거 '값(시계열)'을 살리고, 숨김 메타는 다음 ①판매수집이 재구성(vid 재발견·대장 매칭).
    성공=True(이어쓰기), 실패=사유 로그 후 False(정상 첫 실행 — fallback 금지 원칙에 따라 조용히 넘기지 않음).
    """
    log = on_log or (lambda m: None)
    master = _master_path(out_dir)
    if master.exists() or not url:
        return False
    try:
        from . import gsheet
        gsheet.download_xlsx(url, master)
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


def backup_sources(out_dir: str | Path = "output", *, input_url: str | None = None,
                   output_url: str | None = None, on_log=None) -> list[Path]:
    """작업 시작 전 원본 백업 — **로컬 통계 마스터 + 결과 구글시트 + 관리대장 구글시트**를 타임스탬프
    로컬 xlsx 로 `output/백업/` 에 저장한다(소유자 2026-09-20: 항상 작업 전 별도 백업 후 진행).

    실패는 **로그로 명시**하되 작업을 막지 않는다(백업 실패 ≠ 작업 중단, 하지만 조용히 넘기지 않음).
    구글시트 백업은 export(xlsx)라 SA 없이도 공개공유면 됨. 반환=저장된 백업 파일 목록.
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
    # 2) 결과·관리대장 구글시트(있으면)
    for label, url in (("결과시트", output_url), ("관리대장", input_url)):
        if not url:
            continue
        dest = bdir / f"{label}_{ts}.xlsx"
        try:
            from . import gsheet
            gsheet.download_xlsx(url, dest)
            saved.append(dest)
            log(f"== [백업] {label} 구글시트 → 백업/{dest.name} ==")
        except Exception as exc:   # 공개공유 아님·네트워크 등 → 명시 후 진행(작업은 계속)
            log(f"== [백업] ⚠ {label} 구글시트 백업 실패(진행): {exc.__class__.__name__}: {str(exc)[:120]} ==")
    if saved:
        log(f"== [백업] 작업 전 원본 {len(saved)}개 백업 완료(output/백업/) ==")
    return saved


def _pull_gsheet_keywords(wb, output_url: str | None, log) -> None:
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


def _push_gsheet(wb, output_url: str | None, log, removed_accounts=None, renamed_accounts=None) -> None:
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
        plan = gsheet_index.sync_index(client, roster)                      # 계정목록 증분(마케팅 D~F 보존)
        log(f"== [구글시트] ✅ 결과 반영 완료 — 통계 {len(gids)}시트 · 계정목록 "
            f"갱신 {len(plan.updates)}·신규 {len(plan.inserts)}·판매중지 {len(plan.discontinue)} ==")
    except Exception as exc:
        # ⚠ 조용한 실패 금지 — 계정목록/통계가 최신이 아닐 수 있음을 **눈에 띄게** 경고(과거 이 실패를
        # 한 줄로 삼켜 계정목록이 옛 상태로 방치됨, 라이브 2026-09-23). 실행은 계속(xlsx 는 보존).
        log("== [구글시트] ❌❌ 결과 반영 실패 — **계정목록/통계가 최신이 아닐 수 있습니다(확인 필요)** ==")
        log(f"==   단계='{_phase}' · {exc.__class__.__name__}: {str(exc)[:200]} ==")
        log("==   xlsx 마스터·스냅샷은 정상 저장됨. SA 편집권한·시트 공유·URL 확인 후 재실행하면 반영됩니다 ==")
