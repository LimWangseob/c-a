"""판매분석 판매금액 날짜별 누적 — output/판매분석_일별/{계정ID}.json (소유자 2026-10-13).

매일 ① 판매수집의 판매분석(vi-detail-search, 전날 하루) 옵션별 판매금액(totalGmv)·수량·주문을 날짜 키로 쌓는다.
쿠팡 정산은 판매보다 늦어(로켓그로스 주마감+20영업일 등) 정산 전 최근 판매를 금액으로 알기 위함 —
사업자별 정산내역의 '미정산(정산 예정)' 로켓그로스 추정 보강용.

규칙: 하루 단위 조회(date_from == date_to)만 기록(넓은 기간 보강 조회는 기간 합계라 제외) · 판매금액을 모르는
출처(엑셀 폴백 = gmv None)는 기록 안 함 · 같은 날 재실행 = 그날만 교체 · 판매 0인 날도 빈 기록(자료 없음과 구분) ·
임시 파일에 쓰고 바꿔 끼움(반쯤 쓴 파일 없음).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

DIRNAME = "판매분석_일별"
_KIND = {"RFM": "로켓그로스", "NORMAL": "윙"}


def record(out_dir, account_id: str, date_from: str, date_to: str, metrics: dict) -> str:
    """기록하면 '기록 …', 아니면 '건너뜀 — 사유'."""
    if date_from != date_to:
        return f"건너뜀 — 하루 단위 조회만 기록({date_from}~{date_to})"
    if any(m.gmv is None for m in metrics.values()):
        return "건너뜀 — 판매금액 없는 출처(엑셀 폴백)"
    opts, total = _options(metrics)
    path = Path(out_dir) / DIRNAME / f"{account_id}.json"
    _put(path, date_to, {"수집": datetime.now().isoformat(timespec="seconds"), "합계": total, "옵션": opts})
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
    _put(path, key, {"수집": datetime.now().isoformat(timespec="seconds"), "조회기간": [date_from, date_to],
                     "합계": total, "옵션": opts})
    return f"기록 — {key} 옵션 {len(opts)}개·판매금액 {total['판매금액']:,}원"


def load_daily(out_dir) -> dict:
    """{계정ID: {'YYYY-MM-DD': 기록}} — 일별 저장 전체."""
    return _load_dir(Path(out_dir) / DIRNAME)


def load_periods(out_dir) -> dict:
    """{계정ID: {'M:…'|'W:…': 기록}} — 기간별 저장 전체."""
    return _load_dir(Path(out_dir) / PERIOD_DIRNAME)


def _options(metrics: dict) -> tuple[dict, dict]:
    opts = {vid: {"상품": m.product_name, "옵션": m.option_name,
                  "구분": _KIND.get(m.registration_type, m.registration_type or "-"),
                  "판매금액": m.gmv, "판매수량": m.sales, "주문": m.orders}
            for vid, m in sorted(metrics.items())}
    return opts, {k: sum(o[k] for o in opts.values()) for k in ("판매금액", "판매수량", "주문")}


def _put(path: Path, key: str, rec: dict) -> None:
    """그 키만 교체해 임시 파일에 쓰고 바꿔 끼움(반쯤 쓴 파일 없음)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[key] = rec
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _load_dir(d: Path) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))} if d.is_dir() else {}
