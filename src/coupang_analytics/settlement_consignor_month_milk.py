"""위탁자 정산서 3차 형식 — 7 밀크런을 쿠팡이 뺀 지급 줄 찾기(T-179 ⑩). `settlement_consignor_month_cost.milkrun` 이 부름 · 순수 함수.

쿠팡 달 표시(milkRunOffsetYearMonthBreakdown)는 밀크런 달이 아니라 공제한 지급 줄의 판매 달 → 이 달 파일 합과 원 단위로 같은 공제를 찾음.
쿠팡은 한 달 밀크런을 지급액이 모자라면 다음 지급으로 넘겨 여러 지급일에 나눠 뺌(실측 output44 = 나눠 뺀 합과 파일 합이 원 단위로 같음).
① 한 지급일의 합 ② 지급 순서로 이어진 줄(다른 달에 안 쓴 줄)의 합 = 그 달 파일 합 ③ 이어진 달 묶음의 파일 합 = 이어진 줄의 합(한 지급 줄에 두 달 몫이
섞임 → 지급 순서대로 앞 달부터 채움 · 광고 D-289 ② 와 같은 누적). 원 단위로 안 맞으면 찾지 않음(호출부가 '확인 필요').
"""
from __future__ import annotations


def _runs(left: list, first_month: str, want: int):
    """left = [(key, 금액)] 지급 순서 — 그 달이 끝난 뒤 지급 줄부터 이어진 줄의 합이 want 와 같은 구간(앞에서부터)."""
    for i, (key, _a) in enumerate(left):
        if str(key[0]) <= f"{first_month}-31":
            continue
        acc = 0
        for j in range(i, len(left)):
            acc += left[j][1]
            if acc == want:
                yield left[i:j + 1]
                break


def _fill(months: list, files: dict, run: list) -> dict | None:
    """이어진 줄을 앞 달부터 채움 → {달: [(key, 몫)]} · 그 달이 끝나기 전 지급 줄이 들어가면 None."""
    out: dict = {}
    rest = [list(x) for x in run]
    for m in months:
        need, out[m] = files[m], []
        while need:
            part = min(rest[0][1], need)
            out[m].append((rest[0][0], part))
            need -= part
            rest[0][1] -= part
            if not rest[0][1]:
                rest.pop(0)
        if any(str(key[0]) <= f"{m}-31" for key, _a in out[m]):
            return None
    return out


def _one_day(m: str, want: int, left: list) -> list:
    """한 지급일의 공제 합 = 파일 합(빠른 지급일부터)."""
    for day in sorted({str(key[0]) for key, _a in left if str(key[0]) > f"{m}-31"}):
        xs = [x for x in left if str(x[0][0]) == day]
        if sum(a for _key, a in xs) == want:
            return xs
    return []


def _match(group: list, want: dict, left: list) -> tuple[dict, list]:
    """이어진 달 묶음 ↔ 이어진 지급 줄 → ({달: [(key, 몫)]}, 쓴 줄) · 못 찾음 = ({}, [])."""
    for run in _runs(left, group[0], sum(want[m] for m in group)):
        if len(group) == 1:
            return {group[0]: run}, run
        filled = _fill(group, want, run) if all(a > 0 for _key, a in run) else None
        if filled:
            return filled, run
    return {}, []


def milk_months(files: dict, lines: list) -> dict:
    """files = {밀크런 달 'YYYY-MM': 파일 합} · lines = [(지급 줄 key(지급일, 시작, 끝, …), 밀크런 공제)] → {달: [(key, 몫)]}(몫 합 = 파일 합 · 못 찾은 달 없음)."""
    want = {m: round(x) for m, x in sorted(files.items()) if round(x)}
    left = sorted(((key, round(a)) for key, a in lines if round(a)), key=lambda x: [str(k) for k in x[0]])
    got: dict = {}
    for m, x in want.items():
        got[m] = _one_day(m, x, left)
        left = [y for y in left if y not in got[m]]
    got = {m: xs for m, xs in got.items() if xs}
    months = list(want)
    for n in range(1, len(months) + 1):                        # 달 하나 → 이어진 달 묶음(작은 것부터)
        for group in (months[i:i + n] for i in range(len(months) - n + 1)):
            if any(m in got for m in group):
                continue
            filled, run = _match(group, want, left)
            got.update(filled)
            left = [y for y in left if y not in run]
    return got
