"""정산 다운로드 실행 기록 — 정상/비정상 분석용(소유자 요구 2026-10-06).

한 번 실행마다 output/정산/로그/ 아래에:
- `실행_{실행ID}.log`   : 화면에 찍히는 모든 줄(타임스탬프 포함) — 흐름 추적.
- `처리기록_{실행ID}.csv`: 계정·단계·채널·유형·**정산일**·기간·결과·사유 한 줄씩 — 날짜별 정상/비정상 분석(엑셀로 열림).
  같은 줄을 `처리기록_누적.csv` 에도 덧붙인다(실행을 넘어 비교).
- `오류_{실행ID}.log`   : 예외 전체 추적(traceback) — 원인 분석.
결과 값: 정상 · 건너뜀 · 대기 · 실패 · 차단. 로그인은 단계='로그인'(결과에 판정 코드), 차단 감지는 결과='차단'.
비밀번호·구매자명 등 개인정보는 남기지 않는다(호출부가 넘기지 않음·사유 글자도 200자로 자름).
실행 끝 [실행 결과 종합](D-168) = `result_block` — 판정·전체 계정·비밀번호 오류 계정·사람 조치·오류 현황·받은 파일 전부·남은 소급.
"""
from __future__ import annotations

import csv
import os
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

OK, SKIP, WAIT, FAIL, BLOCK = "정상", "건너뜀", "대기", "실패", "차단"
FIELDS = ("시각", "실행ID", "계정", "단계", "채널", "유형", "정산일", "기간", "결과", "사유")


