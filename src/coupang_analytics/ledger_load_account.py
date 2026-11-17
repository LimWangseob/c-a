"""장부 DB 이관 ④ — 계정 단위 자료 → pay_round(정산 회차) · account_entry(계정 내역) · product_cost(윙 추가지급).

역할(role) 뜻 — 회차 대조(V4)에서 두 번 세지 않게 나눔:
- '지급 구성' = 쿠팡이 계정 단위로 그 회차에서 더하거나 뺀 값(윙 차감 사유 · RG 이월·추가 공제·판매 조정 · 비용 세액).
- '대조용' = 상품 내역의 합이거나 지급 구성의 원천 상세(RG 비용 칸 합 · 재고 보상 합 · 광고정산·밀크런 원천 · 매출내역).
- '예정' = 정산예정기록·정산현황 원문의 예정값(수집일마다).
- J4 판정(2단계 · 판정/J4_판정.json): 월렛 입출금 = '대조용'(실입금 기록 · DEPOSIT 556건 = 그날 회차 최종지급액 합 원 단위 ·
  정산금액 SSOT = 지급내역) · 우대수수료 환급 = '별도 입금'(쿠팡페이가 대표계좌로 직접 · 회차 지급과 별개 · 주문 단위).
KEY: 윙 회차 = 정산일|기간 시작|기간 끝|지급비율|보류 해제|pendingAmount · RG = 정산일|기간 시작|기간 끝|지급비율
(샘플검증 5절 3). 원문의 UTC `T15:00:00Z` = 한국 다음 날(320/320 실측).
"""
from __future__ import annotations

import gzip
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import settlement_files as SF
from .ledger_src import RATIO_AD, RATIO_INBOUND, RATIO_SQL, Registry, account_id, blank, d10, header_index, nid, won

RG_PAY = ("totalLastSettlementUnpaidCfsDeductionAmount", "totalPastCfsDeductionAmount", "totalAdSalesDeductionAmount",
          "totalMilkRunDeductionAmount", "totalArFactoringDeductionAmount", "totalNegativeDeductionAmount",
          "totalCoupangLiveDeductionAmount", "totalDebitCardDeductionAmount", "totalMerchantCashAdvanceDeductionAmount",
          "totalBusinessInsightsDeductionAmount", "totalSubscriptionFeeDeductionAmount",
          "totalPostPurchaseDeductionAmount", "totalCfsFeeAdjustment")
# 더하는 칸: 판매 조정 · 이월(CarryOver = 이번 회차에서 못 뺀 비용을 다음으로 넘긴 금액 → 비용 칸에서 뺀 만큼 되돌려 더함).
# 실측(2단계 J7): 이월 칸 있는 RG 회차 108개 전부 빼기로 넣었을 때 '차 = 2 × 이월' → 더하기로 고침.
RG_PLUS = ("totalSalesAdjustment", "totalCarryOverSettlementDeductionAmount")
_ENTRY_SQL = ("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, link_key, occur_date, "
              "file_id, src_pos) VALUES (?,?,?,?,?,?,?,?,?,?)")


def kst(v) -> str:
    """원문 날짜: UTC 'YYYY-MM-DDT15:00:00Z' → 한국 다음 날 · 그 밖 = 앞 10자."""
    s = str(v or "")
    if s.endswith("T15:00:00Z"):
        return f"{date.fromisoformat(s[:10]) + timedelta(days=1):%Y-%m-%d}"
    return d10(s)


def wing_key(r: dict) -> tuple[str, int]:
    one_day = r.get("기간 시작") == r.get("기간 끝")
    release = int(one_day and won(r.get("지급비율")) == 100)
    return (f"{r.get('정산일')}|{r.get('기간 시작')}|{r.get('기간 끝')}|{won(r.get('지급비율'))}|{release}|"
            f"{won(r.get('pendingAmount'))}"), release


def rg_key(r: dict) -> str:
    return f"{r.get('정산일')}|{r.get('기간 시작')}|{r.get('기간 끝')}|{won(r.get('지급비율'))}"


