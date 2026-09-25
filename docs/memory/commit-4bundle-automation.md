---
name: commit-4bundle-automation
description: 커밋마다 4묶음 자동화(2026-09-25). pre-commit 훅이 외부 .claude 메모리를 docs/memory/로 미러링·스테이징해 git에 백업(세션·PC 바뀌어도 무손실)+코드 변경인데 DECISIONS.md 없으면 경고. SSOT=tools/install_hooks.py·sync_memory.py.
metadata:
  node_type: memory
  type: project
  originSessionId: d8c440ae-0a9a-47f8-a6d2-d96209afecc7
  modified: 2026-09-25T05:19:35.777Z
---

**배경(소유자 2026-09-25)**: 세션 간 확정사항을 손실 없이 넘기려면 3채널 — ①코드+설계서(git)·②결정기록 `docs/DECISIONS.md`(git)·③메모리 — 을 커밋마다 함께 채워야 한다. 앞의 둘은 git 이라 안전하지만 **메모리는 `%USERPROFILE%\.claude\projects\<slug>\memory`(repo 밖)** 이라 PC 교체·`.claude` 소실 시 유실 위험.

**해결(커밋 시 자동 수행)**:
- **`tools/sync_memory.py`**: 외부 실사용 메모리 → repo `docs/memory/` 로 미러링(추가·갱신·삭제, README 포함). 경로=env `COUPANG_MEMORY_DIR` > 기본(USERPROFILE 기반, slug=repo 절대경로의 `:`·`\`·`/`→`-`). 외부 폴더 없으면(다른 PC) **no-op·커밋 안 막음**.
- **pre-commit 훅**(SSOT=`tools/install_hooks.py` PRE_COMMIT): 커밋마다 `sync_memory.py --stage` 실행 → `docs/memory/` 미러링+`git add` → **메모리가 매 커밋 git 에 저장**됨(새 세션/새 PC 는 클론만으로 스냅샷 확보). 실사용 SSOT 는 여전히 `.claude`, `docs/memory/` 는 백업 스냅샷(직접 수정 금지·다음 커밋에 덮임).
- **4묶음 알림**: 코드(src/ui/tools .py) 스테이징인데 `docs/DECISIONS.md` 미스테이징이면 경고 출력(**비차단** — 확정사항이면 DECISIONS·DESIGN·메모리도 담으라는 상기).

**지속성**: 훅은 `.git/hooks` 에 있어 **같은 repo 면 세션 바뀌어도 유지**. 새 클론/새 PC 는 `python tools/install_hooks.py` **1회** 재설치(기존 [[code-health-regression-gate]] 훅과 동일 설치기).

**새 세션 확인법**: `git log --oneline` + `docs/DECISIONS.md` 최근 줄 + `MEMORY.md` 인덱스 = 지난 세션 확정사항 복원. `docs/memory/` = 메모리 git 백업.

관련: [[commit-with-design-and-memory]] [[code-health-regression-gate]] [[recommend-new-session-when-degraded]].
