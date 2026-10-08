"""정산 로컬 기록 — output/정산/ 아래 요청 기록·받은 파일·쿠팡 지급 내역(금액 JSON)·검증 자료의 위치와 관리.

tools/settlement_download.py 에서 분리(2026-10-08·행동 불변): 경로 상수 · 금액 JSON 키 병합(원자적 저장) ·
예전 계정명 → 지금 계정명 맞춤(계정ID 기준·멱등) · 다른 PC 정산 폴더 합치기 · 지급일 대조용 공휴일 불러오기.
브라우저·쿠팡 호출 없음. 경로는 상대경로(앱 데이터 폴더로 chdir 한 뒤 사용 — apppaths.set_workdir).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from coupang_analytics import settlement_accounts as SA
from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_jobs as SJ

BASE = Path("output") / "정산"
JOBS = BASE / "_요청기록.json"
FILES = BASE / "파일"
COSTS = FILES / "비용"                                   # 로켓그로스 비용 리포트(집계 파일 목록과 분리)
AMOUNTS = BASE / "쿠팡지급내역"                           # 정산현황 금액(계정별 JSON) — 집계 대조용
VERIFY = BASE / "검증자료"                                # 월렛·매출내역·부가세·보류·추가지급(계정별 JSON·하루 1회)


def _amount_key(r: dict) -> tuple:
    return r["정산일"], r["기간 시작"], r["기간 끝"], r["지급비율"]


def write_json_atomic(path: Path, data, indent: int | None = None) -> None:
    """임시 파일에 쓰고 바꿔 끼움(중간에 끊겨도 반쯤 쓴 파일이 남지 않음)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _write_amounts(path: Path, rows: dict) -> None:
    write_json_atomic(path, sorted(rows.values(), key=lambda r: (r["정산일"], r["기간 시작"])), indent=1)


def merge_amount_file(src: Path, dst: Path) -> None:
    """금액 기록 JSON 을 dst 로 옮김. dst 가 이미 있으면 (정산일·기간·비율) 키로 합침(dst 값 우선) 후 src 삭제."""
    if not dst.exists():
        os.replace(src, dst)
        return
    rows = {_amount_key(r): r for r in json.loads(src.read_text(encoding="utf-8"))}
    rows.update({_amount_key(r): r for r in json.loads(dst.read_text(encoding="utf-8"))})
    _write_amounts(dst, rows)
    src.unlink()


def save_amounts(name: str, ch: str, new_rows: list) -> None:
    """쿠팡 정산현황 금액(amount_rows 결과)을 계정·채널별 JSON 에 (정산일·기간·비율) 키로 덮어 모아 둔다(원자적 저장)."""
    path = AMOUNTS / f"{SF._token(name, '계정명')}_{ch}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    merged = {_amount_key(r): r for r in old}
    merged.update({_amount_key(r): r for r in new_rows})
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_amounts(path, merged)


def rename_jobs(jobs, accts, file_accounts=()) -> tuple[dict, dict]:
    """요청 기록 안의 예전 계정명·파일 이름 → 지금 이름(제자리). 반환 (계정명 바꿈표, 파일 계정명 바꿈표)."""
    m = SA.renames([j.account for j in jobs], accts)
    mt = SA.renames([*file_accounts, *[j.file.split("/")[-1].split("_")[0] for j in jobs if j.file]], accts,
                    tok=lambda x: SF._token(x, "계정명"))
    for j in jobs:
        j.account = m.get(j.account, j.account)
        if j.file:
            head, _, rest = j.file.rpartition("/")
            acct, _, tail = rest.partition("_")
            j.file = (head + "/" if head else "") + mt.get(acct, acct) + "_" + tail
    return m, mt