class AccountLoader:
    def __init__(self, con: sqlite3.Connection, reg: Registry):
        self.con, self.reg = con, reg

    def entry(self, *row) -> None:
        self.con.execute(_ENTRY_SQL, row)

    # ── 쿠팡지급내역 ──
    def payments(self, base: Path) -> None:
        for p in sorted(base.glob("*.json")):
            acc_label, _, ch = p.stem.rpartition("_")
            acc = account_id(acc_label)
            fid = self.reg.add(p, f"쿠팡지급내역 {ch}", acc)
            if fid is None:
                continue
            rows = json.loads(p.read_text(encoding="utf-8")) or []
            self.entry(acc, ch, "label", "표기", "보기용", 0, acc_label, "", fid, "이름")
            used: dict[str, int] = {}
            for i, r in enumerate(rows):
                self._pay_row(acc, ch, r, fid, i, used)
            self.reg.done(fid, len(rows), len(rows))
        self.con.commit()

    @staticmethod
    def _round_values(ch: str, r: dict) -> tuple:
        """(release, target, payable, deduction, final, pending) — 윙/로켓그로스 칸 이름 차이만 흡수."""
        fin = r.get("최종지급액")
        if ch == "윙":
            return (wing_key(r)[1], won(r.get("targetAmount")), won(r.get("paidAmount")),
                    won(r.get("totalDeductionAmount")), None if fin is None else won(fin), won(r.get("pendingAmount")))
        final = won(r.get("totalFinalSettlementAmount")) if fin is None else won(fin)
        return 0, None, won(r.get("totalPayableAmount")), None, final, None

    def _pay_row(self, acc: str, ch: str, r: dict, fid: int, i: int, used: dict) -> None:
        rk = wing_key(r)[0] if ch == "윙" else rg_key(r)
        used[rk] = used.get(rk, 0) + 1
        if used[rk] > 1:
            rk = f"{rk}#{used[rk]}"        # 같은 KEY 2번째 = KEY 겹침(V3·J3 대상) — 줄은 남김
        release, tgt, payable, ded, final, pending = self._round_values(ch, r)
        self.con.execute("INSERT INTO pay_round(account_id, sale_type, round_key, settle_date, period_start, period_end, "
                         "ratio, status, release, target, payable, deduction, final, pending, file_id, src_pos) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (acc, ch, rk, r.get("정산일") or "", r.get("기간 시작") or "", r.get("기간 끝") or "",
                          float(r.get("지급비율") or 0), str(r.get("지급상태") or ""), release, tgt, payable, ded, final,
                          pending, fid, f"[{i}]"))
        self._pay_entries(acc, ch, rk, r, fid, f"[{i}]")

    def _pay_entries(self, acc: str, ch: str, rk: str, r: dict, fid: int, pos: str) -> None:
        if ch == "윙":
            for j, d in enumerate(r.get("차감 사유") or []):
                self.entry(acc, ch, rk, f"차감 {d.get('사유')}", "지급 구성", -won(d.get("금액")), "", "", fid, f"{pos}.차감[{j}]")
        for k, v in sorted(r.items()):
            if isinstance(v, (int, float)) and v and k not in ("지급비율", "ratio"):
                role = "지급 구성" if ch != "윙" and k in RG_PAY + RG_PLUS else "대조용"
                sign = 1 if k in RG_PLUS else -1
                self.entry(acc, ch, rk, k, role, sign * won(v) if role == "지급 구성" else won(v), "", "", fid, pos)

    # ── 정산예정기록(jsonl 한 파일) ──
    def forecast(self, path: Path) -> None:
        if not path.exists():
            return
        fid = self.reg.add(path, "정산예정기록", None)
        if fid is None:
            return
        read = loaded = 0
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, start=1):
                read += 1
                r = json.loads(line)
                acc = account_id(r.get("계정", ""))
                if acc in self.reg.exclude or not self.reg.wanted(acc):
                    self.reg.skip(fid, "제외·범위 밖 계정 줄")
                    continue
                ch = r.get("채널", "")
                rk = wing_key(r)[0] if ch == "윙" else rg_key(r)
                self.entry(acc, ch, rk, f"예정 최종지급액@{r.get('수집일')}", "예정", won(r.get("최종지급액")), "",
                           r.get("수집일") or "", fid, f"{n}")
                loaded += 1
        self.reg.done(fid, read, loaded)
        self.con.commit()

    # ── 로켓그로스 정산현황 원문(수집일 gz) ──
    def raw_status(self, base: Path) -> None:
        if not base.is_dir():
            return
        for d in sorted(x for x in base.iterdir() if x.is_dir()):
            acc = account_id(d.name)
            for q in sorted(d.glob("*.json.gz")):
                fid = self.reg.add(q, "로켓그로스 정산현황 원문", acc)
                if fid is None:
                    continue
                j = json.load(gzip.open(q, "rt", encoding="utf-8"))
                n = 0
                for part in ("조회", "예정"):
                    for b, blk in enumerate(j.get(part) or []):
                        for k, r in enumerate((blk.get("응답") or {}).get("settlementStatusReports") or []):
                            rk = (f"{kst(r.get('settlementDate'))}|{kst(r.get('settlementPeriodStartDate'))}|"
                                  f"{kst(r.get('settlementPeriodEndDate'))}|{won(r.get('settlementRatio'))}")
                            self.entry(acc, "로켓그로스", rk, f"원문 {part} finalSettlementAmount@{q.name[:10]}",
                                       "예정" if part == "예정" else "대조용", won(r.get("finalSettlementAmount")),
                                       str(r.get("settlementGroupKey") or ""), q.name[:10], fid, f"{part}[{b}][{k}]")
                            n += 1
                self.reg.done(fid, n, n)
            self.con.commit()

    # ── 광고정산 json · 밀크런 xlsx (지급 구성의 원천 상세 = 대조용) ──
    def ads(self, base: Path) -> None:
        if not base.is_dir():
            return
        for p in sorted(base.iterdir()):
            label, _, rest = p.name.partition("_")
            acc = account_id(label)
            if rest.startswith("광고정산") and p.suffix == ".json":
                self._ad_json(p, acc)
            elif rest.startswith("밀크런") and p.suffix == ".xlsx":
                self._milkrun(p, acc)
            elif rest.startswith("매출성장광고") and p.suffix == ".xlsx":
                self._ad_report(p, acc)
            elif self.reg.wanted(acc):
                self.reg.add(p, f"광고 기타({rest.split('_')[0]})", acc, status="생략",
                             note="대조표 7절 생략(광고 상태)")
        self.con.commit()

    def _ad_json(self, p: Path, acc: str) -> None:
        fid = self.reg.add(p, "광고정산", acc)
        if fid is None:
            return
        items = json.loads(p.read_text(encoding="utf-8")).get("items") or []
        for i, x in enumerate(items):
            self.entry(acc, "", f"date:{d10(x.get('date'))}", f"광고 청구가능 {x.get('adType') or ''}", "대조용",
                       -won(x.get("billableAmount")), nid(x.get("campaignId")), d10(x.get("date")), fid, f"items[{i}]")
        self.reg.done(fid, len(items), len(items))

    def _ad_report(self, p: Path, acc: str) -> None:
        """매출성장광고 보고서 → ratio_src '광고 보고서'(날짜×캠페인×광고집행 옵션 광고비 합 · 광고비를 옵션으로 나누는 비율 자료 D-140·D-119).
        같은 날짜·캠페인·옵션 줄(키워드·지면별)은 한 줄로 더함 · src_pos = 첫 행+줄 수."""
        fid = self.reg.add(p, "광고 보고서(매출성장광고)", acc)
        if fid is None:
            return
        g = SF.read_grid(p)
        ix = header_index(g[0]) if g else {}
        agg: dict = {}
        n = 0
        for rn, r in enumerate(g[1:], start=2):
            if blank(r):
                continue
            def c(name: str):
                j = ix.get(name)
                return r[j] if j is not None and j < len(r) else None
            n += 1
            if c("날짜") in (None, "") or c("캠페인ID") in (None, ""):
                self.reg.skip(fid, "날짜·캠페인 ID 빈 줄")
                continue
            k = (d10(c("날짜")), nid(c("캠페인ID")), nid(c("광고집행옵션ID")))
            a = agg.setdefault(k, [rn, 0, 0.0])
            a[1] += 1
            a[2] += float(str(c("광고비") or 0).replace(",", ""))
        for (day, camp, opt), (rn, cnt, cost) in agg.items():
            self.con.execute(RATIO_SQL, (acc, RATIO_AD, camp, opt, day, cost, "", fid, f"{rn}+{cnt}"))
        self.reg.done(fid, n, n - sum(v for (f, _), v in self.reg.skips.items() if f == fid))

    def _milkrun(self, p: Path, acc: str) -> None:
        fid = self.reg.add(p, "밀크런", acc)
        if fid is None:
            return
        g = SF.read_grid(p)
        ix = header_index(g[0]) if g else {}
        n = 0
        for rn, r in enumerate(g[1:], start=2):
            if blank(r):
                continue
            n += 1
            def c(name: str):
                j = ix.get(name)
                return r[j] if j is not None and j < len(r) else None
            self.entry(acc, "로켓그로스", f"date:{d10(c('픽업일'))}", "밀크런 총 합계금액", "대조용", -won(c("총합계금액")),
                       nid(c("밀크런번호")), d10(c("픽업일")), fid, f"{rn}")
            if won(c("취소수수료")):
                self.entry(acc, "로켓그로스", f"date:{d10(c('픽업일'))}", "밀크런 취소수수료", "대조용", -won(c("취소수수료")),
                           nid(c("밀크런번호")), d10(c("픽업일")), fid, f"{rn}")
        self.reg.done(fid, n, n)


