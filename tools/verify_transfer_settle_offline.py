"""셀독전환자 정산 2단계(정산 자료 받기 — 매일 18시 뒤) 오프라인 검증 — 로그인·쿠팡 호출 없음(결정적). D-187.

기대 동작 = `designs/SETTLEMENT_MODULE.md` §15 '2단계' 1~8 (코드에서 뽑지 않음):
 S1 대상 — 로그인 '실패'(비번 오류·2단계 인증·비번 없음)는 무인으로 다시 안 넣음 · 성공·미확인·차단·건너뜀은 받음
 S2 기다림 — 17:40~20:40·앱 파이프라인·정산 자동 수집이 모두 풀려야 시작 · 다음 17:40 까지 안 풀리면 끝 · 설정 빈 값 =
    1단계 결과가 있는 PC 만 매일 켬
 S3 실행 — 계정마다 기다림 재확인(돌면 기다림·중단 아님) · 비번 없음 = 로그인 안 함 · 계정 사이 45~75초 · 결과를 로그인 기록에
    갱신(지문만) · 차단·미완료·오류 2연속 = 중단 · 멈춤 시각 뒤 새 계정 안 함
 S4 원장 정산 기록에 같은 파일이 있으면 요청 안 하고 복사(계정ID 끝 기준·긴 ID 우선·기간 다르면 아님)
 S5 저장 = output/정산_셀독전환/정산 (정산 계정 기록과 섞지 않음) · 지급 내역 2026-01-01~ · 한 실행 계정당 30건 · 재사용은 요청 안 함
 S6 누적 파일 — 시트 4개·상품 칸 = 쿠팡 파일 원본·돈 = 지급 내역·다시 만들어도 같음·비번 없음 · 열려 있으면 오류
 S7 띄우기 — 18:00 무인·재부팅 복구 앱이 함께 띄움(--parent) · 탭 버튼
 S8 같은 잠금 — 1단계·2단계 한 번에 하나

    python tools/verify_transfer_settle_offline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import openpyxl  # noqa: E402

from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import transfer_accounts as TA  # noqa: E402
from coupang_analytics import transfer_login as TL  # noqa: E402
from coupang_analytics import transfer_settle as TS  # noqa: E402
from coupang_analytics.registry_lock import registry_lock  # noqa: E402

PW = "S3cret!pw"          # 결과 파일에 나오면 안 되는 값
FP = lambda aid, p: f"fp:{aid}:{len(p)}"   # noqa: E731  가짜 지문(실제 credstore 키 안 씀)
WING_HDR = ['주문번호', '과세유형', '상품 ID', '상품명', '옵션 ID', '옵션명', '판매가', '판매수량', '환불수량', '판매액',
            '판매자 할인쿠폰(A+B)', '판매자 할인쿠폰(A.즉시할인)', '판매자 할인쿠폰(B.다운로드)', '판매수수료',
            '서비스이용율(%,VAT별도)', '서비스이용료소급분', '마이샵수수료할인', '정산금액', '결제완료일', '배송완료일',
            '구매확정일', '취소완료일', '구매확정(출고)유형', '정산예정일']     # 실파일 2025-11 윙 최종액 주문상세 머리글 그대로
RG_HDR = ['정산유형', '정산주기(종료일)', '세금계산서 발행월', '발생일(결제완료일)', '매출인식일', '주문ID', '거래유형', '카테고리ID',
          '카테고리명', '과세유형', '등록상품 ID', '옵션ID', 'SKU ID', '등록상품명', '옵션명', '판매가(A)', '판매수량(B)',
          '판매액(A*B)', '쿠팡지원할인(C)', '매출금액(A*B-C)', '즉시할인쿠폰(D)', '다운로드쿠폰(E)', '판매자할인쿠폰(D+E)',
          '정산대상액', '판매수수료율(%,VAT별도)', '할인적용 판매수수료율(%,VAT별도)', '판매수수료', '판매수수료 VAT']


def ok(msg):
    print(f"  ✔ {msg}")


def _accts(n=6):
    return [TA.TransferAccount(f"acc{i}", f"사업자{i}", f"대표{i}", f"사업자{i}", f"010-{i}", "①셀독진행", i + 2, (), PW)
            for i in range(1, n + 1)]


class _Clock:
    """now() 대용 — sleep(초) 만큼 시간이 흐름."""
    def __init__(self, t: datetime):
        self.t = t
        self.slept: list[float] = []

    def __call__(self):
        return self.t

    def sleep(self, sec: float) -> None:
        self.slept.append(sec)
        self.t += timedelta(seconds=sec)


def s1_targets():
    print("[S1] 대상 — 로그인 '실패'는 무인으로 다시 안 넣음 · 성공·미확인·차단·건너뜀은 받음")
    accts = _accts()
    state = {"acc1": {"결과": TL.OK, "사유": "로그인 됨"},
             "acc2": {"결과": TL.FAIL, "사유": "로그인 비밀번호 오류 — 쿠팡 안내: 비밀번호가 다릅니다", "지문": ["옛값"]},
             "acc3": {"결과": TL.FAIL, "사유": "비밀번호 맞음 — 2단계 인증 필요(계약자 휴대폰 인증번호 — 연락 필요)"},
             "acc4": {"결과": TL.BLOCK, "사유": "로그인 차단(Akamai)"},
             "acc5": {"결과": TL.SKIP, "사유": "로그인 미완료"}}
    got = [a.account_id for a in TS.pick_targets(accts, state)]
    assert got == ["acc1", "acc4", "acc5", "acc6"], got
    assert [a.account_id for a in TS.pick_targets(accts, {"acc6": {"결과": TL.FAIL, "사유": "비밀번호 없음(파일·관리대장 모두)"}})] \
        == ["acc1", "acc2", "acc3", "acc4", "acc5"]
    ok("성공 acc1·차단 acc4·건너뜀 acc5·미확인 acc6 = 대상 · 비번 오류 acc2(지문 달라도)·2단계 인증 acc3·비번 없음 = 제외")


def s2_wait():
    print("[S2] 기다림 — 17:40~20:40·앱 파이프라인·정산 자동 수집이 모두 풀려야 시작 · 17:40 까지 안 풀리면 끝 · 매일 기본 켬")
    lines: list[str] = []
    c = _Clock(datetime(2026, 11, 10, 18, 0))
    stop = TL.deadline_of(TL.UNTIL_DEFAULT, c())
    assert stop == datetime(2026, 11, 11, 17, 40), stop
    busy_until = datetime(2026, 11, 10, 23, 0)
    busy = lambda: "정산 자동 다운로드이 도는 중" if c() < busy_until else ""   # noqa: E731
    assert TS.wait_ready(TL.UNTIL_DEFAULT, stop, lines.append, busy=busy, now=c, sleep=c.sleep) is True
    assert c() >= busy_until and c() < busy_until + timedelta(seconds=TS.WAIT_POLL_SEC + 1), c()
    assert all(s <= TS.WAIT_POLL_SEC for s in c.slept), c.slept
    assert any("18:00" in m or "17:40" in m for m in lines) and any("정산 자동" in m for m in lines), lines
    c2 = _Clock(datetime(2026, 11, 10, 18, 0))
    assert TS.wait_ready(TL.UNTIL_DEFAULT, stop, lambda m: None, busy=lambda: "", now=c2, sleep=c2.sleep) is True
    assert datetime(2026, 11, 10, 20, 40) <= c2() < datetime(2026, 11, 10, 20, 46), c2()   # 운용 PC 18:00 시간대 끝까지
    c3 = _Clock(datetime(2026, 11, 10, 21, 0))
    assert TS.wait_ready(TL.UNTIL_DEFAULT, TL.deadline_of(TL.UNTIL_DEFAULT, c3()), lambda m: None,
                         busy=lambda: "앱 실행(판매수집·순위)이 도는 중", now=c3, sleep=c3.sleep) is False
    assert c3() >= datetime(2026, 11, 11, 17, 40), c3()
    c4 = _Clock(datetime(2026, 11, 10, 10, 0))
    assert TS.wait_ready(TL.UNTIL_DEFAULT, TL.deadline_of(TL.UNTIL_DEFAULT, c4()), lambda m: None, busy=lambda: "",
                         now=c4, sleep=c4.sleep) is True and c4.slept == []          # 낮·잠금 없음 = 바로
    with tempfile.TemporaryDirectory() as d:          # 빈 설정 = 1단계 결과가 있는 PC 만 켬(없는 PC = 알려진 틀린 비번 재입력 위험)
        assert TS.daily_on(lambda k, d="": "", out_dir=d) is False
        (Path(d) / TL.STATE_FILE).write_text("{}", encoding="utf-8")
        assert TS.daily_on(lambda k, d="": "", out_dir=d) is True
        assert TS.daily_on(lambda k, d="": "0", out_dir=d) is False
    with tempfile.TemporaryDirectory() as d:
        assert TS.daily_on(lambda k, d="": "1", out_dir=d) is True and TS.DAILY_KEY == "transfer/daily"
    ok("18:00 시작 → 23:00(정산 자동 수집 끝) 시작 · 잠금 없어도 20:40 까지 · 계속 돌면 다음 날 17:40 에 끝 · 낮엔 바로 · "
       "빈 설정 = 1단계 결과 있는 PC 만 켬 · '1' 켬 · '0' 끔")


def s3_run():
    print("[S3] 실행 — 계정마다 기다림 재확인 · 비번 없음 = 로그인 안 함 · 사이 45~75초 · 로그인 기록 갱신 · 2연속 중단 · 멈춤 시각")
    accts = _accts()
    state0 = {"acc2": {"결과": TL.FAIL, "사유": "로그인 비밀번호 오류", "지문": ["x"]}}
    pw = lambda a: ([], "비밀번호 없음(파일·관리대장 모두)") if a.account_id == "acc3" else ([PW], "파일")   # noqa: E731
    plan = {"acc1": (TL.OK, "로그인 됨 · 정산 자료 받기 끝"), "acc4": (TL.FAIL, "로그인 비밀번호 오류"),
            "acc5": (TL.OK, "로그인 됨"), "acc6": (TL.OK, "로그인 됨")}
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / TL.STATE_FILE).write_text(json.dumps(state0, ensure_ascii=False), encoding="utf-8")
        c = _Clock(datetime(2026, 11, 10, 21, 0))
        called, busy_calls = [], {"n": 0}

        def busy():                                   # acc5 앞에서 한 번 앱이 돎 → 기다렸다 계속(중단 아님)
            busy_calls["n"] += 1
            return "앱 실행(판매수집·순위)이 도는 중" if called == ["acc1", "acc4"] and busy_calls["n"] == 4 else ""

        def work(a, pws, stop_at):
            called.append(a.account_id)
            assert pws == [PW] and stop_at == datetime(2026, 11, 11, 17, 40)
            c.sleep(600)
            return plan[a.account_id]
        rc = TS.run(accts, lambda m: None, work, out_dir=d, passwords=pw, busy=busy, now=c, sleep=c.sleep, fp=FP,
                    gap=lambda: 60.0)
        assert rc == 0 and called == ["acc1", "acc4", "acc5", "acc6"], (rc, called)
        st = TL.load_state(d)
        assert st["acc1"]["결과"] == TL.OK and st["acc1"]["지문"] == [FP("acc1", PW)], st["acc1"]
        assert st["acc3"]["결과"] == TL.FAIL and "비밀번호 없음" in st["acc3"]["사유"], st["acc3"]
        assert st["acc2"] == state0["acc2"], "제외 계정 기록은 그대로"
        assert st["acc4"]["결과"] == TL.FAIL and st["acc6"]["결과"] == TL.OK
        assert PW not in (Path(d) / TL.STATE_FILE).read_text(encoding="utf-8")
        assert c.slept.count(60.0) == 3, f"계정 사이 쉼 = 로그인한 계정 사이만(4계정 → 3번): {c.slept}"
        assert any(s == TS.WAIT_POLL_SEC or 0 < s < TS.WAIT_POLL_SEC for s in c.slept if s not in (60.0, 600)), c.slept
    with tempfile.TemporaryDirectory() as d:                 # 차단·미완료·오류 2연속 = 중단
        seq = iter([(TL.OK, "x"), (TL.BLOCK, "정산 화면 차단"), (TL.SKIP, "확인 중 오류"), (TL.OK, "x")])
        c = _Clock(datetime(2026, 11, 10, 21, 0))
        called = []
        rc = TS.run(accts, lambda m: None, lambda a, p, s: (called.append(a.account_id), next(seq))[1], out_dir=d,
                    passwords=lambda a: ([PW], "파일"), busy=lambda: "", now=c, sleep=c.sleep, fp=FP, gap=lambda: 50.0)
        assert rc == 1 and called == ["acc1", "acc2", "acc3"], (rc, called)
    with tempfile.TemporaryDirectory() as d:                 # 계정 하나에서 예외 = 건너뜀(무음 아님) · 멈춤 시각 뒤 새 계정 안 함
        c = _Clock(datetime(2026, 11, 11, 16, 0))
        called = []

        def work2(a, p, s):
            called.append(a.account_id)
            if a.account_id == "acc1":
                raise RuntimeError("브라우저 오류")
            c.sleep(7200)                             # 16:00 → acc2 끝 18:00 넘음 → acc3 은 시작 안 함
            return TL.OK, "x"
        rc = TS.run(accts, lambda m: None, work2, out_dir=d, passwords=lambda a: ([PW], "파일"), busy=lambda: "",
                    now=c, sleep=c.sleep, fp=FP, gap=lambda: 50.0)
        st = TL.load_state(d)
        assert rc == 0 and called == ["acc1", "acc2"], (rc, called)
        assert st["acc1"]["결과"] == TL.SKIP and "RuntimeError" in st["acc1"]["사유"], st["acc1"]
    ok("기다렸다 계속·비번 없음 기록·쉼 3번·지문만·제외 계정 그대로 · 차단+오류 2연속 중단 · 예외 = 건너뜀 · 17:40 뒤 새 계정 안 함")


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"PK-test")
    return p


def s4_reuse():
    print("[S4] 원장 정산 기록에 같은 파일 = 요청 안 하고 복사(계정ID 끝 + 대표자명·사업자명 같은 칸 · 기간·리포트 다르면 아님)")
    with tempfile.TemporaryDirectory() as d:
        main = Path(d) / "파일"
        a = SF.settle_file_name("홍길동-주식회사 가나-plan_it", date(2026, 1, 30), "윙", "주정산", "주문상세",
                                date(2026, 1, 5), date(2026, 1, 11))
        _touch(main / a)
        b = SF.settle_file_name("김-다른-it", date(2026, 1, 30), "윙", "주정산", "주문상세", date(2026, 1, 12),
                                date(2026, 1, 18))
        _touch(main / b)
        cost = SF.settle_file_name("홍길동-가나-plan_it", date(2026, 2, 9), "로켓그로스", "주정산", "입출고비",
                                   date(2026, 1, 26), date(2026, 2, 1))
        _touch(main / "비용" / cost)
        plan = ("홍길동", "(주)가나")              # 전환자 파일 대표자명·사업자명(원장 이름과 사업자 표기가 달라도 대표자로 맞음)
        its = ("김", "다른")
        mine = SF.settle_file_name("홍길동-(주)가나-plan_it", date(2026, 1, 30), "윙", "주정산", "주문상세",
                                   date(2026, 1, 5), date(2026, 1, 11))
        assert TS.find_reusable(main, "plan_it", plan, mine) == main / a
        other = SF.settle_file_name("홍길동-(주)가나-plan_it", date(2026, 1, 30), "윙", "주정산", "주문상세",
                                    date(2026, 1, 12), date(2026, 1, 18))
        assert TS.find_reusable(main, "plan_it", plan, other) is None, "'-it' 로 끝나는 다른 계정(김-다른-it) 파일은 아님"
        it_mine = SF.settle_file_name("김-다른-it", date(2026, 1, 30), "윙", "주정산", "주문상세", date(2026, 1, 5),
                                      date(2026, 1, 11))
        assert TS.find_reusable(main, "it", its, other.replace("홍길동-(주)가나-plan-it", "김-다른-it")) == main / b
        assert TS.find_reusable(main, "it", its, it_mine) is None, "plan_it 파일(대표자 다름)을 'it' 계정 것으로 잡지 않음"
        assert TS.find_reusable(main, "it", ("김앤코", ""), it_mine.replace("김-다른", "김앤코")) is None
        mycost = SF.settle_file_name("홍길동-(주)가나-plan_it", date(2026, 2, 9), "로켓그로스", "주정산", "입출고비",
                                     date(2026, 1, 26), date(2026, 2, 1))
        assert TS.find_reusable(main / "비용", "plan_it", plan, mycost) == main / "비용" / cost
        assert TS.find_reusable(main, "plan_it", plan, mycost) is None
        assert TS.find_reusable(Path(d) / "없음", "plan_it", plan, mine) is None
    ok("같은 계정·정산일·채널·유형·리포트·기간 + 대표자 일치 = 원장 파일 · '-it' 겹침 계정 구분 · 비용 폴더 따로 · 폴더 없음 = 없음")


def _ev(acct, ch, kind, sd, ps, pe, reports=()):
    return SJ.SettleEvent(acct, ch, kind, date.fromisoformat(sd), date.fromisoformat(ps), date.fromisoformat(pe),
                          tuple(reports), ref="k")


def s5_store_and_request():
    print("[S5] 저장 = output/정산_셀독전환/정산 · 지급 내역 2026-01-01~ · 계정당 30건 · 원장 파일 있으면 요청 안 함")
    import settlement_download as TD
    from coupang_analytics import settlement_runlog as RL
    from coupang_analytics import settlement_store as STORE
    saved = {k: getattr(TD, k) for k in ("BASE", "JOBS", "FILES", "COSTS", "AMOUNTS", "VERIFY", "AMOUNTS_FROM",
                                         "REUSE_FROM", "LOG", "read_events", "_request_one")}
    saved_store = {k: getattr(STORE, k) for k in ("BASE", "JOBS", "FILES", "COSTS", "AMOUNTS", "FORECAST", "VERIFY")}
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            assert TD.REUSE_FROM is None, "정산 계정(원장) 실행은 재사용 없음 — 지금 동작 그대로"
            TD._use_transfer_store()
            base = Path("output") / "정산_셀독전환" / "정산"
            assert TD.BASE == base and STORE.BASE == base and TD.JOBS == base / "_요청기록.json"
            assert TD.FILES == STORE.FILES == base / "파일" and TD.COSTS == base / "파일" / "비용"
            assert TD.AMOUNTS == STORE.AMOUNTS == base / "쿠팡지급내역" and STORE.FORECAST == base / "정산예정기록.jsonl"
            assert TD.VERIFY == base / "검증자료" and TD.AMOUNTS_FROM == TS.FROM == date(2026, 1, 1)
            assert TD.REUSE_FROM == Path("output") / "정산" / "파일"
            STORE.save_amounts("사업자1-acc1", "윙", [{"정산일": "2026-01-30", "기간 시작": "2026-01-05", "기간 끝": "2026-01-11",
                                                       "지급비율": 70, "최종지급액": 1000}])
            assert (base / "쿠팡지급내역" / "사업자1-acc1_윙.json").exists()
            assert not (Path("output") / "정산" / "쿠팡지급내역").exists(), "원장 정산 기록에 안 씀"
            name = TS.display_name(_accts(1)[0])
            assert name == "대표1-사업자1-acc1", name
            _touch(Path("output") / "정산" / "파일" / SF.settle_file_name(
                "대표1-원장 사업자명-acc1", date(2026, 1, 30), "윙", "주정산", "주문상세", date(2026, 1, 5), date(2026, 1, 11)))
            events = [_ev(name, "윙", "주정산", "2026-01-30", "2026-01-05", "2026-01-11")]
            events += [_ev(name, "윙", "주정산", (date(2026, 2, 6) + timedelta(days=7 * k)).isoformat(),
                           (date(2026, 1, 12) + timedelta(days=7 * k)).isoformat(),
                           (date(2026, 1, 18) + timedelta(days=7 * k)).isoformat()) for k in range(40)]
            asked_range, requested = [], []
            TD.read_events = lambda b, nm, s, e, amounts_from=None: (asked_range.append((s, amounts_from)), events)[1]
            TD._request_one = lambda b, j, nm: (requested.append(j.period_start), f"r{len(requested)}")[1]
            TD.LOG = RL.RunLog(TD.BASE, echo=lambda m: None)

            class A:
                pass
            args = A()
            args.start, args.end, args.cap, args.dry_run, args.until, args.until_at = (
                date(2026, 1, 1), date(2026, 11, 10), 500, False, "", None)
            TS.apply_args(args)
            assert args.cap == TS.CAP == 30 and args.start == TS.FROM
            jobs: list = []
            import time as _t
            real_sleep, TD.time.sleep = _t.sleep, lambda s: None
            # S5 는 요청·재사용 로직만 검증(멈춤 시각 past_until 은 S3 가 모킹된 now 로 덮음) → 여기선 벽시계 의존을 없앤다.
            # 안 그러면 게이트가 17:40(UNTIL_DEFAULT) 이후에 돌 때 cmd_request 가 첫 요청 전 break 해 requested 가 빈다(실측 11-10 17:54).
            real_past_until, TD.past_until = TD.past_until, lambda a: False
            try:
                TD.cmd_request(TS.settle_account(_accts(1)[0]), None, args, jobs)
            finally:
                TD.time.sleep = real_sleep
                TD.past_until = real_past_until
            assert asked_range == [(date(2026, 1, 1), date(2026, 1, 1))], asked_range
            assert len(requested) == 30 and "2026-01-05" not in requested, (len(requested), requested[:3])
            reused = [j for j in jobs if j.period_start == "2026-01-05"]
            assert reused and reused[0].status == SJ.ST_DONE and reused[0].file, reused
            assert (TD.FILES / reused[0].file).exists() and reused[0].file.startswith("대표1-사업자1-acc1_")
            assert any(r["단계"] == "받기" and "원장" in r["사유"] for r in TD.LOG.rows), TD.LOG.rows
            saved_jobs = SJ.load_jobs(TD.JOBS)
            assert len([j for j in saved_jobs if j.status == SJ.ST_REQUESTED]) == 30
        finally:
            os.chdir(cwd)
            for k, v in saved.items():
                setattr(TD, k, v)
            for k, v in saved_store.items():
                setattr(STORE, k, v)
    ok("경로 7개 전환·원장 폴더 안 씀 · 조회 2026-01-01~ · 41건 중 원장 파일 1건 복사(요청 안 함) · 요청 30건(상한)")


def _xlsx(path: Path, grid: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    for r in grid:
        wb.active.append(r)
    wb.save(path)
    return path


def _wing_row(order, pid, name, oid, opt, price, qty, fee, settle, rec="2026-01-08"):
    v = dict.fromkeys(WING_HDR, "")
    v.update({"주문번호": order, "과세유형": "TAX", "상품 ID": pid, "상품명": name, "옵션 ID": oid, "옵션명": opt,
              "판매가": str(price), "판매수량": qty, "환불수량": 0, "판매액": str(price * qty), "판매자 할인쿠폰(A+B)": "0",
              "판매수수료": str(fee), "마이샵수수료할인": "0", "정산금액": str(settle), "구매확정일": rec,
              "구매확정(출고)유형": "수동", "정산예정일": "2026-01-30"})
    return [v[h] for h in WING_HDR]


def _rg_row(order, pid, oid, name, opt, price, qty, fee, vat, cycle="2026-01-11"):
    v = dict.fromkeys(RG_HDR, "")
    v.update({"정산유형": "주정산", "정산주기(종료일)": cycle, "매출인식일": "2026-01-07", "주문ID": order, "거래유형": "주문 정산",
              "등록상품 ID": pid, "옵션ID": oid, "등록상품명": name, "옵션명": opt, "판매가(A)": price, "판매수량(B)": qty,
              "판매액(A*B)": price * qty, "쿠팡지원할인(C)": 0, "매출금액(A*B-C)": price * qty, "판매자할인쿠폰(D+E)": 0,
              "정산대상액": price * qty - fee - vat, "판매수수료": fee, "판매수수료 VAT": vat})
    return [v[h] for h in RG_HDR]


def s6_cumulative():
    print("[S6] 누적 파일 — 시트 4개 · 상품 칸 = 쿠팡 파일 원본 · 돈 = 지급 내역 · 다시 만들어도 같음 · 비번 없음 · 열려 있으면 오류")
    accts = _accts(3)
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "정산"
        n1 = TS.display_name(accts[0])
        assert n1 == "대표1-사업자1-acc1", n1
        _xlsx(store / "파일" / SF.settle_file_name(n1, date(2026, 1, 30), "윙", "주정산", "주문상세", date(2026, 1, 5),
                                                   date(2026, 1, 11)),
              [WING_HDR, _wing_row("1001", "8358672052", "웰빙곳간 그린스틱", "92285508987", "그린스틱, 1개, 30회분",
                                   10690, 1, 1246, 9444),
               _wing_row("1001", "", "", "<기본배송료>", "", 0, 0, 0, 0)])
        _xlsx(store / "파일" / SF.settle_file_name(n1, date(2026, 1, 30), "로켓그로스", "주정산", "판매수수료",
                                                   date(2026, 1, 5), date(2026, 1, 11)),
              [[None] * len(RG_HDR), RG_HDR, _rg_row("2001", "15486616195", "92733163987", "커큐민 120정", "1개 120정",
                                                     18500, 1, 1961, 196)])
        _touch(store / "파일" / "비용" / SF.settle_file_name(n1, date(2026, 1, 30), "로켓그로스", "주정산", "입출고비",
                                                            date(2026, 1, 5), date(2026, 1, 11)))
        amounts = store / "쿠팡지급내역"
        amounts.mkdir(parents=True)
        (amounts / f"{SF._token(n1, '계정명')}_윙.json").write_text(json.dumps([
            {"정산일": "2026-01-30", "기간 시작": "2026-01-05", "기간 끝": "2026-01-11", "지급비율": 70, "최종지급액": 6611,
             "지급상태": "PAID"},
            {"정산일": "2026-02-27", "기간 시작": "2026-01-01", "기간 끝": "2026-01-31", "지급비율": 30, "최종지급액": 2833,
             "지급상태": "PAID"}], ensure_ascii=False), encoding="utf-8")
        SJ.save_jobs(store / "_요청기록.json", [SJ.Job(n1, "윙", "주정산", "주문상세", "2026-01-12", "2026-01-18",
                                                      "2026-02-06", status=SJ.ST_REQUESTED)])
        state = {"acc1": {"결과": TL.OK, "사유": "로그인 됨"}, "acc2": {"결과": TL.FAIL, "사유": "로그인 비밀번호 오류"}}
        out = Path(d) / "누적.xlsx"
        p = TS.build_cumulative(accts, state, store, out, datetime(2026, 11, 10, 21, 0))
        assert p == out and out.exists()
        wb = openpyxl.load_workbook(out, read_only=True)
        assert wb.sheetnames == ["안내", "계정별 요약", "지급 내역", "상품별 정산"], wb.sheetnames
        summ = [list(r) for r in wb["계정별 요약"].iter_rows(values_only=True)]
        pay = [list(r) for r in wb["지급 내역"].iter_rows(values_only=True)]
        prod = [list(r) for r in wb["상품별 정산"].iter_rows(values_only=True)]
        text = json.dumps([[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets],
                          ensure_ascii=False, default=str)
        wb.close()
        h = summ[0]
        r1 = dict(zip(h, summ[1]))
        assert [x[h.index("계정명")] for x in summ[1:]] == ["acc1", "acc2", "acc3"], summ
        assert r1["로그인 결과"] == TL.OK and r1["지급 줄"] == 2 and r1["최종지급액 합"] == 9444, r1
        assert r1["정산 파일"] == 2 and r1["비용 리포트"] == 1 and r1["상품 줄"] == 2 and r1["남은 요청"] == 1, r1
        assert r1["마지막 정산일"] == "2026-02-27", r1
        assert dict(zip(h, summ[2]))["로그인 결과"] == TL.FAIL and dict(zip(h, summ[3]))["로그인 결과"] == "미확인"
        ph = pay[0]
        assert [dict(zip(ph, x))["최종지급액"] for x in pay[1:]] == [6611, 2833], pay
        assert dict(zip(ph, pay[1]))["사업자명"] == "사업자1" and dict(zip(ph, pay[1]))["채널"] == "윙"
        qh = prod[0]
        for col in ("상품 ID", "옵션 ID(VID)", "상품명", "옵션명", "정산 유형", "정산일", "주문번호", "정산금액", "파일"):
            assert col in qh, (col, qh)
        rows = [dict(zip(qh, x)) for x in prod[1:]]
        w = next(x for x in rows if x["채널"] == "윙")
        g = next(x for x in rows if x["채널"] == "로켓그로스")
        assert (w["상품 ID"], w["옵션 ID(VID)"], w["상품명"], w["옵션명"]) == (
            "8358672052", "92285508987", "웰빙곳간 그린스틱", "그린스틱, 1개, 30회분"), w
        assert (g["상품 ID"], g["옵션 ID(VID)"], g["상품명"], g["정산금액"]) == ("15486616195", "92733163987", "커큐민 120정",
                                                                         18500 - 1961 - 196), g
        assert len(rows) == 2, "0원 배송비 보조줄은 상품 줄 아님"
        assert PW not in text and "010-1" not in text, "비밀번호·연락처 없음"
        TS.build_cumulative(accts, state, store, out, datetime(2026, 11, 10, 21, 0))
        wb = openpyxl.load_workbook(out, read_only=True)
        assert len(list(wb["상품별 정산"].iter_rows(values_only=True))) == len(prod)
        wb.close()
        real = os.replace

        def locked(src, dst):
            raise PermissionError(13, "다른 프로그램이 사용 중")
        os.replace = locked
        try:
            try:
                TS.build_cumulative(accts, state, store, out, datetime(2026, 11, 10, 21, 0))
                raise AssertionError("열려 있으면 오류여야 함")
            except TS.CumulativeLocked as exc:
                assert str(out) in str(exc)
        finally:
            os.replace = real
        assert not list(Path(d).glob("*.tmp*")), "임시 파일 남지 않음"
    ok("시트 4개·요약(지급 2줄 9,444·파일 2·비용 1·상품 2·남은 요청 1·미확인)·상품 칸 원본 그대로·다시 만들어도 같음·열림 = 오류")


def s7_launch():
    print("[S7] 띄우기 — 18:00 무인·재부팅 복구 앱이 정산 자동 수집과 함께(--parent) · 탭 버튼")
    from coupang_analytics import app_process as AP
    cmd, _cwd = AP.transfer_settle_cmd(4321)
    assert cmd[-3:] == ["transfer-settle", "--parent", "4321"], cmd
    assert cmd[-4].endswith("settlement_download.py") or cmd[-4].endswith(AP.SETTLE_EXE), cmd
    src = (ROOT / "ui" / "app_qt.py").read_text(encoding="utf-8")
    i = src.index("if auto or resume:              # D-021")
    block = src[i:src.index("win = App(", i)]
    assert "start_transfer_settle" in block and "daily_on()" in block, block
    panel = (ROOT / "ui" / "transfer_panel_qt.py").read_text(encoding="utf-8")
    assert "start_transfer_settle" in panel and "DAILY_KEY" in panel
    ok("명령 = transfer-settle --parent PID · 18:00/재부팅 복구 블록에서 매일 설정이 켜져 있으면 띄움 · 탭 버튼·매일 체크")


def s8_one_at_a_time():
    print("[S8] 같은 잠금 — 1단계(로그인 확인)·2단계(정산 자료 받기) 한 번에 하나")
    assert TS.RUN_LOCK is TL.RUN_LOCK and TL.RUN_LOCK == TL.OUT_DIR / "_잠금" / "_실행.lock"
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            lines: list[str] = []
            with registry_lock(TL.RUN_LOCK, wait_sec=0):
                class A:
                    file, accounts, hidden, start, parent = str(Path(d) / "없음.xlsx"), "", True, "", 0
                rc = TS.main_cli(A(), lambda a, p, s: (TL.OK, ""), lines.append)
                rc2 = TL.main_cli(type("B", (), {"file": str(Path(d) / "없음.xlsx"), "accounts": "", "hidden": True,
                                                 "start": "", "retry": False, "until": "17:40"})())
            assert rc == 2 and any("셀독전환" in m and "도는 중" in m for m in lines), (rc, lines)
            tl_log = "".join(p.read_text(encoding="utf-8") for p in (Path(d) / TL.OUT_DIR / "로그").glob("로그인확인_*.log"))
            assert rc2 == 2 and "다른 셀독전환 실행" in tl_log and "파일 오류" not in tl_log, tl_log
        finally:
            os.chdir(cwd)
    ok("잠금이 잡혀 있으면 2단계·1단계 모두 시작 안 함(종료 코드 2)")


def main() -> int:
    s1_targets()
    s2_wait()
    s3_run()
    s4_reuse()
    s5_store_and_request()
    s6_cumulative()
    s7_launch()
    s8_one_at_a_time()
    print("셀독전환자 정산 자료 받기(2단계) 오프라인 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
