"""정산 로컬 기록 — output/정산/ 아래 요청 기록·받은 파일·쿠팡 지급 내역(금액 JSON)·검증 자료의 위치와 관리.

tools/settlement_download.py 에서 분리(2026-10-08·행동 불변): 경로 상수 · 금액 JSON 키 병합(원자적 저장) ·
예전 계정명 → 지금 계정명 맞춤(계정ID 기준·멱등) · 다른 PC 정산 폴더 합치기 · 지급일 대조용 공휴일 불러오기.
브라우저·쿠팡 호출 없음. 경로는 상대경로(앱 데이터 폴더로 chdir 한 뒤 사용 — apppaths.set_workdir).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
from pathlib import Path

from coupang_analytics import daily_snapshot as DS
from coupang_analytics import settlement_accounts as SA
from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_jobs as SJ

BASE = Path("output") / "정산"
JOBS = BASE / "_요청기록.json"
FILES = BASE / "파일"
COSTS = FILES / "비용"                                   # 로켓그로스 비용 리포트(집계 파일 목록과 분리)
AMOUNTS = BASE / "쿠팡지급내역"                           # 정산현황 금액(계정별 JSON) — 집계 대조용
FORECAST = BASE / "정산예정기록.jsonl"                     # 앞으로의 정산 줄(수집일별·D-078) — 지급 내역과 분리
VERIFY = BASE / "검증자료"                                # 월렛·매출내역·부가세·보류·추가지급(계정별 JSON·하루 1회)
RG_RAW_DIRNAME = "정산현황_원문"                           # BASE/정산현황_원문/{계정}/{날짜}.json.gz (D-164 원인 확인용)
RENAMED_KEEP = ("보관", "계정명바뀜")                       # BASE/보관/계정명바뀜/{옛 이름}/ — 이름 맞춤 때 겹친 옛 파일(삭제 없음 · T-46 ⑥)


def use_base(base: Path) -> None:
    """이 실행의 정산 기록 위치를 바꿈(셀독전환자 정산 자료 = output/정산_셀독전환/정산 · D-187) — 실행 시작에 한 번만."""
    global BASE, JOBS, FILES, COSTS, AMOUNTS, FORECAST, VERIFY
    BASE = Path(base)
    JOBS, FILES, AMOUNTS = BASE / "_요청기록.json", BASE / "파일", BASE / "쿠팡지급내역"
    COSTS, FORECAST, VERIFY = FILES / "비용", BASE / "정산예정기록.jsonl", BASE / "검증자료"


def _amount_key(r: dict) -> tuple:
    return r["정산일"], r["기간 시작"], r["기간 끝"], r["지급비율"]


def _by_paydate(rows: list) -> dict:
    """정산일 → 그날 줄 묶음. 한 정산일을 조회하면 그날 줄이 전부 오므로 정산일 단위로 바꿔 끼움 — 같은 (정산일·기간·비율)
    줄이 여러 개인 보류 해제 지급(100%)도 전부 보관(실측 2026-10-19 디프 5/12 23줄·5/4 42줄 — 쿠팡 줄 번호 없음, D-085)."""
    out: dict = {}
    for r in rows:
        out.setdefault(r["정산일"], []).append(r)
    return out


def write_json_atomic(path: Path, data, indent: int | None = None) -> None:
    """임시 파일에 쓰고 바꿔 끼움(중간에 끊겨도 반쯤 쓴 파일이 남지 않음)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _write_amounts(path: Path, days: dict) -> None:
    rows = [r for g in days.values() for r in g]
    write_json_atomic(path, sorted(rows, key=lambda r: (r["정산일"], r["기간 시작"])), indent=1)


def merge_amount_file(src: Path, dst: Path) -> None:
    """금액 기록 JSON 을 dst 로 옮김. dst 가 이미 있으면 정산일 단위로 합침(같은 정산일은 dst 줄 묶음 우선) 후 src 삭제."""
    if not dst.exists():
        os.replace(src, dst)
        return
    days = _by_paydate(json.loads(src.read_text(encoding="utf-8")))
    days.update(_by_paydate(json.loads(dst.read_text(encoding="utf-8"))))
    _write_amounts(dst, days)
    src.unlink()


