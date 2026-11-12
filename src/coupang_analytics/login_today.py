"""그날 로그인 실패 기록 — D-068(소유자 2026-10-16).

- **비밀번호 오류(쿠팡이 '아이디 또는 비밀번호가 다릅니다' 등으로 거부)** 가 난 비밀번호 값은 **거부 시각부터 24시간
  다시 넣지 않는다** — 앱 재실행·'오늘 처음(다시)'·재부팅 복구·정산 프로그램 모두(같은 `_fresh_login` 경로).
  D-123: 예전엔 달력 날짜 기준이라 자정을 넘는 밤 정산이 다시 넣음(실측 10-26 plan_it 22:32 → 04:33 재제출).
  관리대장(또는 정산 계정 파일)에서 **비밀번호를 고친 값**은 거부된 값이 아니므로 그날 바로 시도한다.
  실측(output(22) 2026-10-16): plan_it 24회·gyi0101 13회 — 실행마다 같은 틀린 값을 다시 제출(계정 잠금 위험).
- 실패 사유(비밀번호 오류·2단계 인증 필요·로그인 차단·로그인 미완료)를 남겨 결과 파일 통합판매현황·실행 요약이
  '왜 못 받았는지'를 보여 준다. 그날 로그인이 되면 사유를 지운다.

파일 = `output/_로그인실패.json` {계정ID: {date, reason, fp_at{지문: 거부 시각}, at}}(옛 기록의 fps 는 at 을 거부 시각으로 읽음). 비밀번호는 저장하지 않고 **이 PC 전용 비밀 키
(credstore·DPAPI)로 만든 HMAC 지문**만 남긴다(output 폴더는 분석용으로 밖에 보내질 수 있음).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

FILE_NAME = "_로그인실패.json"
DEFAULT_DIR = "output"           # 앱·정산 공통 작업 폴더 기준(set_workdir) — 시험은 임시 폴더로 바꿈
KEY_ID = "__login_fp_key__"      # credstore 항목(비밀 키·DPAPI)
BLOCK_HOURS = 24                 # 거부된 값을 다시 넣지 않는 시간(거부 시각부터·D-123)

PW_WRONG = "로그인 비밀번호 오류"
OTP = "2단계 인증 필요"
BLOCKED = "로그인 차단"
UNFINISHED = "로그인 미완료"


def _key() -> bytes:
    """이 PC 전용 지문 키 — 없으면 만들어 credstore 에 암호화 보관."""
    from .credstore import CredStore
    store = CredStore()
    k = store.get_password(KEY_ID)
    if not k:
        k = secrets.token_hex(32)
        store.set_password(KEY_ID, k)
    return k.encode("ascii")


def fingerprint(account_id: str, pw: str) -> str:
    return hmac.new(_key(), f"{account_id}\0{pw}".encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _path(out_dir) -> Path:
    return Path(out_dir or DEFAULT_DIR) / FILE_NAME


def _load(out_dir) -> dict:
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


def _today(today: date | None) -> str:
    return (today or date.today()).isoformat()


def _blocked(cur: dict, now: datetime | None) -> dict[str, str]:
    """거부 뒤 BLOCK_HOURS 가 안 지난 지문 {지문: 거부 시각}. 옛 기록(fps 만)은 기록 시각(at)을 거부 시각으로 본다."""
    at = cur.get("fp_at") or {fp: cur.get("at", "") for fp in cur.get("fps") or []}
    since = (now or datetime.now()) - timedelta(hours=BLOCK_HOURS)
    return {fp: t for fp, t in at.items() if t and datetime.fromisoformat(t) > since}


def record_failure(account_id: str, reason: str, pw: str | None = None, *, out_dir=None,
                   today: date | None = None, now: datetime | None = None) -> None:
    """그날 실패 사유 기록. reason=PW_WRONG 이고 pw 가 있으면 그 값의 지문을 '24시간 다시 넣지 않을 값'에 더함."""
    data = _load(out_dir)
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    cur = data.get(account_id) or {}
    fp_at = _blocked(cur, now)
    if reason == PW_WRONG and pw:
        fp_at.setdefault(fingerprint(account_id, pw), stamp)
    data[account_id] = {"date": _today(today or (now.date() if now else None)), "reason": reason, "fp_at": fp_at,
                        "at": stamp}
    _save(out_dir, data)


def record_success(account_id: str, *, out_dir=None, now: datetime | None = None) -> None:
    """로그인 됨 → 그 계정 실패 사유 지움. 24시간 안에 거부된 값 지문은 남김(대장 줄마다 비번이 달라 둘째 값으로
    들어간 계정도 다시 실행할 때 거부된 첫 값을 또 넣지 않게 — D-012 와 함께)."""
    data = _load(out_dir)
    cur = data.get(account_id)
    if not cur:
        return
    fp_at = _blocked(cur, now)
    if fp_at:
        cur.update(reason="", fp_at=fp_at)
        cur.pop("fps", None)
    else:
        del data[account_id]
    _save(out_dir, data)


def refused_today(account_id: str, pw: str | None, *, out_dir=None, now: datetime | None = None) -> bool:
    """이 비밀번호 값이 최근 24시간 안에 쿠팡에서 거부됐나(그러면 다시 넣지 않음·D-123)."""
    if not pw:
        return False
    return fingerprint(account_id, pw) in _blocked(_load(out_dir).get(account_id) or {}, now)


def reasons_today(*, out_dir=None, today: date | None = None) -> dict[str, str]:
    """{계정ID: 오늘 로그인 실패 사유} — 오늘 기록만."""
    day = _today(today)
    return {aid: v["reason"] for aid, v in _load(out_dir).items() if v.get("date") == day and v.get("reason")}