class VerifyLoader(AccountLoader):
    """검증 원자료 `검증자료/{계정}.json`(하루 1번 즉시 API · 대조표 7-4절)."""

    def run(self, base: Path) -> None:
        for p in sorted(base.glob("*.json")):
            acc = account_id(p.stem)
            fid = self.reg.add(p, "검증 원자료", acc)
            if fid is None:
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            n = (self._pending(acc, d, fid) + self._additional(acc, d, fid) + self._purchase(acc, d, fid)
                 + self._returns(acc, d, fid) + self._held(acc, d, fid) + self._inbound(acc, d, fid))
            k_skip = 0
            for k in ("calendar", "wallet_balance", "rg_vat", "wing_vat", "fast_settlement",
                      "promotion_fee", "review_campaigns"):
                if d.get(k):
                    self.reg.skip(fid, f"키 {k} — 대조표 7-4절 생략·확인 필요(J4)")
                    k_skip += 1
            self.reg.done(fid, n + k_skip, n)
        self.con.commit()

    def _inbound(self, acc: str, d: dict, fid: int) -> int:
        """입고 내역 → ratio_src '입고 적치'(밀크런번호 × 옵션 · 적치 수량, 없으면 요청 수량 · 취소 = flag) — 밀크런을 상품으로 나누는 비율 자료."""
        n = 0
        for i, s in enumerate(d.get("inbound") or []):
            for j, k in enumerate(s.get("skus") or []):
                q = k.get("stowedQty") or k.get("requestedQty") or 0
                self.con.execute(RATIO_SQL, (acc, RATIO_INBOUND, nid(s.get("milkrunSeq")), nid(k.get("vendorItemId")),
                                             d10(s.get("pickupDate")), float(q), "취소" if s.get("cancelled") else "",
                                             fid, f"inbound[{i}].skus[{j}]"))
                n += 1
        return n

    def _pending(self, acc: str, d: dict, fid: int) -> int:
        rows = ((d.get("pending") or {}).get("전체") or {}).get("pendingReports") or []
        for i, r in enumerate(rows):
            rk = f"pending:{d10(r.get('paymentDate'))}|{d10(r.get('revenueRecognitionDateFrom'))}|" \
                 f"{d10(r.get('revenueRecognitionDateTo'))}"
            self.entry(acc, "윙", rk, f"보류 {r.get('pendingReason') or ''}", "대조용", won(r.get("pendingAmount")),
                       str(r.get("paymentStatus") or ""), d10(r.get("pendingReleaseDate")), fid, f"pending[{i}]")
        return len(rows)

    def _additional(self, acc: str, d: dict, fid: int) -> int:
        n = 0
        for ym, blk in sorted((d.get("additional") or {}).items()):
            for i, r in enumerate((blk or {}).get("reports") or []):
                self.con.execute(
                    "INSERT INTO product_cost(account_id, kind, nat_key, option_id, inventory_id, order_no, txn_type, "
                    "occur_date, cycle_end, settle_type, amount, sign, file_stage, settle_date, file_id, sheet, src_row) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (acc, "윙 추가지급", f"{nid(r.get('orderId'))}|{nid(r.get('vendorItemId'))}|{r.get('rewardType')}",
                     nid(r.get("vendorItemId")), "", nid(r.get("orderId")), str(r.get("rewardType") or ""),
                     d10(r.get("payDate")), "", str(r.get("requestStatusType") or ""), won(r.get("finalRewardAmount")),
                     1, "추가지급", d10(r.get("payDate")), fid, f"additional.{ym}", i))
                n += 1
        return n

    def _purchase(self, acc: str, d: dict, fid: int) -> int:
        n = 0
        for ym, blk in sorted((d.get("purchase") or {}).items()):
            for i, r in enumerate((blk or {}).get("purchaseReports") or []):
                rk = f"month:{ym}|{r.get('transactionCycle') or ''}"
                for k in ("revenueAmount", "apAmount", "deductionAmount", "finalPaidAmount", "feeAmount"):
                    self.entry(acc, "윙", rk, f"매출내역 {k}", "대조용", won(r.get(k)), "", "", fid, f"purchase.{ym}[{i}]")
                n += 1
        return n

    def _returns(self, acc: str, d: dict, fid: int) -> int:
        n = 0
        for order, items in sorted((d.get("returns") or {}).items()):
            for i, r in enumerate(items or []):
                for j, it in enumerate(r.get("items") or []):
                    self.entry(acc, "", f"order:{nid(order)}", "반품 조회 옵션", "연결", 0,
                               f"{nid(order)}>{nid(it.get('vendorItemId'))}", d10(r.get("returnDate")), fid,
                               f"returns.{order}[{i}].items[{j}]")
                    n += 1
        return n

    def _held(self, acc: str, d: dict, fid: int) -> int:
        """월렛 입출금(대조용) · 우대수수료 환급(별도 입금) — 둘 다 회차 지급 구성 밖(J4)."""
        n = 0
        for i, w in enumerate(d.get("wallet") or []):
            self.entry(acc, "로켓그로스", f"wallet:{w.get('walletEventId') or i}", f"월렛 {w.get('walletEventType')}",
                       "대조용", won(w.get("amount")), json.dumps(w.get("settlementGroupKeys") or [], ensure_ascii=False),
                       d10(str(w.get("paymentDate") or "")[:8]), fid, f"wallet[{i}]")
            n += 1
        for ym, blk in sorted((d.get("favorable") or {}).items()):
            for i, r in enumerate((blk or {}).get("rows") or []):
                self.entry(acc, "윙", f"favorable:{ym}", "우대수수료 환급", "별도 입금", won(r.get("refundAmount")),
                           nid(r.get("orderId")), d10(r.get("realTransferDateStr")), fid, f"favorable.{ym}[{i}]")
                n += 1
        return n


def load(con: sqlite3.Connection, reg: Registry, settle_dir: Path) -> None:
    VerifyLoader(con, reg).run(Path(settle_dir) / "검증자료")
    a = AccountLoader(con, reg)
    a.payments(Path(settle_dir) / "쿠팡지급내역")
    a.forecast(Path(settle_dir) / "정산예정기록.jsonl")
    a.raw_status(Path(settle_dir) / "정산현황_원문")
    a.ads(Path(settle_dir) / "검증자료" / "광고")
    reg.flush()
