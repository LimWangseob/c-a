r"""정산 표본 전후 계산 시험 도구(S1 · D-353) — 계정 자료를 한 번 읽어 이 PC 에 계산용 복사본(pickle)으로 저장하고,
옛 코드(src 폴더 A)·새 코드(src 폴더 B)가 같은 저장 자료로 계산만 다시 해 전후 금액을 비교한다. 정산서·앱은 이 파일을 안 씀(시험 도구만).

    python tools/settlement_sample.py cache --name output38 --accounts seankim137 --managed-output <output> --settle-dir <output\정산>
        --stats <정산집계.xlsx> --basis 2026-11-15 --inputs <입력 폴더> --issued 2026-11-16 [--settle-only <json>]
    python tools/settlement_sample.py run --name output38 --src <src 폴더> --out 후.json [--kind both|old|new] [--direct]
    python tools/settlement_sample.py diff 전.json 후.json [--paths 30]
    python tools/settlement_sample.py ab --name output38 --old-src <src A> --new-src <src B> --out-dir <폴더>   # run 2번 + diff → 전후.txt

- 저장 경계 = `settlement_statement_context.load()` 결과(ctx · 정산서 계산 직전 공통 자료). 계산 = 옛 엑셀 위탁정산서
  `settlement_statement_deduct.account` + `shown`·`summary_row`(1쪽·요약 숫자) · 새 위탁자 정산서 `settlement_consignor_month.account_source`
  + 판매 달마다 `build_month`. 계산 중에 읽는 파일(광고 보고서 등)은 매번 원래 파일에서 읽음(저장 안 함 = 늘 최신).
- 저장 위치 = 본 저장소 `output\_표본캐시\<이름>\`(git 밖 · worktree 에서도 본 저장소) · `--cache-root` 로 바꿈.
- 자동 다시 읽기 ① 원래 파일 지문(경로·크기·수정 시각 · 폴더 이름 목록)이 다르면 ② 고르는 src 의 읽기 코드(읽는 동안 돈 src 파일 내용)가
  저장 때와 다르면 → 그 src 로 다시 읽어 새로 저장(사유 출력). 네트워크 = 막음(감사 훅 · 구글시트 실시간 읽기는 ❌).
- 계정 = 1~2개 권장(41계정 전체는 이 도구 범위 밖 · 메모리). 결과 json = {"old": {계정ID: …}, "new": {"계정ID YYYY-MM": …}, "오류": {…}}.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import pickle
import subprocess
import sys
import time
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import settlement_sample_track as TR  # noqa: E402

ARG_PATHS = ("managed_output", "settle_dir", "stats", "inputs", "settle_only", "supp", "snap")
ARG_TEXT = ("basis", "issued")
CTX_OUT = "ctx_out"          # CTX.load 가 쓰는 출력 폴더(사업자_대응표.csv) — 저장 폴더 안 · 지문에서 뺌
META = "meta.json"
MAX_ACCOUNTS = 2


def main_checkout(root: Path = ROOT) -> Path:
    """worktree 면 본 저장소 폴더(.git 파일의 gitdir → …/.git/worktrees/<이름> 의 두 단계 위) · 아니면 그대로."""
    g = root / ".git"
    if g.is_file():
        return Path(g.read_text(encoding="utf-8").split(":", 1)[1].strip()).parents[2]
    return root


def default_cache_root() -> Path:
    return main_checkout() / "output" / "_표본캐시"


# ── 읽기·계산 묶음(Kit) — 실제 = src 폴더의 정산 모듈 · 시험 = 합성 함수 ─────────────────────────────────

@dataclass
class Kit:
    src: Path
    load: Callable          # (args dict, 출력 폴더) → ctx
    compute: Callable       # (ctx, 계정ID 목록, kind) → {"old"|"new": {...}, "오류": {...}}


def real_kit(src: Path) -> Kit:
    """src 폴더의 coupang_analytics 를 불러 묶음 — 한 프로세스에 src 하나(다른 src = 다른 프로세스 · `ab` 가 나눠 돌림)."""
    src = Path(src).resolve()
    if not (src / "coupang_analytics" / "__init__.py").is_file():
        raise SystemExit(f"❌ src 폴더가 아님(coupang_analytics 없음): {src}")
    TR.install(block_network=True)
    sys.path.insert(0, str(src))
    loaded = [m for m in sys.modules if m == "coupang_analytics" or m.startswith("coupang_analytics.")]
    for m in loaded:
        if not str(getattr(sys.modules[m], "__file__", "") or "").startswith(str(src)):
            raise SystemExit(f"❌ 다른 src 의 모듈이 이미 불러짐: {m} — src 마다 프로세스를 나눠 돌릴 것")
    gs = importlib.import_module("coupang_analytics.gsheet_api")
    setattr(gs, "GSheetClient", _NoNet)
    ctx_mod = importlib.import_module("coupang_analytics.settlement_statement_context")

    def load(args: dict, out: Path):
        kw = {k: (Path(v) if v and k in ARG_PATHS else v) for k, v in args.items() if v is not None}   # 빈 칸 = 기본값(옛 저장분의 없어진 칸 포함)
        return ctx_mod.load(ctx_mod.StatementArgs(out=out, **kw))

    return Kit(src=src, load=load, compute=lambda ctx, accts, kind: _real_compute(ctx, accts, kind))


class _NoNet:
    def __init__(self, *a, **k):
        raise TR.NetworkBlocked("네트워크 금지(표본 시험 도구) — 구글시트 실시간 읽기 대신 --settle-only 사본을 줄 것")


def _real_compute(ctx, accts: list, kind: str) -> dict:
    CM = importlib.import_module("coupang_analytics.settlement_consignor_month")
    SRC = importlib.import_module("coupang_analytics.settlement_statement_source")
    DED = importlib.import_module("coupang_analytics.settlement_statement_deduct")
    SH = importlib.import_module("coupang_analytics.settlement_statement_sheets")
    BK = importlib.import_module("coupang_analytics.settlement_statement_book")
    names = {SRC.aid_of(a): a for a in ctx.accts}
    miss = [x for x in accts if x not in names]
    if miss:
        raise SystemExit(f"❌ 정산집계에 없는 계정ID: {miss}")
    out: dict = {kind: {}, "오류": {}}
    judge = CM.load_judge(inputs=ctx.args.inputs) if kind == "new" else None
    for aid in accts:
        try:
            if kind == "old":
                a = DED.account(ctx, names[aid])
                v = SH.shown(a)
                out["old"][aid] = {"요약": dict(zip(BK.SUM_HDR, BK.summary_row(a, v))), "1쪽": v, "자료": a}
                continue
            s = CM.account_source(ctx, names[aid])
        except Exception as e:  # noqa: BLE001 — 표본 기록용: 어느 src 가 깨지는지 그대로 결과에 남기고 끝 코드 1
            out["오류"][f"{kind} {aid}"] = repr(e)
            continue
        for m in CM.sale_months(s):
            try:
                out["new"][f"{aid} {m}"] = CM.build_month(None, s, m, judge)
            except Exception as e:  # noqa: BLE001 — 위와 같음(달 단위)
                out["오류"][f"new {aid} {m}"] = repr(e)
    return out


# ── 저장 자료 ─────────────────────────────────────────────────────────────────────────────

class Store:
    """<cache-root>/<이름>/meta.json(args·계정·entries) + ctx_<n>.pkl · entry = 읽기 코드 지문·원래 파일 지문·만든 src·읽은 시간."""

    def __init__(self, root: Path, name: str):
        if not name or any(c in name for c in '\\/:*?"<>|'):
            raise SystemExit(f"❌ 저장 이름이 맞지 않음: {name!r}")
        self.dir = Path(root) / name

    @property
    def meta_path(self) -> Path:
        return self.dir / META

    def meta(self) -> dict:
        if not self.meta_path.is_file():
            raise SystemExit(f"❌ 저장 자료 없음: {self.dir} — 먼저 cache 명령")
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def write_meta(self, meta: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.meta_path)

    def save_entry(self, meta: dict, entry: dict, ctx) -> None:
        keep = [e for e in meta.get("entries", []) if e["code"] != entry["code"]]
        for e in meta.get("entries", []):
            if e["code"] == entry["code"]:
                (self.dir / e["pkl"]).unlink(missing_ok=True)
        n = 1 + max([int(e["pkl"][4:-4]) for e in meta.get("entries", [])] or [0])
        entry["pkl"] = f"ctx_{n}.pkl"
        tmp = self.dir / (entry["pkl"] + ".tmp")
        with open(tmp, "wb") as f:
            TR.dump(ctx, f)
        os.replace(tmp, self.dir / entry["pkl"])
        entry["pkl_bytes"] = (self.dir / entry["pkl"]).stat().st_size
        meta["entries"] = keep + [entry]
        self.write_meta(meta)

    def load_ctx(self, entry: dict):
        with open(self.dir / entry["pkl"], "rb") as f:
            return pickle.load(f)


def read_fresh(kit: Kit, store: Store, meta: dict):
    """원래 파일에서 읽기(지문 기록) → (ctx, entry). 저장 폴더(ctx_out 포함)·src 는 지문에서 뺌."""
    out = store.dir / CTX_OUT
    t = time.time()
    with TR.Reads(exclude=(store.dir, kit.src)) as rd, TR.CodeRun(kit.src) as cr:
        ctx = kit.load(meta["args"], out)
    secs = round(time.time() - t, 1)
    entry = {"code": TR.code_sig(kit.src, sorted(cr.files)), "fp": TR.fingerprint(rd.files(), rd.dirs()),
             "src": str(kit.src), "python": sys.version, "saved": datetime.now().isoformat(timespec="seconds"), "read_s": secs}
    return ctx, entry


def pick(kit: Kit, store: Store, meta: dict) -> tuple[dict | None, list[str]]:
    """이 src 에 맞는 저장 자료(entry) 또는 None + 다시 읽는 사유. 읽기 코드가 같은 entry 중 원래 파일 지문이 그대로인 것."""
    why = []
    for e in meta.get("entries", []):
        if e.get("python") != sys.version:
            why.append(f"파이썬 판 다름({e['pkl']} · {e.get('python')})")
            continue
        diff = [rel for rel, h in TR.code_sig(kit.src, list(e["code"])).items() if h != e["code"][rel]]
        if diff:
            why.append(f"읽기 코드 다름({e['pkl']} · {', '.join(diff[:5])}{' …' if len(diff) > 5 else ''})")
            continue
        ch = TR.changed(e["fp"])
        if ch:
            why.append(f"원래 자료 바뀜({e['pkl']} · {len(ch)}곳: {'; '.join(ch[:3])}{' …' if len(ch) > 3 else ''})")
            continue
        return e, why
    return None, why or ["저장 자료 없음"]


def ensure_entry(kit: Kit, store: Store, log: Callable = print) -> dict:
    """이 src 에 맞는 저장 자료가 있으면 그대로, 없으면(파일·읽기 코드 바뀜 포함) 다시 읽어 저장 → entry."""
    meta = store.meta()
    e, why = pick(kit, store, meta)
    if e is not None:
        log(f"저장 자료 사용 {e['pkl']}(처음 읽기 {e['read_s']}s · {e['saved']} · src {e['src']})")
        return e
    log("다시 읽음 — " + " / ".join(why))
    ctx, e = read_fresh(kit, store, meta)
    store.save_entry(meta, e, ctx)
    del ctx
    log(f"읽기 {e['read_s']}s · 저장 {e['pkl']} {e['pkl_bytes'] / 1e6:.0f}MB · 원래 파일 {len(e['fp']['files'])}개 · 폴더 {len(e['fp']['dirs'])}개")
    return e


def compute_all(kit: Kit, fresh_ctx: Callable, accts: list, kinds: list, log: Callable = print) -> dict:
    """kind 마다 새로 푼 ctx 로 계산(한 계산이 ctx 를 바꿔도 다른 계산에 안 번짐 · 정산서 도구 2개가 따로 도는 것과 같게)."""
    res: dict = {"old": {}, "new": {}, "오류": {}}
    for kind in kinds:
        t = time.time()
        ctx = fresh_ctx()
        part = kit.compute(ctx, accts, kind)
        del ctx
        res[kind].update(part.get(kind, {}))
        res["오류"].update(part.get("오류", {}))
        log(f"계산 {kind} {time.time() - t:.1f}s · {len(part.get(kind, {}))}건 · 오류 {len(part.get('오류', {}))}")
    return res


def run(kit: Kit, store: Store, kinds: list, direct: bool = False, log: Callable = print) -> dict:
    """direct = 저장 자료(pickle)를 전혀 거치지 않고 계산마다 원래 파일에서 바로 읽음(시험 ① 기준값 · 저장 안 함 · 읽기 시간 × kind 수)."""
    meta = store.meta()
    if direct:
        def read():
            t = time.time()
            ctx = kit.load(meta["args"], store.dir / CTX_OUT)
            log(f"바로 읽기 {time.time() - t:.1f}s(저장 안 함)")
            return ctx
        return compute_all(kit, read, meta["accounts"], kinds, log)
    e = ensure_entry(kit, store, log)

    def fresh():
        t = time.time()
        ctx = store.load_ctx(e)
        log(f"불러오기 {time.time() - t:.1f}s")
        return ctx
    return compute_all(kit, fresh, meta["accounts"], kinds, log)


# ── json 으로 옮기기 · 비교 ──────────────────────────────────────────────────────────────────

def plain(x, depth: int = 0):
    """결과 → json 값(결정적): set = 정렬 목록 · tuple = 목록 · dict 키 = 글자 · dataclass·객체 = 칸 사전(+형 이름) · 나머지 = str."""
    if depth > 60:
        raise ValueError("결과가 너무 깊음(순환 참조 의심)")
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, dict):
        return {str(k): plain(v, depth + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v, depth + 1) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((plain(v, depth + 1) for v in x), key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
    if is_dataclass(x):
        return {"__형": type(x).__name__, **{f.name: plain(getattr(x, f.name), depth + 1) for f in fields(x)}}
    if hasattr(x, "__dict__"):
        return {"__형": type(x).__name__, **{k: plain(v, depth + 1) for k, v in vars(x).items()}}
    return str(x)


def write_json(res: dict, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(plain(res), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def _items(xs: list | None, key: str) -> dict:
    return {f"{i + 1}. {x.get('name', x.get('date', ''))}" if isinstance(x, dict) else str(i + 1): (x.get(key) if isinstance(x, dict) else x)
            for i, x in enumerate(xs or [])}


def money_new(d: dict) -> dict:
    """새 위탁자 정산서 금액 칸 — 정산 금액 · 확정 전 · 1~8 · 9 반영 · 10 · 날짜별 입금 · 어디로 갔나요 · 상품 소계."""
    if "오류" in d:
        return {"오류": d["오류"]}
    out = {"정산 금액": d.get("settle_amount"), "확정 전": d.get("pending_total"), "9 반영": (d.get("common") or {}).get("total_applied")}
    for label, key, k in (("1~8", "lines", "amount"), ("10", "separate", "amount"), ("날짜별", "deposits", "amount"),
                          ("어디로", "flow", "amount"), ("상품 소계", "products", "subtotal")):
        for i, v in _items(d.get(key), k).items():
            out[f"{label} {i}"] = v
    return out


def money_old(d: dict) -> dict:
    """옛 엑셀 위탁정산서 금액 칸 — 전체 요약 한 줄(SUM_HDR) 중 숫자·일치 칸 + 1쪽 숫자(shown)."""
    out = {f"요약 {k}": v for k, v in (d.get("요약") or {}).items() if isinstance(v, (int, float)) or k.startswith("정산 100%")}
    out.update({f"1쪽 {k}": v for k, v in (d.get("1쪽") or {}).items() if isinstance(v, (int, float))})
    return out


def walk(a, b, path: str, out: list) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"추가 `{path}.{k}`")
            elif k not in b:
                out.append(f"삭제 `{path}.{k}`")
            else:
                walk(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"변경 `{path}`: {json.dumps(a, ensure_ascii=False)[:150]} → {json.dumps(b, ensure_ascii=False)[:150]}")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def money_rows(x: dict | None, y: dict | None, kind: str) -> list[tuple]:
    """금액 칸 바뀐 줄 [(칸, 전, 후, 차이)] — 한쪽에만 있는 칸 포함."""
    f = money_old if kind == "old" else money_new
    a, b = f(x or {}), f(y or {})
    rows = []
    for k in list(dict.fromkeys(list(a) + list(b))):
        u, v = a.get(k), b.get(k)
        if u != v:
            rows.append((k, u, v, (v or 0) - (u or 0) if (_num(u) or u is None) and (_num(v) or v is None) else ""))
    return rows


def _fmt(v) -> str:
    if _num(v):
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
    return "—" if v is None else str(v)[:80]


def _diff_kind(a: dict, b: dict, kind: str, title: str, paths: int) -> tuple[list, int]:
    keys = sorted(set(a) | set(b))
    if not keys:
        return [], 0
    lines, total, same = [f"## {title} — {len(keys)}건"], 0, []
    for key in keys:
        rows = money_rows(a.get(key), b.get(key), kind)
        other: list = []
        walk(a.get(key), b.get(key), "", other)
        if not rows and not other:
            same.append(key)
            continue
        total += len(rows)
        lines.append(f"### {key} — 금액 칸 변화 {len(rows)} · 바뀐 경로 {len(other)}")
        if rows:
            lines += ["| 칸 | 전 | 후 | 차이 |", "|---|---:|---:|---:|"]
            lines += [f"| {k} | {_fmt(u)} | {_fmt(v)} | {_fmt(dv)} |" for k, u, v, dv in rows]
        lines += [f"- {p}" for p in other[:paths]] + ([f"- … 외 {len(other) - paths}곳"] if len(other) > paths else [])
    lines.append(f"- 전부 같음 {len(same)}건: {', '.join(same)}" if same else "- 전부 같은 건 없음")
    return lines, total


def diff(old: dict, new: dict, paths: int = 30) -> tuple[str, int]:
    """두 결과 json → (전후 표 글, 금액 칸 바뀐 수). 표 = 금액 칸만 · 그 밑에 금액 밖 바뀐 경로(앞 paths 개) · 양쪽 오류."""
    lines, total = [], 0
    for kind, title in (("old", "옛 엑셀 위탁정산서(settlement_statement_*)"), ("new", "새 위탁자 정산서(settlement_consignor_month*)")):
        part, n = _diff_kind(old.get(kind) or {}, new.get(kind) or {}, kind, title, paths)
        lines += part
        total += n
    for tag, d in (("전", old), ("후", new)):
        lines += [f"- ❌ {tag} 오류 {k}: {v}" for k, v in (d.get("오류") or {}).items()]
    return "\n".join(lines), total


# ── 명령줄 ───────────────────────────────────────────────────────────────────────────────

def _accounts(text: str) -> list[str]:
    accts = list(dict.fromkeys(x.strip() for x in text.split(",") if x.strip()))
    if not accts:
        raise SystemExit("❌ --accounts 비었음(계정ID 1~2개)")
    if len(accts) > MAX_ACCOUNTS:
        raise SystemExit(f"❌ 계정 {len(accts)}개 — 이 도구는 {MAX_ACCOUNTS}개까지(전체 계정 실행 금지 · 메모리)")
    return accts


def new_meta(store: Store, args: dict, accts: list) -> dict:
    """저장 이름의 인자·계정을 정함 — 같으면 저장 자료 유지 · 다르면 옛 저장 자료(pkl) 지우고 새로."""
    meta = {"args": args, "accounts": accts, "entries": []}
    if store.meta_path.is_file():
        old = store.meta()
        if (old["args"], old["accounts"]) == (args, accts):
            meta["entries"] = old.get("entries", [])
        else:
            for e in old.get("entries", []):
                (store.dir / e["pkl"]).unlink(missing_ok=True)
    store.write_meta(meta)
    return meta


def cmd_cache(a: argparse.Namespace) -> int:
    store = Store(a.cache_root, a.name)
    accts = _accounts(a.accounts)
    args: dict = {k: (str(Path(getattr(a, k)).resolve()) if getattr(a, k) else None) for k in ARG_PATHS}
    args.update({k: getattr(a, k) for k in ARG_TEXT})
    args["only"] = accts
    new_meta(store, args, accts)
    ensure_entry(real_kit(a.src), store)
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    kinds = ["old", "new"] if a.kind == "both" else [a.kind]
    res = run(real_kit(a.src), Store(a.cache_root, a.name), kinds, direct=a.direct)
    write_json(res, a.out)
    print(f"결과 {a.out}")
    for k, v in res["오류"].items():
        print(f"❌ 오류 {k}: {v}")
    return 1 if res["오류"] else 0


def cmd_diff(a: argparse.Namespace) -> int:
    old, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (a.old, a.new))
    text, n = diff(old, new, a.paths)
    if a.save:
        Path(a.save).write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\n금액 칸 바뀐 수 {n}")
    return 0


def cmd_ab(a: argparse.Namespace) -> int:
    """옛 src → 새 src 차례로(동시 아님 · 메모리) 각각 다른 프로세스에서 run → diff → <out-dir>/전후.txt."""
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    codes = {}
    for tag, src in (("전", a.old_src), ("후", a.new_src)):
        cmd = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "run", "--name", a.name, "--src", str(src),
               "--out", str(out / f"{tag}.json"), "--kind", a.kind, "--cache-root", str(a.cache_root)]
        print(f"▶ {tag} = {src}", flush=True)
        codes[tag] = subprocess.run(cmd, env=dict(os.environ, OPENBLAS_NUM_THREADS="1")).returncode
    return cmd_diff(argparse.Namespace(old=out / "전.json", new=out / "후.json", paths=a.paths, save=out / "전후.txt")) or max(codes.values())


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="정산 표본 전후 계산 시험 도구(S1 · D-353)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cache", help="계정 자료 읽어 저장")
    c.add_argument("--accounts", required=True, help="쉼표로 나눈 계정ID 1~2개")
    for k in ARG_PATHS:
        c.add_argument("--" + k.replace("_", "-"), required=k in ("managed_output", "settle_dir", "stats", "inputs"))
    for k in ARG_TEXT:
        c.add_argument("--" + k, required=True)
    r = sub.add_parser("run", help="저장 자료로 계산 → json")
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--direct", action="store_true", help="저장 자료 안 쓰고 원래 파일에서 바로(비교 기준값)")
    ab = sub.add_parser("ab", help="옛 src·새 src run + diff")
    ab.add_argument("--old-src", required=True, type=Path)
    ab.add_argument("--new-src", required=True, type=Path)
    ab.add_argument("--out-dir", required=True, type=Path)
    for p in (c, r, ab):
        p.add_argument("--name", required=True, help="저장 이름(예 output38)")
        p.add_argument("--cache-root", type=Path, default=default_cache_root())
    for p in (c, r):
        p.add_argument("--src", type=Path, default=ROOT / "src")
    for p in (r, ab):
        p.add_argument("--kind", choices=("both", "old", "new"), default="both")
    d = sub.add_parser("diff", help="두 json 금액 칸 전후 표")
    d.add_argument("old", type=Path)
    d.add_argument("new", type=Path)
    d.add_argument("--save", type=Path)
    for p in (d, ab):
        p.add_argument("--paths", type=int, default=30, help="금액 밖 바뀐 경로 몇 개까지 보일지")
    return ap


def main(argv: list[str] | None = None) -> int:
    getattr(sys.stdout, "reconfigure", lambda **k: None)(encoding="utf-8")
    a = _parser().parse_args(argv)
    return {"cache": cmd_cache, "run": cmd_run, "diff": cmd_diff, "ab": cmd_ab}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