class RunLog:
    def __init__(self, base_dir, *, now: datetime | None = None, echo=print):
        self.now = now or datetime.now()
        self.run_id = self.now.strftime("%y%m%d_%H%M%S")
        self.dir = Path(base_dir) / "로그"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.text = self.dir / f"실행_{self.run_id}.log"
        self.csv = self.dir / f"처리기록_{self.run_id}.csv"
        self.total = self.dir / "처리기록_누적.csv"
        self.errors = self.dir / f"오류_{self.run_id}.log"
        self.status = self.dir / "_현재상태.txt"   # 매 실행이 **덮어쓰는** 고정 경로 — 창 없는 자동 실행 모니터링용.
        self.echo = echo
        self.rows: list[dict] = []
        self.accounts: list[str] = []                     # 이번 실행 대상 계정 이름(호출부가 채움)
        self.files: list[tuple[str, str, str]] = []       # 이번 실행에서 받은·저장한 파일 (계정, 전체 경로, 메모)
        self.left: dict[tuple[str, str], tuple[int, str]] = {}   # 남은 소급 {(계정, 종류): (수, 단위)} — 마지막 값

    def saved(self, account: str, path, note: str = "") -> None:
        """받은·저장한 파일 하나를 [실행 결과 종합]의 '받은 파일' 목록에 올린다(처리기록 CSV 칸은 그대로)."""
        self.files.append((account, str(Path(path).resolve()), note))

    def remaining(self, account: str, kind: str, n: int, unit: str) -> None:
        """그 계정의 남은 소급(예: 판매분석 120일) — 같은 계정·종류는 마지막 값만."""
        self.left[(account, kind)] = (int(n), unit)

    def line(self, msg: str) -> None:
        stamped = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        self.echo(stamped)
        with self.text.open("a", encoding="utf-8") as f:
            f.write(stamped + "\n")

    def heartbeat(self, status: str, detail: str = "", *, extra: tuple[str, ...] = ()) -> None:
        """현재 상태를 고정 경로(`로그/_현재상태.txt`)에 **덮어쓴다**(append 아님) — 창 없는(console=False)
        자동 실행을 운용 PC에서 한눈에 확인(살아있나·뭘 하나). 매 호출마다 '갱신' 시각이 바뀌어 생존 신호가 된다.
        비밀번호·구매자명 등 개인정보는 호출부가 넘기지 않는다(내용은 300자로 자름). 임시파일→os.replace 로
        읽는 쪽이 반쪽 파일을 보지 않게 한다."""
        lines = [
            "정산 자동 다운로드 — 현재 상태",
            f"갱신: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"상태: {status}",
            f"내용: {str(detail)[:300]}",
            f"실행ID: {self.run_id}",
            f"상세 로그: {self.text.name}",
            *extra,
        ]
        tmp = self.status.with_name(self.status.name + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, self.status)

    def record(self, account: str, step: str, result: str, reason: str = "", *, channel: str = "", kind: str = "",
               settle_date: str = "", period: str = "") -> None:
        row = {"시각": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "실행ID": self.run_id, "계정": account, "단계": step,
               "채널": channel, "유형": kind, "정산일": settle_date, "기간": period, "결과": result,
               "사유": str(reason)[:200]}
        self.rows.append(row)
        for path in (self.csv, self.total):
            new = not path.exists()
            with path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                w.writerow(row)
        mark = {OK: "✔", SKIP: "·", WAIT: "…", FAIL: "✖", BLOCK: "⛔"}.get(result, "?")
        what = " ".join(x for x in (channel, kind, settle_date and f"정산일 {settle_date}", period) if x)
        self.line(f"  {mark} [{step}] {account} {what} → {result}" + (f" ({reason})" if reason else ""))

    def error(self, account: str, step: str, exc: BaseException, result: str = FAIL, **fields) -> None:
        """예외를 처리기록(사유=종류: 메시지·채널/정산일 등 fields)과 오류 로그(전체 추적) 양쪽에 남긴다."""
        self.record(account, step, result, f"{exc.__class__.__name__}: {exc}", **fields)
        with self.errors.open("a", encoding="utf-8") as f:
            f.write(f"===== {datetime.now():%Y-%m-%d %H:%M:%S} · {account} · {step} =====\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            f.write("\n")

    def unresolved_failures(self) -> dict[str, str]:
        """이번 실행에서 **실패로 끝난 계정** {계정: 마지막 실패 단계} — 실패·차단 뒤 정상 기록이 없는 계정만(다음 바퀴에
        다시 받아 해소된 계정은 제외). 완료 표시에 '실패 N계정 확인 필요'를 넣는 데 쓴다(2026-10-12)."""
        last_fail: dict[str, tuple[int, str]] = {}
        last_ok: dict[str, int] = {}
        for i, r in enumerate(self.rows):
            if r["결과"] in (FAIL, BLOCK):
                last_fail[r["계정"]] = (i, r["단계"])
            elif r["결과"] == OK:
                last_ok[r["계정"]] = i
        return {a: step for a, (i, step) in last_fail.items() if last_ok.get(a, -1) < i}

    def summary(self, *, pending: int = 0, stopped: bool = False, note: str = "") -> list[str]:
        """계정별·결과별 건수 + 단계별 비정상 건수 + [실행 결과 종합](D-168) — 끝에 출력·로그에도 남김."""
        by_acct: dict = {}
        for r in self.rows:
            by_acct.setdefault(r["계정"], Counter())[r["결과"]] += 1
        lines = [f"[요약] {a}: " + " · ".join(f"{k} {v}" for k, v in sorted(c.items())) for a, c in by_acct.items()]
        bad = Counter((r["단계"], r["결과"]) for r in self.rows if r["결과"] in (FAIL, BLOCK))
        lines += [f"[비정상] {s} {res}: {n}건" for (s, res), n in sorted(bad.items())] or ["[비정상] 없음"]
        lines += result_block(self, pending=pending, stopped=stopped, note=note)
        for ln in lines:
            self.line(ln)
        return lines


ALL = "(전체)"
PW_HINT = "관리대장(정산은 원장) 비밀번호 확인 — 거부된 값은 고칠 때까지 다시 넣지 않음"


class Totals:
    """여러 바퀴(RunLog)를 합친 회차 결과 — result_block 재료(rows·files·left·accounts)."""

    def __init__(self):
        self.rows: list[dict] = []
        self.files: list[tuple[str, str, str]] = []
        self.left: dict = {}
        self.accounts: list[str] = []
        self.passes = 0

    def add(self, lg: RunLog) -> None:
        self.rows += lg.rows
        self.files += lg.files
        self.left.update(lg.left)
        self.accounts += [a for a in lg.accounts if a not in self.accounts]
        self.passes += 1


def _key(r: dict) -> tuple:
    return r["계정"], r["단계"], r["채널"], r["유형"], r["정산일"], r["기간"]


def open_failures(rows: list[dict]) -> list[dict]:
    """실패·차단 줄 중 **풀리지 않은 것** — 같은 일(계정·단계·채널·유형·정산일·기간)이 뒤에 정상으로 끝나면 풀림.
    '(전체)' 중단·예외는 뒤에 어떤 정상 줄이든 생기면(다음 바퀴가 다시 돎) 풀림. 계정 단위 실패('계정'·'차단감지')는 짝이 되는
    정상 줄이 없어 풀리지 않음 — 같은 바퀴 소급 단계의 정상 줄이 정기 단계 실패를 가리지 않게(오류 정의)."""
    out: dict = {}
    for r in rows:
        if r["결과"] in (FAIL, BLOCK):
            out[_key(r)] = r
        elif r["결과"] == OK:
            out = {k: v for k, v in out.items() if k != _key(r) and k[0] != ALL}
    return list(out.values())


def _last_login(rows: list[dict]) -> dict[str, dict]:
    last: dict = {}
    for r in rows:
        if r["단계"] == "로그인":
            last[r["계정"]] = r
    return last


def login_problems(rows: list[dict]) -> tuple[list[str], dict[str, str]]:
    """(비밀번호 오류 계정, {사람 조치 필요 계정: 사유}) — 계정마다 **마지막 로그인 줄** 기준(뒤에 성공하면 빠짐)."""
    pw, human = [], {}
    for acct, r in _last_login(rows).items():
        if r["결과"] not in (FAIL, BLOCK):
            continue
        if "비밀번호 오류" in r["사유"]:
            pw.append(acct)
        else:
            human[acct] = r["사유"][:120]
    return pw, human


def verdict(rows: list[dict], stopped: bool = False) -> str:
    """판정 = '원인 --> 결과'(소유자 11-08 — 결과만 쓰지 말고 원인까지). 진전 없음 --> 중단(stopped = watch 가 진전 없이 끝남)
    > 연속 실패 --> 중단('(전체)' 중단이 안 풀림) > 일부 실패 --> 확인 필요(안 풀린 실패·'확인 필요' 대기) > 정상 완료."""
    fails = open_failures(rows)
    if stopped:
        return "진전 없음 --> 중단"
    if any(r["계정"] == ALL for r in fails):
        return "연속 실패 --> 중단"
    if fails or any(r["결과"] == WAIT and "확인 필요" in r["사유"] for r in rows):
        return "일부 실패 --> 확인 필요"
    return "정상 완료"


def _grouped(rows: list[dict]) -> list[str]:
    by: dict = {}
    for r in rows:
        by.setdefault((r["단계"], r["결과"]), []).append(r["계정"])
    return [f"  - {s} {res} {len(a)}건: {', '.join(dict.fromkeys(a))}" for (s, res), a in sorted(by.items())]


def _left_text(left: dict, pending: int) -> str:
    tot: dict = {}
    for (acct, kind), (n, unit) in left.items():
        if n > 0:
            t = tot.setdefault((kind, unit), [0, 0])
            t[0] += n
            t[1] += 1
    parts = [f"{k} {n}{u}({c}계정)" for (k, u), (n, c) in tot.items()]
    if pending:
        parts.append(f"쿠팡 파일 생성·요청 대기 {pending}건")
    if parts:
        return " · ".join(parts)
    return "없음" if left else "확인 못 함(소급 단계를 돌지 않음)"


def result_block(src, *, pending: int = 0, stopped: bool = False, note: str = "", title: str = "실행 결과 종합") -> list[str]:
    """[실행 결과 종합](D-168) 줄들 — src = RunLog 또는 Totals(rows·files·left·accounts). 로그만 보고 정상 수행 여부를 판단하게:
    판정 · 전체 작업 계정 · 비밀번호 오류 계정 · 사람 조치 필요 · 오류 현황 · 대기·확인 필요 · 남은 소급 · 받은 파일 전부(경로).
    마지막 줄 = 한 줄 요약(상태 카드·화면 끝 몇 줄만 보는 사람용). 비밀번호 값은 다루지 않음(계정 이름·사유만)."""
    rows = src.rows
    accts = list(src.accounts) or list(dict.fromkeys(r["계정"] for r in rows if r["계정"] != ALL))
    judge = verdict(rows, stopped)
    pw, human = login_problems(rows)
    fails = open_failures(rows)
    waits = [r for r in rows if r["결과"] == WAIT]
    left = _left_text(src.left, pending)
    out = [f"===== [{title}] =====", f"판정: {judge}" + (f" — {note}" if note else ""),
           f"전체 작업 계정: {len(accts)}개" + (f" — {', '.join(accts)}" if accts else ""),
           f"비밀번호 오류로 수집 안 된 계정: {len(pw)}개" + (f" — {', '.join(pw)} ({PW_HINT})" if pw else ""),
           f"사람 조치 필요: {len(human)}개", *[f"  - {a}: {why}" for a, why in human.items()],
           f"오류 현황(실패·차단, 뒤에 풀린 것 제외): {len(fails)}건", *_grouped(fails),
           f"대기·확인 필요(다음 바퀴·다음 회차에 다시): {len(waits)}건", *_grouped(waits),
           f"남은 소급: {left}",
           f"이번 실행에서 받은 파일: {len(src.files)}개",
           *[f"  - {a}: {p}" + (f" ({m})" if m else "") for a, p, m in src.files],
           f"==> {judge} · 계정 {len(accts)} · 비밀번호 오류 {len(pw)} · 사람 조치 {len(human)} · 오류 {len(fails)} · "
           f"받은 파일 {len(src.files)} · 남은 소급 {left}"]
    return out
