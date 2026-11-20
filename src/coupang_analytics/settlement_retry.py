"""정산 받기 오류 = 회차마다 계정·항목별 최대 3번 시도(처음 + 다시 2번) · 그 뒤 더 시도 안 함 · 오류 로그(D-373 · 소유자 2026-11-20).

- 한 번의 시도 = 그 계정의 그 항목을 한 바퀴에 한 번 받으려 한 것(같은 바퀴 안 두 번째 실패는 세지 않음 · 호출 안 15초×2 재시도는
  한 시도 안).
- 셈 = 서버·일시 오류 · 받기 실패 · 파싱 오류 · 접속 차단(Akamai·차단 감지) · 그 밖의 오류. 쿠팡 파일 생성 대기는 오류가 아님(여기 안 옴).
- 예외: 비밀번호 거부 = 지금 방식 그대로(24시간 안 넣음 D-012·D-068·D-123 — 막지 않고 로그만 한 번) · 2차 인증 = 사람 조치
  (처음부터 다시 시도 안 함 · 로그만).
- 횟수 = 회차(그날 00:10)마다 0부터 · 같은 회차 안 재시작(재부팅 복구)은 상태 파일로 이어 셈.
- 오류 로그 한 건 = 시각 · 회차 · 실행ID · 계정 · 시도 항목 · 데이터(받으려던 자료의 날짜·기간) · 시도(n/3) · 결과 · 오류사유
  → `재시도_오류기록.csv`(누적·엑셀로 열림) + 정산 실행 로그 한 줄. 비밀번호·키 같은 비밀 값은 호출부가 넘기지 않음(사유 200자).
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

MAX_TRIES = 3                                   # 처음 1번 + 다시 2번(소유자 '2번까지 다시 시도')
ERROR, BLOCK, HUMAN, PASSWORD = "오류", "접속 차단", "사람 조치", "비밀번호 거부"
RETRY, GIVE_UP, NO_RETRY = "다음 바퀴에 다시 시도", "더 시도 안 함(3번 실패)", "다시 시도 안 함"
FIELDS = ("시각", "회차", "실행ID", "계정", "시도 항목", "데이터", "시도", "결과", "오류사유")
LOG_NAME, STATE_NAME = "재시도_오류기록.csv", "_재시도_상태.json"


class Tries:
    """한 회차의 계정·항목별 시도 횟수. folder = 정산 로그 폴더 · cycle = 회차 시작(ISO) · line = 실행 로그 한 줄 쓰기."""

    def __init__(self, folder, cycle: str, *, line=print):
        self.dir = Path(folder)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.csv, self.state = self.dir / LOG_NAME, self.dir / STATE_NAME
        self.cycle, self.line, self.pass_id = cycle, line, ""
        self.items: dict[str, dict] = {}
        if self.state.exists():                 # 같은 회차 재시작 = 이어 셈 · 다른 회차 = 0부터(④)
            old = json.loads(self.state.read_text(encoding="utf-8"))
            if old.get("회차") == cycle:
                self.items = old.get("항목") or {}

    @staticmethod
    def _key(account: str, item: str, data: str) -> str:
        return f"{account}\t{item}\t{data}"

    def begin_pass(self, pass_id: str) -> None:
        self.pass_id = pass_id

    def why_not(self, account: str, item: str, data: str = "") -> str:
        """다시 시도하면 안 되는 이유('' = 시도해도 됨) — 3번 소진 · 사람 조치(2차 인증) · 이번 바퀴에 이미 실패. 비밀번호 거부는 막지 않음."""
        e = self.items.get(self._key(account, item, data))
        if not e or e["종류"] == PASSWORD:
            return ""
        if e["결과"] == GIVE_UP:
            return f"이번 회차 {e['시도']}번 실패 — 더 시도 안 함(마지막 사유: {e['사유'][:80]})"
        if e["결과"] == NO_RETRY:
            return f"{e['종류']} 필요 — 다시 시도 안 함({e['사유'][:80]})"
        if e["바퀴"] == self.pass_id:
            return "이번 바퀴에 이미 실패 — 다음 바퀴에 다시 시도"
        return ""

    def ended(self, account: str, item: str, data: str = "") -> bool:
        """그 회차에 끝난 항목인가(3번 소진·2차 인증) — 다시 시도할 수 있는 실패·비밀번호 거부는 False(받을 것 수에 그대로 셈)."""
        e = self.items.get(self._key(account, item, data))
        return bool(e) and e["종류"] != PASSWORD and e["결과"] != RETRY

    def cannot_login(self, account: str) -> bool:
        """이번 회차에 그 계정 로그인을 다시 하지 않나(비밀번호 거부·2차 인증·로그인 3번 소진) — 생성 대기 바퀴 대상에서 뺌."""
        e = self.items.get(self._key(account, "로그인", ""))
        return bool(e) and (e["종류"] == PASSWORD or e["결과"] != RETRY)

    def fail(self, account: str, item: str, reason: str, data: str = "", kind: str = ERROR,
             now: datetime | None = None) -> dict | None:
        """실패 1건 — 이번 바퀴 첫 실패면 시도 수 +1·오류 로그 한 건. 이미 끝난 항목(소진·다시 시도 안 함)·같은 바퀴 두 번째 = None."""
        key = self._key(account, item, data)
        e = self.items.get(key)
        if e and (e["결과"] != RETRY or e["바퀴"] == self.pass_id):
            return None
        n = (e["시도"] if e else 0) + 1
        result = NO_RETRY if kind in (HUMAN, PASSWORD) else GIVE_UP if n >= MAX_TRIES else RETRY
        e = {"계정": account, "항목": item, "데이터": data, "시도": n, "결과": result, "종류": kind,
             "사유": str(reason)[:200], "바퀴": self.pass_id, "시각": f"{now or datetime.now():%Y-%m-%d %H:%M:%S}"}
        self.items[key] = e
        self._save()
        self._write(e)
        return e

    def ok(self, account: str, item: str, data: str = "") -> None:
        """성공 = 그 항목 기록 지움(뒤에 다시 실패하면 새로 셈)."""
        if self.items.pop(self._key(account, item, data), None) is not None:
            self._save()

    def retry_now(self) -> int:
        """이번 바퀴에 실패했고 아직 다시 시도할 수 있는 항목 수 — 0 보다 크면 회차를 끝내지 않음(다음 바퀴)."""
        return sum(1 for e in self.items.values() if e["결과"] == RETRY and e["바퀴"] == self.pass_id)

    def given_up(self) -> dict[str, str]:
        """이번 회차에 실패로 끝난 계정 {계정: 항목}(3번 소진·사람 조치·비밀번호 거부 — 마지막 바퀴가 대기 바퀴라 그 계정이 안
        들어가도 끝 상태 '완료·실패 확인'에 남게 · 로그인 성공하면 ok 로 빠짐)."""
        out: dict[str, str] = {}
        for e in self.items.values():
            if e["결과"] in (GIVE_UP, NO_RETRY):
                out.setdefault(e["계정"], e["항목"])
        return out

    def summary_lines(self) -> list[str]:
        """[실행 결과 종합]에 넣을 줄 — 더 시도 안 한 항목 전부(계정·항목·데이터·시도·사유) · 없으면 줄 없음."""
        ended = [e for e in self.items.values() if e["결과"] != RETRY]
        if not ended:
            return []
        return [f"오류로 더 시도 안 한 항목(D-373 · 기록 {self.csv.name}): {len(ended)}건",
                *[f"  - {e['계정']} · {e['항목']}" + (f" · {e['데이터']}" if e["데이터"] else "")
                  + f" · {e['시도']}/{MAX_TRIES} · {e['결과']} · {e['사유'][:120]}" for e in ended]]

    def _save(self) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self.dir), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"회차": self.cycle, "항목": self.items}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.state)

    def _write(self, e: dict) -> None:
        row = {"시각": e["시각"], "회차": self.cycle, "실행ID": self.pass_id, "계정": e["계정"], "시도 항목": e["항목"],
               "데이터": e["데이터"], "시도": f"{e['시도']}/{MAX_TRIES}", "결과": e["결과"], "오류사유": e["사유"]}
        new = not self.csv.exists()
        with self.csv.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
        mark = "↻" if e["결과"] == RETRY else "⛔"
        self.line(f"  {mark} [오류 {e['시도']}/{MAX_TRIES}] {e['계정']} · {e['항목']}"
                  + (f" · {e['데이터']}" if e["데이터"] else "") + f" → {e['결과']} ({e['종류']}: {e['사유']})")