def save_amounts(name: str, ch: str, new_rows: list) -> None:
    """쿠팡 정산현황 금액(amount_rows 결과)을 계정·채널별 JSON 에 정산일 단위로 바꿔 끼워 모아 둔다(원자적 저장)."""
    path = AMOUNTS / f"{SF._token(name, '계정명')}_{ch}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    merged = _by_paydate(old)
    merged.update(_by_paydate(new_rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    DS.keep_before_overwrite(path)                        # 같은 정산일 줄을 쿠팡이 고쳐도 옛 줄 남김(D-335)
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


def _keep_newer_verify(src: Path, dst: Path) -> None:
    """검증 자료 src(예전 이름) → dst(지금 이름). dst 가 있으면 수집일이 더 최근인 쪽만 남김(같으면 dst)."""
    if dst.exists():
        day = lambda p: json.loads(p.read_text(encoding="utf-8")).get("수집일") or ""   # noqa: E731
        if day(src) <= day(dst):
            src.unlink()
            return
    os.replace(src, dst)


def _keep_old(src: Path, old_tok: str, sub: str) -> None:
    """겹친 옛 이름 파일 → BASE/보관/계정명바뀜/{옛 이름}/{sub}/ (지우지 않음 · 같은 이름이 이미 있으면 번호 붙임)."""
    d = BASE.joinpath(*RENAMED_KEEP, old_tok, sub)
    d.mkdir(parents=True, exist_ok=True)
    dst, n = d / src.name, 1
    while dst.exists():
        dst, n = d / f"{src.stem}.{n}{src.suffix}", n + 1
    shutil.move(str(src), str(dst))


def _merge_ledger(src: Path, dst: Path) -> None:
    """월자료 받은 기록 합침 — 종류별 {달: 시각} 은 합집합(같은 달 = 지금 이름 값) · 그 밖 값은 지금 이름 쪽 우선."""
    a, b = json.loads(src.read_text(encoding="utf-8")), json.loads(dst.read_text(encoding="utf-8"))
    out = {**a, **b}
    for k in set(a) & set(b):
        if isinstance(a[k], dict) and isinstance(b[k], dict):
            out[k] = {**a[k], **b[k]}
    write_json_atomic(dst, out, indent=1)


def _merge_ad_state(src: Path, dst: Path) -> None:
    """광고 상태({계정}_광고.json) 합침 — '캠페인 없음' 달은 합집합 · 그 밖 값은 지금 이름 쪽 우선."""
    a, b = json.loads(src.read_text(encoding="utf-8")), json.loads(dst.read_text(encoding="utf-8"))
    out = {**a, **b, "캠페인 없음": sorted(set(a.get("캠페인 없음") or []) | set(b.get("캠페인 없음") or []))}
    write_json_atomic(dst, out)


def _move_or_keep(src: Path, dst: Path, old_tok: str, sub: str, merge=None) -> None:
    """src(옛 이름) → dst(지금 이름). dst 가 없으면 옮김 · 있으면 dst 유지(merge 가 있으면 먼저 합침) + src 는 보관."""
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return
    if merge is not None:
        merge(src, dst)
    _keep_old(src, old_tok, sub)


def _move_folder(src: Path, dst: Path, old_tok: str, sub: str) -> None:
    """계정 폴더(월자료·정산현황 원문) 옛 이름 → 지금 이름 — 파일마다 _move_or_keep(받은 기록은 합침) · 빈 옛 폴더만 치움."""
    for f in sorted(src.iterdir()):
        _move_or_keep(f, dst / f.name, old_tok, sub, _merge_ledger if f.name == "_받은기록.json" else None)
    src.rmdir()


def _migrate_side_data(mt: dict, jobs) -> bool:
    """월자료(검증자료/월자료/{계정}/)·광고(검증자료/광고/{계정}_*)·정산현황 원문(정산현황_원문/{계정}/)의 옛 이름 → 지금 이름 —
    계정 이름이 바뀌어도 받은 달을 이어 씀(T-46 ⑥ · output (37) hide4u '(계정사용불가)' 뒤 폴더 둘 · 처음부터 다시 받음).
    요청형 월자료 작업의 파일 경로('월자료/{계정}/…')도 지금 이름으로. 반환 = 작업 기록을 바꿨나."""
    for old, new in mt.items():
        for base, sub in ((VERIFY / "월자료", "월자료"), (BASE / RG_RAW_DIRNAME, RG_RAW_DIRNAME)):
            if (base / old).is_dir():
                _move_folder(base / old, base / new, old, sub)
        ad = VERIFY / "광고"
        for p in sorted(ad.glob(f"{glob.escape(old)}_*")) if ad.is_dir() else []:
            tail = p.name.partition("_")[2]
            _move_or_keep(p, ad / f"{new}_{tail}", old, "광고", _merge_ad_state if tail == "광고.json" else None)
    changed = False
    for j in jobs:
        head, _, rest = (j.file or "").partition("/")
        acct, _, tail = rest.partition("/")
        if head == "월자료" and tail and acct in mt:
            j.file, changed = f"월자료/{mt[acct]}/{tail}", True
    return changed


def _side_names() -> list:
    """월자료·광고·정산현황 원문에 쓰인 계정 이름(바꿈표 재료)."""
    out = [p.name for d in (VERIFY / "월자료", BASE / RG_RAW_DIRNAME) if d.is_dir() for p in d.iterdir() if p.is_dir()]
    out += [p.name.partition("_")[0] for p in (VERIFY / "광고").glob("*_*")] if (VERIFY / "광고").is_dir() else []
    return out


def migrate_names(accts, log) -> None:
    """요청 기록(_요청기록.json)·받은 파일·쿠팡 지급 내역 파일의 예전 계정명 → 지금 계정명(멱등).
    금액 기록 파일 이름의 계정명도 바꿈표에 넣는다 — 합치기로 옮겨 온 금액 기록만 예전 이름일 때(파일·요청 기록은
    이미 새 이름) 바꿈표가 비어 계정이 둘로 갈리던 결함(2026-10-08 재현·수정).
    검증 자료(검증자료/{계정명}.json)도 맞춘다 — 예전 이름 파일이 남아 집계 '계좌 입금'·'검증'에 계정이 두 번 들어가던
    결함(2026-10-13 운용 PC 실측: aehee5505·hk66597582). 스냅샷이라 합치지 않고 수집일 최근 것 하나만 남김.
    월자료·광고·정산현황 원문도 맞춘다(_migrate_side_data · T-46 ⑥)."""
    jobs = SJ.load_jobs(JOBS)
    names = [SF.parse_file_name(p.name)["account"] for d in (FILES, COSTS) for p in d.glob("*.xlsx")]
    names += [p.stem.rpartition("_")[0] for p in AMOUNTS.glob("*.json")]
    names += [p.stem for p in VERIFY.glob("*.json")]
    names += _side_names()
    m, mt = rename_jobs(jobs, accts, names)
    if _migrate_side_data(mt, jobs) or m or mt:
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
    for p in list(VERIFY.glob("*.json")):
        if p.stem in mt:
            _keep_newer_verify(p, p.with_name(f"{mt[p.stem]}.json"))
    if m or mt:
        log(f"  [계정명 맞춤] 요청 기록 {len(m)}개·파일 계정명 {len(mt)}개를 지금 계정 파일 이름으로 바꿈")


STATS_KEEP = 3                                           # output/정산 에 남기는 정산집계 수(최신 · D-243 ②)
_STATS_NAME = re.compile(r"정산집계_(\d{2})(\d{2})\d{2}_\d{6}\.xlsx")


def rotate_stats(base: Path, keep: int = STATS_KEEP) -> int:
    """정산집계(정산집계_yymmdd_HHMMSS.xlsx)는 최신 keep 개만 base 에 · 나머지는 base/보관/YYYY-MM/(파일 이름 날짜)로 이동 —
    지우지 않음(D-243 ② · output (37) 75개 약 180MB). 읽는 코드 없음(정산서 도구는 --stats 경로 인자). 반환 = 옮긴 수."""
    olds = sorted((p for p in Path(base).glob("정산집계_*.xlsx") if _STATS_NAME.fullmatch(p.name)), key=lambda p: p.name)[:-keep or None]
    for p in olds:
        yy, mm = _STATS_NAME.fullmatch(p.name).groups()
        d = Path(base) / "보관" / f"20{yy}-{mm}"
        d.mkdir(parents=True, exist_ok=True)
        os.replace(p, d / p.name)
    return len(olds)


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