def migrate_names(accts, log) -> None:
    """요청 기록(_요청기록.json)·받은 파일·쿠팡 지급 내역 파일의 예전 계정명 → 지금 계정명(멱등).
    금액 기록 파일 이름의 계정명도 바꿈표에 넣는다 — 합치기로 옮겨 온 금액 기록만 예전 이름일 때(파일·요청 기록은
    이미 새 이름) 바꿈표가 비어 계정이 둘로 갈리던 결함(2026-10-08 재현·수정)."""
    jobs = SJ.load_jobs(JOBS)
    names = [SF.parse_file_name(p.name)["account"] for d in (FILES, COSTS) for p in d.glob("*.xlsx")]
    names += [p.stem.rpartition("_")[0] for p in AMOUNTS.glob("*.json")]
    m, mt = rename_jobs(jobs, accts, names)
    if m or mt:
        SJ.save_jobs(JOBS, jobs)
    for d in (FILES, COSTS):
        for p in list(d.glob("*.xlsx")):
            acct, _, tail = p.name.partition("_")
            if acct in mt:
                os.replace(p, p.with_name(mt[acct] + "_" + tail))
    for p in list(AMOUNTS.glob("*.json")):
        acct, _, ch = p.stem.rpartition("_")
        if acct in mt:
            merge_amount_file(p, p.with_name(f"{mt[acct]}_{ch}.json"))
    if m or mt:
        log(f"  [계정명 맞춤] 요청 기록 {len(m)}개·파일 계정명 {len(mt)}개를 지금 계정 파일 이름으로 바꿈")


def merge_folder(src: Path, accts) -> tuple[int, int, int, int]:
    """다른 PC 정산 폴더(src)를 이 PC 기록에 합침 — 요청 기록=같은 작업은 이 PC 우선·나머지 추가 / 받은 파일=같은
    이름 있으면 그대로 둠(원본 폴더에 남음) / 금액 기록=키로 합침. 반환 (요청 추가, 요청 중복, 파일 옮김, 파일 그대로)."""
    jobs, extra = SJ.load_jobs(JOBS), SJ.load_jobs(src / "_요청기록.json")
    rename_jobs(extra, accts)                               # 옮겨 온 기록도 같은 이름 규칙 → 같은 작업은 한 번만
    added, dup = SJ.merge_jobs(jobs, extra)
    SJ.save_jobs(JOBS, jobs)
    moved = kept = 0
    for sub, dst in (("파일", FILES), ("파일/비용", COSTS)):
        dst.mkdir(parents=True, exist_ok=True)
        srcs = sorted((src / sub).glob("*.xlsx"))
        mt = SA.renames([p.name.partition("_")[0] for p in srcs], accts, tok=lambda x: SF._token(x, "계정명"))
        for p in srcs:
            acct, _, tail = p.name.partition("_")
            target = dst / f"{mt.get(acct, acct)}_{tail}"         # 지금 이름 기준으로 같은 파일 있는지
            if target.exists():
                kept += 1
            else:
                os.replace(p, target)
                moved += 1
    AMOUNTS.mkdir(parents=True, exist_ok=True)
    for p in sorted((src / "쿠팡지급내역").glob("*.json")):
        merge_amount_file(p, AMOUNTS / p.name)
    return added, dup, moved, kept


def load_holidays(amounts: list, log):
    """지급일 대조용 공휴일(정산일이 걸친 해 전부). 해마다 캐시(output/_holidays_YYYY.json) → 없으면 특일정보 API(키=credstore)
    → 둘 다 없으면 None(지급일 대조만 '자료 없음'·집계는 계속). 실패 사유는 로그에 남김(무음 아님)."""
    from coupang_analytics import holiday_kr as HK
    from coupang_analytics import holiday_source as HS
    years = sorted({int(r["정산일"][:4]) for r in amounts if r.get("정산일")})
    if not years:
        return None
    try:
        fetch = HS.fetch_from_store()
    except HS.HolidayApiError as exc:
        fetch, why = None, str(exc)
    else:
        why = ""
    try:
        return set().union(*(HK.holidays(y, fetch=fetch) for y in years))
    except HK.HolidaySourceError as exc:
        log(f"  [공휴일] 지급일 대조 건너뜀 — {exc}" + (f" ({why})" if why else ""))
        return None
