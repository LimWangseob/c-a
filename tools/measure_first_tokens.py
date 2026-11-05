# -*- coding: utf-8 -*-
"""이 저장소에서 연 세션들의 첫 응답 입력 토큰을 최근 10개 출력(앱 코드와 무관한 측정 도구).

CLAUDE.md 축소(D-151) 효과 비교용 — 기준 = 11-02 세션 104,107. 대조표 = docs/decisions/claudemd-move-2026-11-05.md.
사용: py -3.12 tools/measure_first_tokens.py  (출력 = 세션 생성 시각, 토큰 수, 세션 파일 앞 8자)
"""
import glob, json, os, time
rows = []
for p in glob.glob(os.path.expanduser(r"~/.claude/projects/D--coupang-analytics/*.jsonl")):
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            if '"usage"' not in ln: continue
            try: u = json.loads(ln)["message"]["usage"]
            except Exception: continue
            n = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            rows.append((os.path.getctime(p), n, os.path.basename(p)[:8])); break
for c, n, s in sorted(rows)[-10:]:
    print(time.strftime("%m-%d %H:%M", time.localtime(c)), n, s)
