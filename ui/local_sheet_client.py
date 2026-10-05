"""통합 앱 로컬 시트 클라이언트 — 구글 자격증명 없이 단독 실행용 저장소(JSON 1파일 = 시트 묶음).

도메인 store(worklog_store·contract_store·creditor_store·cs_gsheet)가 쓰는 구글시트 클라이언트 인터페이스를
**덕타이핑**으로 구현한다(sheet_titles·sheet_id·ensure_sheets·read_values·write_values·batch_update). 통합 앱을
설치·실험용으로 **즉시 실행**하게 해주고(네트워크·키 불필요), 나중에 실제 GSheetClient 로 **인자만 바꿔** 끼울 수 있다.

데이터는 `path`(JSON)에 시트별 2차원 배열로 보관하고, 쓰기마다 저장한다. insertDimension(ROWS)만 해석하고
서식·필터·검증 요청은 무시한다(로컬 저장엔 서식이 없음). RAW 여부는 값 보존(문자열)이라 구분 불필요.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


class LocalSheetClient:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.grids: dict[str, list[list[str]]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                raise RuntimeError(f"로컬 저장소 읽기 실패({self.path}): {exc}") from exc
            self.grids = {k: [list(r) for r in v] for k, v in data.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.grids, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    # ── 구글시트 클라이언트 인터페이스(덕타이핑) ──────────────────
    def sheet_titles(self) -> list[str]:
        return list(self.grids)

    def sheet_id(self, title: str):
        return (list(self.grids).index(title) + 1) if title in self.grids else None

    def ensure_sheets(self, titles) -> dict:
        changed = False
        for t in titles:
            if t not in self.grids:
                self.grids[t] = []
                changed = True
        if changed:
            self._save()
        return {t: self.sheet_id(t) for t in titles}

    def read_values(self, sheet: str, cell_range=None) -> list[list[str]]:
        out: list[list[str]] = []
        for r in self.grids.get(sheet, []):
            r = list(r)
            while r and r[-1] in ("", None):
                r.pop()
            out.append(r)
        while out and not out[-1]:
            out.pop()
        return out

    def write_values(self, sheet: str, rows, start: str = "A1", raw: bool = False) -> None:
        g = self.grids.setdefault(sheet, [])
        r0 = int(re.sub(r"\D", "", start)) - 1
        while len(g) < r0 + len(rows):
            g.append([])
        for i, row in enumerate(rows):
            g[r0 + i] = [("" if v is None else str(v)) for v in row]
        self._save()

    def batch_update(self, requests) -> dict:
        titles = list(self.grids)
        for q in requests:
            ins = q.get("insertDimension")
            if ins and ins["range"]["dimension"] == "ROWS":
                g = self.grids[titles[ins["range"]["sheetId"] - 1]]
                s, e = ins["range"]["startIndex"], ins["range"]["endIndex"]
                for _ in range(e - s):
                    g.insert(s, [])
        self._save()
        return {}
