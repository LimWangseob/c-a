"""위탁정산서(관리 상품만 · D-116) 만들기 — 전 위탁 계정 정산서 1개씩 + 전체 요약. T-25 이관 입구(옛 `run_contract_window.py` →
`statement_managed.main()` · 행동 불변). 실행 = `tools/settlement_statements.py`(인자) · 5단계에서 정산다운로드.exe `statements` 가 부름.

모듈 지도: context(입력·공통 자료) → account·deduct(계정 계산 1·2부) → sheets·book(엑셀) · 입력 읽기 = statement_source ·
장부 = settlement_ledger · 배분 규칙 = settlement_managed_alloc · 체험단 = settlement_experience · 추가지급 = settlement_additional_pay.
"""
from __future__ import annotations

from pathlib import Path

from coupang_analytics import settlement_statement_account as AC
from coupang_analytics import settlement_statement_context as CTX
from coupang_analytics import settlement_statement_source as SRC
from coupang_analytics.settlement_statement_book import book, safe_name, summary_book, summary_row
from coupang_analytics.settlement_statement_deduct import account
from coupang_analytics.settlement_statement_sheets import shown

ARGS = CTX.StatementArgs


def _dest(ctx, a: dict, own: bool) -> Path:
    info = a["info"]
    return (ctx.out / (SRC.OWN_DIR if own else "")
            / f"정산서_{safe_name(info['사업자'])}_{safe_name(info['대표자'] or '')}_{a['aid']}_관리상품.xlsx")


def _report(ctx, res: list, skipped: list, failed: list | None = None, files: list | None = None) -> dict:
    failed = failed or []
    rows = [r for r, own in res if not own]
    allv = [r for r in rows + [r for r in skipped if r[0] not in SRC.OWN_BUSINESSES]]
    okn = sum(1 for r in allv if r[14] == "일치")
    print(f"정산서 {len(rows)}곳(+우리 사업자 {sum(own for _, own in res)}) · 정산서 없음 {len(skipped)}곳 → {ctx.out}")
    print(f"정산 100% 일치(계정 전체·위탁): {okn}/{len(allv)}")
    for r in allv:
        if r[14] != "일치":
            print(f"  ✘ {r[0]} ({r[2]}): {r[15]}")
    for r in skipped:
        print(f"  · 정산서 없음 {r[0]} ({r[2]}): {r[3]}")
    for aid, why in failed:
        print(f"  ❌ 정산서 못 만듦 {aid}: {why}")
    return {"made": len(rows), "own": sum(own for _, own in res), "skipped": len(skipped), "ok": okn, "total": len(allv),
            **_ids(res, skipped, failed, files or [])}


def _ids(res: list, skipped: list, failed: list, files: list) -> dict:
    """계정별 결과(배치 보고용) — 만든 계정 · 우리 사업자 · 정산서 없음(사유) · 못 만듦(사유) · 만든 파일."""
    return {"made_ids": [r[2] for r, _ in res], "own_ids": [r[2] for r, own in res if own],
            "none": [(r[2], r[3]) for r in skipped], "failed": list(failed), "files": [str(f) for f in files]}


def _one(ctx, acct) -> tuple:
    """계정 1개 → ('made', 요약 줄, 우리 사업자?, 파일) 또는 ('none', 요약 줄) — 옛 반복 본문 그대로(T-25 · 행동 불변)."""
    a = account(ctx, acct)
    row = summary_row(a, shown(a))                      # 정산서 1쪽과 같은 숫자(줄 합계 검산 포함)
    if not AC.issued(a["scope"], a["mpids"]):
        return ("none", row)
    own = a["info"]["사업자"] in SRC.OWN_BUSINESSES
    dest = _dest(ctx, a, own)
    book(ctx, a, dest)
    if abs(a["ship_stats"] - (a["ship"]["관리"][1] + a["ship"]["제외"][1] + a["ship"]["확인 필요"][1])) > 1:
        print(f"  ⚠ {a['aid']} 배송비 정산금액 집계 {a['ship_stats']:,.0f} ≠ 정산 원본 배송비 줄 합 — 확인 필요")
    return ("made", row, own, dest)


def run(args: CTX.StatementArgs, *, skip: tuple = (), history_rows: list | None = None) -> dict:
    """정산서를 만들고 요약 숫자를 돌려줌. 입력 폴더에 필요한 파일이 없으면 FileNotFoundError(시작 전 중단).
    계정 하나가 예외를 내면 그 계정만 'failed'(사유)로 남기고 나머지 계정은 계속 만든다(계정별 격리 · D-399 계획 설계 5).
    skip = 건너뛸 계정ID(정산 받기 실패 계정) · history_rows = 원장 '계정이력' 행(메모리 · CTX.load)."""
    miss = CTX.missing_inputs(args.inputs)
    if miss:
        raise FileNotFoundError(f"입력 폴더 {args.inputs} 에 없음: {', '.join(miss)}")
    ctx = CTX.load(args, history_rows)
    res, skipped, failed, files = [], [], [], []
    for acct in ctx.accts:
        aid = SRC.aid_of(acct)
        if (args.only and aid not in args.only) or aid in skip:
            continue
        try:
            got = _one(ctx, acct)
        except Exception as exc:  # noqa: BLE001 — 계정 하나의 오류 = 그 계정만 '정산서 못 만듦'(사유를 보고) · 다른 계정은 계속
            failed.append((aid, f"{exc.__class__.__name__}: {exc}"))
            print(f"  ❌ {aid} 정산서 못 만듦 — {exc.__class__.__name__}: {exc}")
            continue
        if got[0] == "none":
            skipped.append(got[1])
        else:
            res.append((got[1], got[2]))
            files.append(got[3])
    files.append(summary_book(ctx, res, skipped))
    return _report(ctx, res, skipped, failed, files)
