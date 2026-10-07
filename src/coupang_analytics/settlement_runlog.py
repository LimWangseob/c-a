"""정산 다운로드 실행 기록 — 정상/비정상 분석용(소유자 요구 2026-10-06).

한 번 실행마다 output/정산/로그/ 아래에:
- `실행_{실행ID}.log`   : 화면에 찍히는 모든 줄(타임스탬프 포함) — 흐름 추적.
- `처리기록_{실행ID}.csv`: 계정·단계·채널·유형·**정산일**·기간·결과·사유 한 줄씩 — 날짜별 정상/비정상 분석(엑셀로 열림).
  같은 줄을 `처리기록_누적.csv` 에도 덧붙인다(실행을 넘어 비교).
- `오류_{실행ID}.log`   : 예외 전체 추적(traceback) — 원인 분석.
결과 값: 정상 · 건너뜀 · 대기 · 실패 · 차단. 로그인은 단계='로그인'(결과에 판정 코드), 차단 감지는 결과='차단'.
비밀번호·구매자명 등 개인정보는 남기지 않는다(호출부가 넘기지 않음·사유 글자도 200자로 자름).
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

    def summary(self) -> list[str]:
        """계정별·결과별 건수 + 단계별 비정상 건수(끝에 출력·로그에도 남김)."""
        by_acct: dict = {}
        for r in self.rows:
            by_acct.setdefault(r["계정"], Counter())[r["결과"]] += 1
        lines = [f"[요약] {a}: " + " · ".join(f"{k} {v}" for k, v in sorted(c.items())) for a, c in by_acct.items()]
        bad = Counter((r["단계"], r["결과"]) for r in self.rows if r["결과"] in (FAIL, BLOCK))
        lines += [f"[비정상] {s} {res}: {n}건" for (s, res), n in sorted(bad.items())] or ["[비정상] 없음"]
        for ln in lines:
            self.line(ln)
        return lines
