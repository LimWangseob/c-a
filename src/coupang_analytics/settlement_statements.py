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


def _report(ctx, res: list, skipped: list) -> dict:
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
    return {"made": len(rows), "own": sum(own for _, own in res), "skipped": len(skipped), "ok": okn, "total": len(allv)}


def run(args: CTX.StatementArgs) -> dict:
    """정산서를 만들고 요약 숫자를 돌려줌. 입력 폴더에 필요한 파일이 없으면 FileNotFoundError(시작 전 중단)."""
    miss = CTX.missing_inputs(args.inputs)
    if miss:
        raise FileNotFoundError(f"입력 폴더 {args.inputs} 에 없음: {', '.join(miss)}")
    ctx = CTX.load(args)
    res, skipped = [], []
    for acct in ctx.accts:
        a = account(ctx, acct)
        row = summary_row(a, shown(a))                      # 정산서 1쪽과 같은 숫자(줄 합계 검산 포함)
        if not (a["mpids"] or a["scope"].startswith(AC.LEDGER) or a["scope"] == AC.SETTLE_ONLY):
            skipped.append(row)
            continue
        own = a["info"]["사업자"] in SRC.OWN_BUSINESSES
        book(ctx, a, _dest(ctx, a, own))
        res.append((row, own))
        if abs(a["ship_stats"] - (a["ship"]["관리"][1] + a["ship"]["제외"][1] + a["ship"]["확인 필요"][1])) > 1:
            print(f"  ⚠ {a['aid']} 배송비 정산금액 집계 {a['ship_stats']:,.0f} ≠ 정산 원본 배송비 줄 합 — 확인 필요")
    summary_book(ctx, res, skipped)
    return _report(ctx, res, skipped)
