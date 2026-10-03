"""무인 실행 중 Windows 디스플레이/시스템 절전 억제(keep-awake).

왜 필요한가(2026-10-02 실측)
---------------------------
③ 반자동 순위는 **보이는 Chrome 창**을 쓰는데, 야간 무인 중 디스플레이가 꺼지면(전원 옵션) 창 컴포지터가
멈춰 ``page.bring_to_front()``(CDP 창 활성화)가 **타임아웃 없이 무한 대기**한다. 실측: 22:31:52 "kw 2/4 완료"
직후 멈췄다가 아침 08:25:06 에 그 다음 키워드부터 재개(약 10시간, PC는 밤새 켜져 있었고 절전/부팅 이벤트
없음·같은 프로세스). Playwright sync 특성상 ``bring_to_front`` 자체에 타임아웃을 걸 수 없으므로, **실행 중
디스플레이를 깨워 둬 애초에 멈추지 않게** 한다(근본 차단).

동작
----
``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)`` 는 **호출한 스레드**
기준으로 그 상태를 유지하고, 스레드가 끝나면 자동 해제된다(파이프라인은 백그라운드 스레드에서 돈다). 그래서
WingBrowser 수명(열림~닫힘)에 맞춰 켜고 끈다. Windows 아님/실패면 no-op(조용히 넘기지 않고 1회만 로그).
"""
from __future__ import annotations

import ctypes
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

_warned = False


def keep_awake(active: bool) -> bool:
    """active=True 면 디스플레이+시스템 절전을 억제, False 면 해제(기본 절전 허용). 성공 시 True.

    Windows 전용(``SetThreadExecutionState``). 다른 OS·실패면 no-op 로 False(실패는 1회만 로그).
    """
    global _warned
    if sys.platform != "win32":
        return False
    try:
        flags = ES_CONTINUOUS
        if active:
            flags |= ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        res = ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
        return res != 0
    except Exception as exc:
        if not _warned:
            _warned = True
            try:
                from . import config
                print(config.format_log(f"[power] 절전 억제 설정 실패(무시): {exc.__class__.__name__}"))
            except Exception:
                pass
        return False


__all__ = ["keep_awake"]
