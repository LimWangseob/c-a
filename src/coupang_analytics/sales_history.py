"""판매분석 판매금액 날짜별 누적 — output/판매분석_일별/{계정ID}/{YYYY-MM}.json (소유자 2026-10-13 · 달 파일 D-243 ③).

매일 ① 판매수집의 판매분석(vi-detail-search, 전날 하루) 옵션별 판매금액(totalGmv)·수량·주문을 날짜 키로 쌓는다.
쿠팡 정산은 판매보다 늦어(로켓그로스 주마감+20영업일 등) 정산 전 최근 판매를 금액으로 알기 위함 —
사업자별 정산내역의 '미정산(정산 예정)' 로켓그로스 추정 보강용.

규칙: 하루 단위 조회(date_from == date_to)만 기록(넓은 기간 보강 조회는 기간 합계라 제외) · 판매금액을 모르는
출처(엑셀 폴백 = gmv None)는 기록 안 함 · 같은 날 재실행 = 그날만 교체 · 판매 0인 날도 빈 기록(자료 없음과 구분) ·
임시 파일에 쓰고 바꿔 끼움(반쯤 쓴 파일 없음).

달 파일(D-243 ③ · 2026-11-15): 계정 1개 = 파일 1개를 매일 통째로 다시 써 output 이 커졌다(58MB) → 계정 폴더 × 달 파일.
그날이 든 달 파일만 다시 씀(지난 달 파일은 소급으로 그 달 날을 받을 때만). 옛 파일(`판매분석_일별/{계정}.json`)은 이 폴더에
처음 기록할 때 전부 달 파일로 바꾸고 `output/보관/YYYY-MM/판매분석_일별/` 로 옮김(삭제 없음). 읽기는 옛 파일·달 파일을
함께 읽음(옮기지 않음 — 다른 PC 사본 폴더를 읽어도 그대로).
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from . import daily_snapshot

DIRNAME = "판매분석_일별"
_KIND = {"RFM": "로켓그로스", "NORMAL": "윙"}


def record(out_dir, account_id: str, date_from: str, date_to: str, metrics: dict) -> str:
    """기록하면 '기록 …', 아니면 '건너뜀 — 사유'."""
    if date_from != date_to:
        return f"건너뜀 — 하루 단위 조회만 기록({date_from}~{date_to})"
    if any(m.gmv is None for m in metrics.values()):
        return "건너뜀 — 판매금액 없는 출처(엑셀 폴백)"
    opts, total = _options(metrics)
    _migrate_legacy(Path(out_dir))
    _put(_month_path(out_dir, account_id, date_to), date_to,
         {"수집": datetime.now().isoformat(timespec="seconds"), "합계": total, "옵션": opts})
    return f"기록 — 옵션 {len(opts)}개·판매금액 {total['판매금액']:,}원"


# ── 기간별(월·주) 합계 — 통합 판매현황(designs/SALES_SUMMARY.md·2026-10-15) ──────────────────────
# 키 = 'M:YYYY-MM'(달) · 'W:YYYY-MM-DD'(그 주 월요일). 쿠팡이 준 기간 합계를 그대로 저장(일별을 더해 만들지 않음 —
# 로그인 실패한 날이 있어도 다음 날 기간 조회가 메움). 조회기간 = [시작, 끝](이번 달·주는 끝이 어제라 매일 다시 받음).
PERIOD_DIRNAME = "판매분석_기간"


def record_period(out_dir, account_id: str, key: str, date_from: str, date_to: str, metrics: dict) -> str:
    """기간 합계 1건 저장(같은 키는 교체). 판매금액 모르는 출처(gmv None)는 저장 안 함."""
    if any(m.gmv is None for m in metrics.values()):
        return "건너뜀 — 판매금액 없는 출처"
    opts, total = _options(metrics)
    path = Path(out_dir) / PERIOD_DIRNAME / f"{account_id}.json"
    daily_snapshot.keep_before_overwrite(path)                # 진행 중 기간 누계 교체 전 값(D-335)
    _put(path, key, {"수집": datetime.now().isoformat(timespec="seconds"), "조회기간": [date_from, date_to],
                     "합계": total, "옵션": opts})
    return f"기록 — {key} 옵션 {len(opts)}개·판매금액 {total['판매금액']:,}원"


def load_daily(out_dir) -> dict:
    """{계정ID: {'YYYY-MM-DD': 기록}} — 일별 저장 전체(옛 계정 파일 + 계정 폴더 달 파일 합침 · 읽기만)."""
    d = Path(out_dir) / DIRNAME
    if not d.is_dir():
        return {}
    ids = sorted({p.stem for p in d.glob("*.json")} | {p.name for p in d.iterdir() if p.is_dir()})
    return {aid: load_account(out_dir, aid) for aid in ids}


def load_account(out_dir, account_id: str) -> dict:
    """한 계정의 {'YYYY-MM-DD': 기록} — 옛 파일 + 달 파일(같은 날이면 달 파일). 없으면 {}."""
    d = Path(out_dir) / DIRNAME
    legacy = d / f"{account_id}.json"
    data = json.loads(legacy.read_text(encoding="utf-8")) if legacy.is_file() else {}
    for p in sorted((d / account_id).glob("*.json")) if (d / account_id).is_dir() else []:
        data.update(json.loads(p.read_text(encoding="utf-8")))
    return dict(sorted(data.items()))


def _month_path(out_dir, account_id: str, day: str) -> Path:
    return Path(out_dir) / DIRNAME / account_id / f"{day[:7]}.json"


def _migrate_legacy(out: Path) -> None:
    """옛 계정 파일(판매분석_일별/{계정}.json) → 계정 폴더 달 파일(같은 달 파일이 있으면 합침 · 같은 날은 달 파일 값)
    → 옛 파일을 output/보관/YYYY-MM/판매분석_일별/ 로 이동(D-243 · 삭제 금지). 옛 파일이 없으면 아무것도 안 함."""
    d = out / DIRNAME
    for legacy in sorted(d.glob("*.json")) if d.is_dir() else []:
        by_month: dict = {}
        for day, rec in json.loads(legacy.read_text(encoding="utf-8")).items():
            by_month.setdefault(day[:7], {})[day] = rec
        for month, recs in by_month.items():
            path = _month_path(out, legacy.stem, month)
            have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            _write(path, {**recs, **have})
        _archive(out, legacy)


def _archive(out: Path, legacy: Path) -> None:
    now = datetime.now()
    dest = out / "보관" / f"{now:%Y-%m}" / DIRNAME / legacy.name
    if dest.exists():                                    # 같은 달에 두 번 옮김(다른 PC 사본 합침 등) — 덮어쓰지 않음
        dest = dest.with_name(f"{legacy.stem}_{now:%d%H%M%S}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(dest))


def load_periods(out_dir) -> dict:
    """{계정ID: {'M:…'|'W:…': 기록}} — 기간별 저장 전체."""
    return _load_dir(Path(out_dir) / PERIOD_DIRNAME)


def _options(metrics: dict) -> tuple[dict, dict]:
    opts = {vid: {"상품": m.product_name, "옵션": m.option_name,
                  "구분": _KIND.get(m.registration_type, m.registration_type or "-"),
                  "판매금액": m.gmv, "판매수량": m.sales, "주문": m.orders, "등록상품ID": m.inventory_id}
            for vid, m in sorted(metrics.items())}
    return opts, {k: sum(o[k] for o in opts.values()) for k in ("판매금액", "판매수량", "주문")}


def _put(path: Path, key: str, rec: dict) -> None:
    """그 키만 교체해 임시 파일에 쓰고 바꿔 끼움(반쯤 쓴 파일 없음)."""
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[key] = rec
    _write(path, data)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _load_dir(d: Path) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))} if d.is_dir() else {}
