"""셀독전환자 정산 2단계 — 정산 자료 받기(매일 18시 뒤 · 소유자 2026-11-08 D-179② · D-187 · 설계 §15 '2단계').

1단계(transfer_login — 로그인 확인)와 같은 계정 파일·비밀번호 후보·로그인 판정을 쓰고, 계정마다 원장 정산과 **같은 요청·받기 함수**
(tools/settlement_download 의 cmd_request·cmd_download — 이 모듈은 그 함수를 `work` 로 받음)로 2026-01-01 부터 정산 자료를 받는다.
저장 = output/정산_셀독전환/정산/(원장 정산 기록과 섞지 않음 — D-111 ⑥) · 끝마다 누적 엑셀을 받은 것 전부로 다시 만든다.

안전 규칙(런타임 병렬 금지·사무실 IP 보호):
- 17:40~20:40(운용 PC 18:00 시간대) · 앱 파이프라인 · 정산 자동 수집(watch)이 **모두 끝나야** 계정을 시작 — 계정마다 다시 확인하고
  돌면 **기다림**(5분마다). 멈춤 = 시작 뒤 처음 오는 17:40(밤 시작 = 다음 날) — 그때까지 못 하면 남은 계정은 다음 날.
- 로그인 '실패'(비밀번호 오류·2단계 인증·비밀번호 없음) 계정은 **무인으로 다시 넣지 않음**(같은 틀린 값 반복 = 계정 잠금 위험).
  비밀번호를 고친 뒤 사람이 1단계 '성공 안 된 계정만 다시'로 확인 → 성공하면 다음 날부터 받음.
- 계정 사이 45~75초 · 차단·미완료·오류 2계정 연속 = 전체 중단(1단계와 같음) · 1단계·2단계는 같은 잠금으로 한 번에 하나.
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import settlement_accounts as SA
from . import settlement_files as SF
from . import transfer_login as TL

OUT_DIR = TL.OUT_DIR
STORE_DIR = OUT_DIR / "정산"                       # 정산 계정과 같은 모양(_요청기록.json·파일·쿠팡지급내역·로그)
CUMULATIVE = OUT_DIR / "셀독전환_정산내역_누적.xlsx"
RUN_LOCK = TL.RUN_LOCK                            # 1단계·2단계 한 번에 하나
FROM = date(2026, 1, 1)                           # 정산 자료 시작(§15 · 지급일 기준)
CAP = 30                                          # 한 실행 계정당 요청 — 윙 다운로드 목록이 최근 30건만 보임(STATE 사실)
WAIT_POLL_SEC = 300
DAILY_KEY = "transfer/daily"                      # '1' 켬 · '0' 끔 · 빈 값 = 1단계 결과가 있는 PC 만 켬(소유자 '매일 18시 뒤' D-179②)
_OFF = ("0", "끔", "off", "false")


class CumulativeLocked(Exception):
    """누적 엑셀을 바꿔 끼우지 못함(엑셀에서 열려 있음 등) — 받은 파일은 그대로 남음."""


@dataclass
class SettleTarget(SA.SettleAccount):
    """원장 정산 함수에 넘길 계정(이름 = 대표자-사업자-계정ID) + 원장 파일 재사용 판단용 대표자명·사업자명."""
    names: tuple = ()


def daily_on(get=None, out_dir=OUT_DIR) -> bool:
    """18:00 무인·재부팅 복구 앱이 2단계를 함께 띄울지. 빈 값 = 1단계 결과(로그인확인_최신.json)가 있는 PC 만 — 없는 PC 는
    비밀번호 오류로 알려진 계정을 모름(지문 키도 PC 마다 다름) → 틀린 비번을 한 번 더 넣는 일을 막음. 탭 체크 = '1'·'0'."""
    if get is None:
        from . import appconfig
        get = appconfig.get
    v = (get(DAILY_KEY, "") or "").strip().lower()
    return v not in _OFF if v else (Path(out_dir) / TL.STATE_FILE).exists()


def settle_account(a) -> SettleTarget:
    label = "-".join(dict.fromkeys(x for x in (a.representative, a.business_name) if x)) or a.account_id
    return SettleTarget(a.account_id, label, "", names=(a.representative, a.business_name))


def display_name(a) -> str:
    """파일·기록의 계정명 = '대표자-사업자-계정ID'(원장 정산과 같은 규칙 SA.display_name)."""
    return SA.display_name(settle_account(a))


def apply_args(args) -> None:
    """원장 정산 함수가 읽는 실행 인자를 2단계 값으로: 시작 2026-01-01 · 계정당 요청 30 · 창 숨김(무인)."""
    args.start = max(args.start, FROM)
    args.cap = min(args.cap, CAP)
    args.hidden, args.dry_run = True, False
    args.until = TL.UNTIL_DEFAULT


# ── 대상·기다림 ─────────────────────────────────────────────────
def pick_targets(accts, state: dict) -> list:
    """로그인 '실패' 제외 — 성공·미확인·차단·건너뜀만(무인 재시도로 같은 틀린 비번을 넣지 않음)."""
    return [a for a in accts if (state.get(a.account_id) or {}).get("결과") != TL.FAIL]


def ready_reason(until: str, at: datetime, busy) -> str:
    if TL.in_quiet(until, at):
        return f"운용 PC 18:00 실행 시간대({until} 부터 {TL.QUIET_HOURS}시간)"
    return busy()


def wait_ready(until: str, stop_at: datetime | None, log, *, busy=TL.busy_reason, now=datetime.now,
               sleep=time.sleep) -> bool:
    """시작해도 되면 True · 멈춤 시각까지 안 되면 False. 이유가 바뀔 때만 로그."""
    last = ""
    while True:
        at = now()
        if stop_at and at >= stop_at:
            return False
        why = ready_reason(until, at, busy)
        if not why:
            return True
        if why != last:
            log(f"  ⏳ {why} — 끝나면 이어서(5분마다 확인" + (f" · 멈춤 {stop_at:%m-%d %H:%M})" if stop_at else ")"))
            last = why
        sleep(min(WAIT_POLL_SEC, (stop_at - at).total_seconds()) if stop_at else WAIT_POLL_SEC)


# ── 전체 ─────────────────────────────────────────────────────
def _one(a, pws: list, src: str, work, fp, out_dir, at: str, stop_at, log) -> str:
    """계정 하나 → 결과(로그인 기록에 갱신 — 비밀번호 값 대신 지문)."""
    log(f"== [{a.kind}] {a.label} ({a.account_id}) 정산 자료 받기 · 비밀번호 {src} ==")
    try:
        status, reason = work(a, pws, stop_at)
    except Exception as exc:   # 그 계정만 '건너뜀'(무음 아님 — 처리기록·오류 로그는 work 쪽)·다음 계정 진행
        status, reason = TL.SKIP, f"받기 중 오류 — {exc.__class__.__name__}: {str(exc)[:80]}"
    TL.save_result(out_dir, a.account_id, status, reason, src, at, [fp(a.account_id, p) for p in pws])
    log(f"  → {status}: {reason}")
    return status


def run(accts, log, work, *, until: str = TL.UNTIL_DEFAULT, out_dir=OUT_DIR, passwords=None, busy=TL.busy_reason,
        sleep=time.sleep, now=datetime.now, fp=None, gap=None) -> int:
    """대상 계정마다 기다림 확인 → work(a, 비번 후보, 멈춤 시각) → 결과 기록. 반환 0(끝·멈춤 시각) | 1(연속 문제 중단).
    비밀번호 후보가 없으면 로그인 안 하고 '실패' 기록 · 쉼(45~75초)은 로그인한 계정 사이만."""
    from . import login_today
    from . import transfer_accounts as TA
    passwords, fp = passwords or TA.login_passwords, fp or login_today.fingerprint
    gap = gap or (lambda: random.uniform(*TL.GAP_SEC))
    targets = pick_targets(accts, TL.load_state(out_dir))
    stop_at = TL.deadline_of(until, now())
    log(f"[셀독전환 정산] 대상 {len(targets)}계정 / 파일 {len(accts)}계정(로그인 '실패' 제외) · 멈춤 "
        + (f"{stop_at:%m-%d %H:%M}" if stop_at else "없음"))
    trouble, tried = 0, 0
    for a in targets:
        if not wait_ready(until, stop_at, log, busy=busy, now=now, sleep=sleep):
            log(f"  ⏸ 멈춤 시각({stop_at:%m-%d %H:%M}) — 남은 계정은 다음 실행에서 이어서")
            return 0
        pws, src = passwords(a)
        if not pws:
            TL.save_result(out_dir, a.account_id, TL.FAIL, "비밀번호 없음(파일·관리대장 모두)", src,
                           now().isoformat(sep=" ", timespec="seconds"))
            log(f"  [{a.label}] 비밀번호 없음 — 연락 필요로 기록(로그인 안 함)")
            continue
        if tried:
            sleep(gap())
        tried += 1
        status = _one(a, pws, src, work, fp, out_dir, now().isoformat(sep=" ", timespec="seconds"), stop_at, log)
        trouble = trouble + 1 if status in (TL.BLOCK, TL.SKIP) else 0
        if trouble >= TL.BLOCK_STOP:
            log(f"  ⛔ 차단·미완료·오류 {TL.BLOCK_STOP}계정 연속 — 전체 중단(사무실 IP 차단 의심·다른 계정 보호)")
            return 1
    return 0


# ── 원장 정산 파일 재사용 ─────────────────────────────────────────
def find_reusable(folder: Path, account_id: str, names: tuple, fname: str) -> Path | None:
    """원장 정산 폴더에서 fname 과 같은 정산일·채널·유형·리포트·기간 + 같은 계정의 파일. 같은 계정 = 이름 끝이 계정ID 이고
    앞부분(대표자-사업자)에 전환자 대표자명 또는 사업자명이 칸 그대로 있음('plan_it'·'it' 처럼 끝만 같은 계정 구분)."""
    if not Path(folder).is_dir():
        return None
    tok = SF._token(account_id, "계정ID")
    suffix = fname.split("_", 1)[1]
    want = [SF._token(n, "이름") for n in names if str(n or "").strip()]
    for p in sorted(Path(folder).iterdir()):
        if not (p.is_file() and p.name.endswith("_" + suffix)):
            continue
        acct = p.name[: -len(suffix) - 1]
        if acct.endswith("-" + tok) and any(f"-{n}-" in f"-{acct[: -len(tok) - 1]}-" for n in want):
            return p
    return None


# ── 누적 파일 ─────────────────────────────────────────────────────
GUIDE = (
    ("무엇", "미정산 셀독전환자(①②) 계정의 쿠팡 정산 자료 — 2026-01-01 부터 받은 것 전부(실행마다 다시 만듦 · D-187)"),
    ("돈 합계", "'지급 내역' 시트(쿠팡 정산현황 그대로 · 최종지급액). '상품별 정산'은 상품 구분용 — 주정산·최종액 파일은 같은 주문이 "
              "겹칠 수 있어 '정산 유형' 칸으로 구분"),
    ("상품 칸", "쿠팡 정산 파일 원본 그대로 — 상품 ID = 윙 '상품 ID'·로켓그로스 '등록상품 ID' · 옵션 ID(VID) = 윙 '옵션 ID'·"
              "로켓그로스 '옵션ID' · 상품명·옵션명 = 파일 원문"),
    ("원본", "output/정산_셀독전환/정산/파일 (비용 리포트 = 파일/비용) · 지급 내역 원본 = 정산/쿠팡지급내역"),
    ("빠진 계정", "'계정별 요약'의 로그인 결과가 '실패'(비밀번호 오류·2단계 인증·비밀번호 없음) = 연락 필요(1단계 결과 엑셀 '연락 필요')"),
)
SUMMARY_HEAD = ("유형", "대표자명", "사업자명", "계정명", "로그인 결과", "지급 줄", "최종지급액 합", "정산 파일", "비용 리포트",
                "상품 줄", "마지막 정산일", "남은 요청")
PAY_HEAD = ("유형", "대표자명", "사업자명", "계정명", "채널", "정산일", "기간 시작", "기간 끝", "지급비율", "최종지급액", "지급상태")
PROD_HEAD = ("유형", "대표자명", "사업자명", "계정명", "채널", "정산일", "정산 유형", "기간 시작", "기간 끝", "주문번호", "상품 ID",
             "옵션 ID(VID)", "상품명", "옵션명", "수량", "판매액", "판매자 할인쿠폰", "수수료", "정산금액", "매출인식일",
             "구매확정·거래유형", "파일")


def _gather(a, store: Path, jobs: list, log) -> tuple[list, list, dict]:
    """계정 하나 → (지급 줄, 상품 줄, 요약 칸)."""
    from . import settlement_jobs as SJ
    who = (a.kind, a.representative, a.business_name, a.account_id)
    tok = SF._token(display_name(a), "계정명")
    pays, prods, last = [], [], ""
    for ch in (SF.CH_WING, SF.CH_RG):
        p = store / "쿠팡지급내역" / f"{tok}_{ch}.json"
        for r in json.loads(p.read_text(encoding="utf-8")) if p.exists() else []:
            pays.append((*who, ch, r["정산일"], r["기간 시작"], r["기간 끝"], r.get("지급비율"), r.get("최종지급액"),
                         r.get("지급상태", "")))
            last = max(last, r["정산일"])
    files = sorted((store / "파일").glob(f"{tok}_*.xlsx"))
    for f in files:
        try:
            sf = SF.load_settle_file(f)
        except Exception as exc:   # 읽지 못한 파일은 그 파일만 빼고 이유를 남김(무음 아님)
            log(f"  ❌ 누적 파일 — {f.name} 을 읽지 못함: {exc.__class__.__name__}: {str(exc)[:100]}")
            continue
        last = max(last, sf.settle_date.isoformat())
        for r in sf.rows:
            prods.append((*who, sf.channel, sf.settle_date.isoformat(), sf.kind, r.period_start.isoformat(),
                          r.period_end.isoformat(), r.order_id, r.product_id, r.option_id, r.product_name, r.option_name,
                          r.qty, r.sales, r.coupon, r.fee, r.settle, r.recognized.isoformat() if r.recognized else "",
                          r.kind, f.name))
    name = display_name(a)
    left = sum(1 for j in jobs if j.account == name and j.status in (SJ.ST_PLANNED, SJ.ST_REQUESTED))
    costs = len(list((store / "파일" / "비용").glob(f"{tok}_*.xlsx")))
    return pays, prods, {"지급 줄": len(pays), "최종지급액 합": sum(int(x[9] or 0) for x in pays), "정산 파일": len(files),
                         "비용 리포트": costs, "상품 줄": len(prods), "마지막 정산일": last, "남은 요청": left}


def build_cumulative(accts, state: dict, store=STORE_DIR, out=CUMULATIVE, now: datetime | None = None, log=None) -> Path:
    """받은 것 전부 → 누적 엑셀(임시 파일에 쓰고 바꿔 끼움). 바꿔 끼우지 못하면 CumulativeLocked."""
    import openpyxl
    from openpyxl.utils import get_column_letter
    from . import settlement_jobs as SJ
    log = log or (lambda m: None)
    store, out, now = Path(store), Path(out), now or datetime.now()
    jobs = SJ.load_jobs(store / "_요청기록.json") if (store / "_요청기록.json").exists() else []
    wb = openpyxl.Workbook()
    guide = wb.active
    guide.title = "안내"
    for row in (("만든 시각", f"{now:%Y-%m-%d %H:%M:%S}"), *GUIDE):
        guide.append(row)
    sheets = {"계정별 요약": SUMMARY_HEAD, "지급 내역": PAY_HEAD, "상품별 정산": PROD_HEAD}
    ws = {t: wb.create_sheet(t) for t in sheets}
    for t, head in sheets.items():
        ws[t].append(head)
    for a in accts:
        pays, prods, summ = _gather(a, store, jobs, log)
        login = (state.get(a.account_id) or {}).get("결과", "미확인")
        ws["계정별 요약"].append((a.kind, a.representative, a.business_name, a.account_id, login,
                                *(summ[h] for h in SUMMARY_HEAD[5:])))
        for r in pays:
            ws["지급 내역"].append(r)
        for r in prods:
            ws["상품별 정산"].append(r)
    for sh in wb.worksheets:
        sh.freeze_panes = "A2"
        for i in range(1, sh.max_column + 1):
            sh.column_dimensions[get_column_letter(i)].width = 70 if sh.title == "안내" and i == 2 else 16
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.xlsx")
    wb.save(tmp)
    try:
        os.replace(tmp, out)
    except PermissionError as exc:
        tmp.unlink()
        raise CumulativeLocked(f"{out} — 엑셀에서 열려 있어 바꾸지 못함(닫으면 다음 실행에서 다시 만듦)") from exc
    return out


# ── 명령줄(정산다운로드.exe transfer-settle — 18:00 무인 앱·'셀독전환 정산' 탭이 띄움) ──────────────────────
def main_cli(args, work, log) -> int:
    """args: file·accounts. 반환 0 | 1(연속 문제 중단) | 2(파일 오류·다른 셀독전환 실행 중) | 3(누적 파일 못 씀)."""
    from .registry_lock import RegistryLockError, registry_lock
    try:
        with registry_lock(RUN_LOCK, wait_sec=0):
            return _main(args, work, log)
    except RegistryLockError:
        log("[셀독전환 정산] ⛔ 다른 셀독전환 실행(로그인 확인·정산 자료 받기)이 도는 중 — 이 실행은 끝냄")
        return 2


def _main(args, work, log) -> int:
    from . import appconfig
    from . import transfer_accounts as TA
    path = args.file or appconfig.get(TA.CONFIG_KEY, "") or TA.DEFAULT_PATH
    try:
        accts, warns = TA.read_transfer_file(path)
    except TA.TransferFileError as exc:
        log(f"[셀독전환 정산] ⛔ 파일 오류 — {exc} ('셀독전환 정산' 탭에서 전환자 파일 지정)")
        return 2
    for w in warns:
        log(f"  [파일] ⚠ {w}")
    only = {x.strip() for x in (args.accounts or "").split(",") if x.strip()}
    if only - {a.account_id for a in accts}:
        log(f"[셀독전환 정산] ⛔ 파일에 없는 계정: {sorted(only - {a.account_id for a in accts})}")
        return 2
    accts = [a for a in accts if not only or a.account_id in only]
    log(f"[셀독전환 정산] 파일 {path} · ①② {len(accts)}계정 · 저장 {STORE_DIR}")
    rc = run(accts, log, work)
    try:
        out = build_cumulative(accts, TL.load_state(), log=log)
    except CumulativeLocked as exc:
        log(f"[셀독전환 정산] ❌ 누적 파일 — {exc}")
        return 3
    log(f"[셀독전환 정산] 끝 — 누적 파일 {out.resolve()}")
    return rc
