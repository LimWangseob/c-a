# docs/memory — 세션 메모리 스냅샷(자동 생성·수정 금지)

이 폴더는 `tools/sync_memory.py` 가 **커밋마다** 외부 실사용 메모리
(`%USERPROFILE%\.claude\projects\<slug>\memory`)를 미러링한 **백업 스냅샷**입니다.
직접 수정하지 마세요 — 실사용 메모리를 고치면 다음 커밋에 자동 반영됩니다.
목적: PC 교체·`.claude` 소실에도 확정사항(메모리)을 git 으로 보존(손실 방지).
