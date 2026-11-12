"""앱 [실행 결과 종합](D-168 앱 쪽 · D-172 판정 '원인 --> 결과') — ①②③·재고 역기록 실행 끝 블록.

로그 끝만 보고 정상 수행 여부를 판단하게 한다. `run_stages` 가 `RunSummary` 로 감싸 단계 로그를 받고(오류 줄 모음),
실행 끝(예외·중지 포함)에 블록을 찍는다. 재료:
- ① = `LAST_SALES`(pipeline.run_full 이 채움 — 계정·비밀번호 오류·로그인 못 한 계정과 사유·수집 성공 수·저장 파일)
- ③ = `LAST_RANK`(pipeline_ranks — 측정·빈 칸·VID 없음·차단) · 오류 = 단계별 '❌' 줄(②·재고 역기록은 '실패' 줄도)
판정: 오류 발생 --> 중단 · 사람 중지 --> 중단 · 일부 실패[·순위 빈 칸] --> 확인 필요 · 정상 완료.
비밀번호 값은 다루지 않음(계정 이름·사유만).
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from .login_today import OTP

LAST_SALES: dict = {}   # ① 끝 정보 — run_stages 시작 때 비우고 pipeline.run_full 이 채움
SALES, KEYWORDS, RANKS, STOCK, PREP = "① 판매수집", "② 키워드 선정", "③ 순위", "재고 역기록", "준비"
PW_HINT = "관리대장 비밀번호 확인 — 거부된 값은 24시간 다시 넣지 않음"
MAX_LINES = 20          # 단계마다 오류 줄 표시 상한(넘으면 '외 N건')
TITLE = "===== [실행 결과 종합] ====="


def is_error(stage: str, msg: str) -> bool:
    """오류 줄 — '❌' 는 모든 단계. ②·재고 역기록은 재시도가 없어 '실패' 줄도 오류(①③은 도중 '실패'가 뒤에 풀림)."""
    return "❌" in msg or (stage in (KEYWORDS, STOCK) and "실패" in msg)


def verdict(*, crashed: str, stopped: bool, failed: bool, unfilled: int) -> str:
    """판정 = '원인 --> 결과'(D-172) — 결과만 쓰지 않는다."""
    if crashed:
        return "오류 발생 --> 중단"
    if stopped:
        return "사람 중지 --> 중단"
    causes = [c for c, on in (("일부 실패", failed), ("순위 빈 칸", unfilled > 0)) if on]
    return f"{'·'.join(causes)} --> 확인 필요" if causes else "정상 완료"


def _where(p) -> str:
    s = str(p)
    return s if s.startswith("http") else str(Path(s).resolve())   # 드라이브부터 전체 경로


class RunSummary:
    """run_stages 를 감싸는 로그 탭 + 끝 블록. `with RunSummary(...) as log:` → log(msg) 로 쓰면 원래 로그로도 나감."""

    def __init__(self, on_log, accounts, *, should_stop, rank: dict, sheet_url: str = ""):
        self._log, self.accounts, self._stop, self.rank, self.sheet_url = on_log, list(accounts), should_stop, rank, sheet_url
        self.stage, self.retried = PREP, 0
        self.errors: dict[str, list[str]] = {}
        self.ran: list[str] = []
        self.files: list[tuple[str, object]] = []

    def __call__(self, msg: str) -> None:
        self._log(msg)
        if is_error(self.stage, msg):
            self.errors.setdefault(self.stage, []).append(msg.strip())

    def enter(self, stage: str, *, again: bool = False) -> None:
        """단계 시작. again=다시 시도 — 그 단계 첫 회 오류 줄은 버림(재시도 결과로 판정)."""
        self.stage = stage
        if stage not in self.ran:
            self.ran.append(stage)
        if again:
            self.errors.pop(stage, None)
            self.retried += 1

    def saved(self, what: str, path) -> None:
        if path:
            self.files.append((what, path))

    def __enter__(self) -> RunSummary:
        LAST_SALES.clear()
        return self

    def __exit__(self, et, ev, tb) -> Literal[False]:
        crashed = "" if et is None else f"{et.__name__}: {(str(ev).splitlines() or [''])[0][:200]}"
        for ln in self.block(crashed):
            self._log(ln)
        return False                          # 예외는 그대로 올림

    def _all_files(self) -> list:
        out, seen = [], set()
        sheet = [("결과 구글시트", self.sheet_url)] if self.sheet_url and (SALES in self.ran or RANKS in self.ran) else []
        for what, p in [*LAST_SALES.get("files", []), *self.files, *sheet]:
            w = _where(p)
            if w not in seen:
                seen.add(w)
                out.append((what, w))
        return out

    def _rank_line(self) -> str:
        r = self.rank
        if RANKS not in self.ran:
            return "③ 순위: 이번 실행에서 안 돎"
        if not r:
            self.errors.setdefault(RANKS, []).append("③ 순위 결과 없음(결과 워크북 없음 등 — 위 로그 확인)")
            return "③ 순위: 결과 없음"
        tail = " · 모든 처리 끝난 뒤 빈 칸 1회 재시도함" if self.retried else ""
        n, first = int(r.get("searched") or 0), r.get("first_searched")
        split = f"(첫 회 {first} + 재시도 {n - first})" if self.retried and first is not None else ""
        return (f"③ 순위: 측정 {n}건{split} · 빈 칸 {r.get('unfilled', 0)} · VID 없음 {r.get('novid', 0)} · "
                f"차단감지 {r.get('blocked', 0)}회{tail}")

    def _error_lines(self) -> list[str]:
        out = []
        for stage in (PREP, SALES, KEYWORDS, RANKS, STOCK):
            rows = self.errors.get(stage, [])
            if rows:
                out.append(f"  - {stage} {len(rows)}건:")
                out += [f"      {x}" for x in rows[:MAX_LINES]]
                if len(rows) > MAX_LINES:
                    out.append(f"      … 외 {len(rows) - MAX_LINES}건")
        return out

    def _failed(self, pw, missed, unfilled: int) -> bool:
        """'일부 실패' 원인 — ③ '❌' 줄은 빈 칸이 남았으면 '순위 빈 칸' 원인(칸마다 찍힘)이라 빼고, VID 없음·다른 단계 오류만."""
        other = any(v for k, v in self.errors.items() if k != RANKS)
        rank_err = bool(self.errors.get(RANKS)) and not unfilled
        novid = RANKS in self.ran and bool(self.rank.get("novid"))
        return bool(pw or missed or other or rank_err or novid)

    def _sales_line(self, n_accts: int) -> str:
        s = LAST_SALES
        if SALES not in self.ran:
            return "① 판매수집: 이번 실행에서 안 돎"
        return f"① 판매수집: 수집 성공 {s.get('ok', '?')}/{s.get('total', n_accts)}계정"

    @staticmethod
    def _named(head: str, items: list, hint: str = "") -> str:
        return f"{head}: {len(items)}개" + (f" — {', '.join(items)}" + (f" ({hint})" if hint else "") if items else "")

    def block(self, crashed: str = "") -> list[str]:
        accts = list(LAST_SALES.get("accounts") or self.accounts)
        pw, missed = list(LAST_SALES.get("pw", [])), dict(LAST_SALES.get("missed", {}))
        human = {a: w for a, w in missed.items() if w == OTP}
        lost = {a: w for a, w in missed.items() if w != OTP}
        rank_line = self._rank_line()                         # 결과 없음이면 오류 줄 추가 → nerr 전에
        unfilled = int(self.rank.get("unfilled") or 0) if RANKS in self.ran else 0
        nerr = sum(len(v) for v in self.errors.values())
        judge = verdict(crashed=crashed, stopped=bool(self._stop()), failed=self._failed(pw, missed, unfilled),
                        unfilled=unfilled)
        files = self._all_files()
        return [TITLE, f"판정: {judge}", *([f"오류 내용: {crashed}"] if crashed else []),
                self._named("전체 작업 계정", accts), self._sales_line(len(accts)),
                self._named("비밀번호 오류로 수집 안 된 계정", pw, PW_HINT),
                f"사람 조치 필요: {len(human)}개", *[f"  - {a}: {w}" for a, w in human.items()],
                f"로그인 못 한 계정(다음 실행에서 다시): {len(lost)}개", *[f"  - {a}: {w}" for a, w in lost.items()],
                f"② 키워드 선정: {'함' if KEYWORDS in self.ran else '이번 실행에서 안 돎'}",
                rank_line,
                f"오류 현황('❌' 줄 · ②·재고 역기록은 '실패' 줄 포함): {nerr}건", *self._error_lines(),
                f"이번 실행에서 저장한 파일: {len(files)}개", *[f"  - {w}: {p}" for w, p in files],
                f"==> {judge} · 계정 {len(accts)} · 비밀번호 오류 {len(pw)} · 사람 조치 {len(human)} · "
                f"로그인 못 함 {len(lost)} · 순위 빈 칸 {unfilled} · 오류 {nerr} · 저장 파일 {len(files)}"]


__all__ = ["LAST_SALES", "RunSummary", "is_error", "verdict"]
