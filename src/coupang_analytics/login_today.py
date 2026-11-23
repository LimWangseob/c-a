"""그날 로그인 실패 기록 — D-068(소유자 2026-10-16).

- **비밀번호 오류(쿠팡이 '아이디 또는 비밀번호가 다릅니다' 등으로 거부)** 가 난 비밀번호 값은 **거부 시각부터 24시간
  다시 넣지 않는다** — 앱 재실행·'오늘 처음(다시)'·재부팅 복구·정산 프로그램 모두(같은 `_fresh_login` 경로).
  D-123: 예전엔 달력 날짜 기준이라 자정을 넘는 밤 정산이 다시 넣음(실측 10-26 plan_it 22:32 → 04:33 재제출).
  관리대장(또는 정산 계정 파일)에서 **비밀번호를 고친 값**은 거부된 값이 아니므로 그날 바로 시도한다.
  실측(output(22) 2026-10-16): plan_it 24회·gyi0101 13회 — 실행마다 같은 틀린 값을 다시 제출(계정 잠금 위험).
- 실패 사유(비밀번호 오류·2단계 인증 필요·로그인 차단·로그인 미완료)를 남겨 결과 파일 통합판매현황·실행 요약이
  '왜 못 받았는지'를 보여 준다. 그날 로그인이 되면 사유를 지운다.

- T-160(소유자 2026-11-23 '1~6 전부 수용'): 자동입력으로 **로그인에 성공한 값의 지문**(ok_fp·ok_at)을 남겨, 다음 로그인 때
  지금 대장 후보 중 그 지문과 같은 값을 맨 앞에 넣는다(`success_first`). 대장에서 그 값이 사라지면 기억은 쓰지 않는다(대장
  현재 값만 넣음 D-012). 실측: dalbong1849·wavetech = 대장 1줄짜리 옛 값이 '적은 줄 먼저' 규칙으로 1번째 → 24시간마다 거부.

파일 = `output/_로그인실패.json` {계정ID: {date, reason, fp_at{지문: 거부 시각}, at, ok_fp, ok_at}}(옛 기록의 fps 는 at 을 거부
시각으로 읽음). 비밀번호는 저장하지 않고 **이 PC 전용 비밀 키(credstore·DPAPI)로 만든 HMAC 지문**만 남긴다(output 폴더는
분석용으로 밖에 보내질 수 있음).
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
    out = {fp: t for fp, t in at.items() if t and datetime.fromisoformat(t) > since}
    ok_fp, ok_at = cur.get("ok_fp"), cur.get("ok_at")
    if ok_fp in out and ok_at and datetime.fromisoformat(ok_at) >= datetime.fromisoformat(out[ok_fp]):
        del out[ok_fp]   # 같은 값이 거부 뒤에 로그인 성공 = 그 거부는 지난 일(성공이 최신 · T-160)
    return out


def _ok(cur: dict) -> dict:
    """그 계정의 성공 값 기억(지문·시각) — 없으면 빈 dict."""
    return {k: cur[k] for k in ("ok_fp", "ok_at") if cur.get(k)}


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
                        "at": stamp, **_ok(cur)}
    _save(out_dir, data)


def record_success(account_id: str, pw: str | None = None, *, out_dir=None, now: datetime | None = None) -> None:
    """로그인 됨 → 그 계정 실패 사유 지움. 24시간 안에 거부된 값 지문은 남김(대장 줄마다 비번이 달라 둘째 값으로
    들어간 계정도 다시 실행할 때 거부된 첫 값을 또 넣지 않게 — D-012 와 함께).
    pw = 자동입력으로 넣어 성공한 값(세션 재사용이면 None) → 그 지문을 '성공 값'으로 기억(T-160 · 평문 저장 안 함)."""
    data = _load(out_dir)
    cur = data.get(account_id)
    if not cur and not pw:
        return
    cur = cur or {}
    fp_at = _blocked(cur, now)
    ok = _ok(cur)
    if pw:
        fp = fingerprint(account_id, pw)
        fp_at.pop(fp, None)
        ok = {"ok_fp": fp, "ok_at": (now or datetime.now()).isoformat(timespec="seconds")}
    if fp_at or ok:
        cur.update(reason="", fp_at=fp_at, **ok)
        cur.pop("fps", None)
        data[account_id] = cur
    else:
        del data[account_id]
    _save(out_dir, data)


def success_first(account_id: str, pws: list, *, out_dir=None, now: datetime | None = None) -> tuple[list, int | None]:
    """후보 순서 — 지난번 로그인에 성공한 값(지문)이 **지금 후보에 있으면 맨 앞으로**, 나머지 순서는 그대로(T-160).
    성공 기억이 없거나 · 그 값이 후보에 없거나(대장에서 사라짐 — 기억 무시 D-012) · 성공 뒤에 다시 거부됐으면 그대로.
    반환 = (새 순서, 앞으로 옮긴 값의 원래 위치 0부터 | None)."""
    pws = list(pws)
    if len(pws) < 2:
        return pws, None
    cur = _load(out_dir).get(account_id) or {}
    ok_fp = cur.get("ok_fp")
    if not ok_fp or ok_fp in _blocked(cur, now):
        return pws, None
    for k, pw in enumerate(pws):
        if pw and fingerprint(account_id, pw) == ok_fp:
            return ([pw] + pws[:k] + pws[k + 1:], k) if k else (pws, None)
    return pws, None


def refused_today(account_id: str, pw: str | None, *, out_dir=None, now: datetime | None = None) -> bool:
    """이 비밀번호 값이 최근 24시간 안에 쿠팡에서 거부됐나(그러면 다시 넣지 않음·D-123)."""
    if not pw:
        return False
    blocked = _blocked(_load(out_dir).get(account_id) or {}, now)
    return bool(blocked) and fingerprint(account_id, pw) in blocked


def reasons_today(*, out_dir=None, today: date | None = None) -> dict[str, str]:
    """{계정ID: 오늘 로그인 실패 사유} — 오늘 기록만."""
    day = _today(today)
    return {aid: v["reason"] for aid, v in _load(out_dir).items() if v.get("date") == day and v.get("reason")}
