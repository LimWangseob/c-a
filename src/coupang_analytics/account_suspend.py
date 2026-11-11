"""계정 정지(승인 반려) 감지 → 관리대장 계정아이디 칸 취소선 표기(가역) — 소유자 2026-11-11.

매일 18시 실행에서 로그인 성공 직후 `browser.Browser.is_suspended()` 로 정지(승인 반려) 계정을 감지한다
(정지 계정은 윙 홈이 온보딩 화면·메뉴가 /unapproved/ 로 라우팅 — hide4u 실측). 정지면:
- 그 계정 수집을 건너뛰고(다음 계정) 여기 상태 파일에 기록한다.
- 실행 끝에 관리대장 계정아이디 칸에 **취소선**을 쳐 '정지'로 표기 → 다음 회차부터 input_list 가 그 계정을
  제외(불필요한 로그인·받기·광고 500 없음).

가역(원복): **앱이 친 취소선만** 이 상태 파일에 남긴다. 매 회차 그 계정들을 로그인만 해서 재확인하고,
정상으로 바뀌면 취소선을 지우고 기록에서 뺀다 → 다음 회차 다시 수집 대상. 사람이 친 해지-취소선
(상태 파일에 없음)은 건드리지 않는다.

파일 = `output/_계정정지.json` {계정ID: {업체코드, struck_at, last_seen, applied}}.
`applied` = 취소선을 이미 관리대장에 썼는지(중복 쓰기·중복 백업 방지). 되쓰기는 shopmine_sync 와 같은
안전장치: 변경이 있을 때만, **구글시트 탭 복제 백업을 먼저** 한 뒤 쓴다(로컬 백업 금지 — 평문 비번).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

FILE_NAME = "_계정정지.json"
DEFAULT_DIR = "output"


def _path(out_dir) -> Path:
    return Path(out_dir or DEFAULT_DIR) / FILE_NAME


def _load(out_dir=None) -> dict:
    p = _path(out_dir)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(out_dir, data: dict) -> None:
    p = _path(out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _stamp(now: datetime | None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")


def mark_suspended(account_id: str, vendor_code: str = "", *, out_dir=None, now: datetime | None = None) -> None:
    """정지 감지 → 상태 파일 기록. 재감지면 last_seen 만 갱신(취소선 실제 표기는 apply_strikes 가 현재 대장
    취소선 상태를 보고 멱등 적용 — 이 파일에 있는데 아직 안 struck 이면 친다)."""
    if not account_id:
        return
    data = _load(out_dir)
    cur = data.get(account_id) or {}
    data[account_id] = {
        "업체코드": vendor_code or cur.get("업체코드", ""),
        "struck_at": cur.get("struck_at") or _stamp(now),
        "last_seen": _stamp(now),
    }
    _save(out_dir, data)


def clear_suspended(account_id: str, *, out_dir=None) -> None:
    """정상 전환(또는 수동 원복) → 상태 파일에서 제거."""
    data = _load(out_dir)
    if account_id in data:
        del data[account_id]
        _save(out_dir, data)


def suspended_ids(out_dir=None) -> set[str]:
    """앱이 정지로 판정해 둔 계정ID 집합(재확인 패스 대상)."""
    return set(_load(out_dir).keys())


def struck_accounts(rows: list, strike_grid: list) -> set[str]:
    """현재 관리대장에서 **계정아이디 칸이 (그 계정 모든 행) 취소선인** 계정ID 집합.

    strike_grid = read_ledger_rows 가 준 취소선 격자(행 인덱스 = rows 와 정렬·1행부터). 없으면 빈 집합.
    '모든 행' 기준 = 이 기능이 계정 모든 행에 치므로, 전 행이 struck 일 때만 struck 으로 본다(부분은 미완 표기)."""
    from . import input_list
    col = input_list.account_id_column(rows)
    if col is None or not strike_grid:
        return set()

    def _struck(r: int) -> bool:   # r = 1-based 시트 행
        row = strike_grid[r - 1] if 0 <= r - 1 < len(strike_grid) else []
        return bool(row[col]) if col < len(row) else False

    return {aid for aid, rs in input_list.account_id_rows(rows).items() if rs and all(_struck(r) for r in rs)}


def apply_strikes(client, sheet: str, rows: list, *, struck_now=frozenset(), unstrike=frozenset(),
                  out_dir=None, log=lambda *a: None, dry_run: bool = False) -> dict:
    """상태 파일 기준으로 관리대장 취소선을 **멱등** 적용(실행 때 1회).

    - 상태 파일에 있고 **현재 대장에 아직 안 struck**(`struck_now` 에 없음)인 계정 → 계정아이디 **모든 행** 취소선 ON
      (사람이 떼면 struck_now 에서 빠져 자동 재표기). 이미 struck 이면 다시 안 씀(멱등).
    - `unstrike`(이번에 정상 전환으로 원복할 계정) 중 현재 struck 인 것 → 취소선 OFF + 상태 파일에서 제거.
    변경이 있을 때만 **백업(구글시트 탭 복제) 먼저** 하고 쓴다. dry_run 이면 쓰지 않고 계획만 반환.
    client 는 GSheetClient 호환(duplicate_sheet·set_strike). rows = 관리대장 값 격자 · struck_now = struck_accounts().
    """
    from . import input_list
    col = input_list.account_id_column(rows)
    if col is None:
        return {"skipped": "no_id_col"}
    acc_rows = input_list.account_id_rows(rows)
    data = _load(out_dir)
    plan_strike = {aid: acc_rows[aid] for aid in data
                   if aid not in struck_now and acc_rows.get(aid)}
    plan_unstrike = {aid: acc_rows[aid] for aid in unstrike
                     if aid in struck_now and acc_rows.get(aid)}
    result = {"strike": {k: len(v) for k, v in plan_strike.items()},
              "unstrike": {k: len(v) for k, v in plan_unstrike.items()}, "col": col}
    if dry_run or not (plan_strike or plan_unstrike):
        return result

    name = f"백업_계정정지_{datetime.now():%Y%m%d_%H%M%S}"
    client.duplicate_sheet(sheet, name)
    log(f"[계정정지] 되쓰기 전 관리대장 백업 → {name}")

    for aid, rs in plan_strike.items():
        client.set_strike(sheet, col, rs, True)
        log(f"[계정정지] '{aid}' 계정아이디 취소선 설정({len(rs)}행) — 정지 표기")
    for aid, rs in plan_unstrike.items():
        client.set_strike(sheet, col, rs, False)
        data.pop(aid, None)
        log(f"[계정정지] '{aid}' 취소선 해제({len(rs)}행) — 정상화 원복")
    _save(out_dir, data)
    return result
