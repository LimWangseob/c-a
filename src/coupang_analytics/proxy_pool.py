"""노출순위(rank) 검색 전용 프록시 — 비로그인 공개검색을 고정 IP 뒤에서 수행(2026-10-01 소유자 결정).

핵심 원칙
---------
* 프록시는 **노출순위(③) 검색에만** 적용한다. 로그인·판매수집(위탁계정)에는 적용하지 않는다
  — 비로그인 공개검색이라 계정 밴 위험이 없고, Akamai 차단·쿨다운 완화에 도움.
* ``PROXY_ENABLED=False`` 이면 기존처럼 직접 연결(None 반환).
* ``PROXY_ENABLED=True`` 인데 유효 프록시가 없으면 **직접 연결로 우회하지 않고** 예외를 발생
  시킨다(fail-closed). 호출부(rank)는 이 예외를 잡아 '순위 조회 건너뜀'으로 처리한다.
* rank 는 계정별이 아니라 **프록시 1개를 전역 egress** 로 쓴다(PROXY_RANK_URL 명시, 없으면 풀에서
  결정적 선택). 런타임에서 외부 호출(헬스체크)은 하지 않는다 — 로드·선택만.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

from . import config
from .proxy_manager import ProxyConfigurationError, ProxyManager, ProxyNode

_RANK_MGR: Optional[ProxyManager] = None
_RANK_LOADED = False


def _enabled() -> bool:
    return bool(getattr(config, "PROXY_ENABLED", False))


def proxy_file_path() -> Optional[str]:
    """프록시 목록 파일 경로(data_root 기준). apppaths가 없으면 상대경로 폴백."""
    name = getattr(config, "PROXY_FILE", "proxies.txt")
    try:
        from . import apppaths

        return os.path.join(apppaths.data_root(), name)
    except Exception:
        return name


def _normalize_required(url: str, *, label: str = "proxy") -> str:
    try:
        return ProxyNode(raw_url=url).raw_url
    except (ProxyConfigurationError, TypeError) as exc:
        raise ProxyConfigurationError(f"{label} 설정이 유효하지 않습니다: {exc}") from exc


def load_manager() -> Optional[ProxyManager]:
    """설정을 읽어 ProxyManager를 생성한다(rank 전용).

    OFF면 None. ON이면 최소 1개 유효 프록시가 있어야 하며, 없으면 ProxyConfigurationError
    (설정 실수로 원래 회선에 조용히 붙는 일 방지).
    """
    if not _enabled():
        return None

    mgr = ProxyManager()
    path = proxy_file_path()
    if path and os.path.isfile(path):
        mgr.load_from_file(path, strict=False)

    rank_url = (getattr(config, "PROXY_RANK_URL", "") or "").strip()
    if rank_url:
        mgr.load_proxies([_normalize_required(rank_url, label="PROXY_RANK_URL")], strict=True)

    if len(mgr) == 0:
        location = path or getattr(config, "PROXY_FILE", "proxies.txt")
        raise ProxyConfigurationError(
            "PROXY_ENABLED=True 이지만 사용할 수 있는 프록시가 없습니다. "
            f"프록시 파일({location}) 또는 PROXY_RANK_URL 을 확인하세요."
        )
    return mgr


def _pick(pool: list[ProxyNode], key: str) -> ProxyNode:
    """풀에서 결정적(rendezvous) 1개 선택 — 풀 구성이 바뀌어도 재선택 범위 최소."""
    def score(node: ProxyNode) -> bytes:
        return hashlib.sha256(f"{key}\0{node.raw_url}".encode("utf-8")).digest()

    return max(pool, key=score)


def rank_proxy(mgr: Optional[ProxyManager]) -> Optional[str]:
    """노출순위 검색용 고정 프록시 URL. OFF면 None. ON인데 활성 프록시 없으면 fail-closed 예외."""
    if not _enabled():
        return None
    if mgr is None:
        raise ProxyConfigurationError("PROXY_ENABLED=True 이지만 ProxyManager가 초기화되지 않았습니다.")

    explicit = (getattr(config, "PROXY_RANK_URL", "") or "").strip()
    if explicit:
        norm = _normalize_required(explicit, label="PROXY_RANK_URL")
        node = next((n for n in mgr.proxies if n.raw_url == norm), None)
        if node is not None and not node.is_active:
            raise ProxyConfigurationError(f"PROXY_RANK_URL 프록시가 비활성 상태입니다: {node.redacted_url}")
        return norm

    pool = [n for n in mgr.proxies if n.is_active]
    if not pool:
        raise ProxyConfigurationError(
            "노출순위 프록시 풀에 활성 노드가 없습니다. proxies.txt 또는 PROXY_RANK_URL 을 확인하세요."
        )
    return _pick(pool, "__rank__").raw_url


def rank_proxy_url(*, reload: bool = False) -> Optional[str]:
    """캐시된 매니저로 rank 프록시 해석(매 실행 1회 로드). OFF=None. 오류는 fail-closed 예외."""
    global _RANK_MGR, _RANK_LOADED
    if reload or not _RANK_LOADED:
        _RANK_MGR = load_manager()
        _RANK_LOADED = True
    return rank_proxy(_RANK_MGR)


def rank_proxy_or_skip(log=None) -> tuple[Optional[str], bool]:
    """(프록시URL|None, ok). OFF=(None, True) 무프록시 정상. ON+설정오류=(None, False) **순위 스킵**
    (직접연결로 우회하지 않음). rank 호출부에서 ok=False면 순위 브라우저를 열지 않는다."""
    try:
        return rank_proxy_url(), True
    except ProxyConfigurationError as exc:
        if log:
            log(_SKIP_MSG.format(exc=exc))
        return None, False


_SKIP_MSG = ("  ❌ [프록시] 노출순위 프록시가 켜져 있는데 쓸 프록시가 없음 → 이 검색 건너뜀(직접연결 안 함·그 칸 공란). "
             "proxies.txt 를 넣거나 설정 탭 '노출순위 프록시'를 끄세요 — {exc}")


def public_search_proxy(log=None) -> tuple[Optional[str], bool]:
    """비로그인 쿠팡 공개 검색(② 자동완성·키워드 추천 탭·순위 조회 탭)의 프록시 — config.json 설정을 먼저 적용한 뒤
    ③ 순위와 같은 규칙으로 선택(D-031). (url|None, ok): OFF=(None, True)·ON+오류=(None, False) → 호출부가 그 검색을
    건너뜀(직접연결로 우회하지 않음). ⛔ 로그인·판매수집·정산에는 쓰지 않는다(🔒 정책)."""
    config.apply_proxy_override(log)
    return rank_proxy_or_skip(log)


def _pick_url(urls: list[str], key: str) -> str:
    """raw_url 목록에서 결정적(rendezvous) 1개 선택 — _pick 과 동일한 점수식."""
    def score(u: str) -> bytes:
        return hashlib.sha256(f"{key}\0{u}".encode("utf-8")).digest()

    return max(urls, key=score)


def rank_proxy_pool_urls() -> list[str]:
    """활성 노출순위 프록시 노드 raw_url 목록(결정적 정렬). OFF/매니저없음=[].

    PROXY_RANK_URL 이 명시되면 그 1개만(풀 회전 대상 아님). 캐시된 매니저를 쓴다(매 실행 1회 로드).
    ON 인데 유효 프록시가 없으면 load_manager 가 ProxyConfigurationError 를 올린다(fail-closed).
    """
    global _RANK_MGR, _RANK_LOADED
    if not _enabled():
        return []
    if not _RANK_LOADED:
        _RANK_MGR = load_manager()
        _RANK_LOADED = True
    if _RANK_MGR is None:
        return []
    explicit = (getattr(config, "PROXY_RANK_URL", "") or "").strip()
    if explicit:
        return [_normalize_required(explicit, label="PROXY_RANK_URL")]
    return sorted(n.raw_url for n in _RANK_MGR.proxies if n.is_active)


def pick_rank_proxy(tried=None, log=None) -> tuple[Optional[str], bool, str]:
    """egress 회전용 프록시 선택 — 아직 안 쓴 활성 노드 1개.

    tried = 이번 실행에 이미 시도한 raw_url 집합(호출부가 관리). 반환 (url|None, ok, status):
      * OFF                     → (None, True,  "off")      무프록시 정상(회전 안 함)
      * 새 노드 있음            → (url,  True,  "ok")
      * ON+설정오류(풀 없음)    → (None, False, "error")    순위 스킵(직접연결 안 함)
      * 활성 노드 전부 tried    → (None, False, "exhausted") 더 바꿀 egress 없음 → 쿨다운으로

    ⚠ fail-closed: ON 인데 쓸 egress 가 없으면 절대 직접연결로 우회하지 않는다.
    tried=set() 로 부르면 rank_proxy_or_skip 의 첫 선택과 동일한 노드를 준다(같은 _pick 점수식).
    """
    if not _enabled():
        return None, True, "off"
    tried = tried or set()
    try:
        urls = rank_proxy_pool_urls()
    except ProxyConfigurationError as exc:
        if log:
            log(_SKIP_MSG.format(exc=exc))
        return None, False, "error"
    if not urls:
        return None, False, "error"
    remaining = [u for u in urls if u not in tried]
    if not remaining:
        return None, False, "exhausted"
    return _pick_url(remaining, "__rank__"), True, "ok"


def reset_cache() -> None:
    """프록시 설정/파일 변경 후 캐시를 비운다(다음 rank 조회부터 재로드)."""
    global _RANK_MGR, _RANK_LOADED
    _RANK_MGR, _RANK_LOADED = None, False


def redacted(url: Optional[str]) -> str:
    """로그용 자격증명 가린 표기."""
    if not url:
        return "직접연결(프록시 없음)"
    try:
        return ProxyNode(raw_url=url).redacted_url
    except (ProxyConfigurationError, TypeError):
        return "유효하지 않은 프록시"


__all__ = [
    "load_manager", "rank_proxy", "rank_proxy_url", "rank_proxy_or_skip", "public_search_proxy",
    "rank_proxy_pool_urls", "pick_rank_proxy",
    "reset_cache", "proxy_file_path", "redacted",
]
