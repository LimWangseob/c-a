"""계정별 고정 프록시 배정.

운영 원칙
---------
* ``PROXY_ENABLED=False`` 이면 기존처럼 직접 연결한다.
* ``PROXY_ENABLED=True`` 인데 사용할 수 있는 프록시가 없거나 설정이 잘못되면
  **직접 연결로 우회하지 않고 예외를 발생**시킨다(fail-closed).
* ``PROXY_ACCOUNT_MAP`` 에 지정한 프록시는 해당 계정의 전용 프록시로 취급하여
  일반 풀 자동 배정 대상에서 제외한다.
* 일반 풀은 활성(``is_active``) 노드만 사용하고, rendezvous hashing으로 계정별
  배정을 결정한다. 풀 구성 변경 시 단순 ``hash % N`` 보다 재배정 범위를 줄인다.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

from . import config
from .proxy_manager import ProxyConfigurationError, ProxyManager, ProxyNode


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


def _normalized_account_map() -> dict[str, str]:
    result: dict[str, str] = {}
    raw_map = getattr(config, "PROXY_ACCOUNT_MAP", {}) or {}
    for account_id, url in raw_map.items():
        if not account_id:
            raise ProxyConfigurationError("PROXY_ACCOUNT_MAP에 빈 계정 ID가 있습니다.")
        result[str(account_id)] = _normalize_required(
            url, label=f"PROXY_ACCOUNT_MAP[{account_id!r}]"
        )
    return result


def load_manager() -> Optional[ProxyManager]:
    """설정을 읽어 ProxyManager를 생성한다.

    프록시가 꺼져 있으면 ``None``을 반환한다. 프록시가 켜져 있으면 최소 1개의
    유효한 프록시가 반드시 존재해야 하며, 그렇지 않으면 ``ProxyConfigurationError``를
    발생시킨다. 따라서 설정 실수 때문에 원래 회선으로 조용히 연결되는 일이 없다.
    """
    if not _enabled():
        return None

    mgr = ProxyManager(strategy="round_robin")
    path = proxy_file_path()
    if path and os.path.isfile(path):
        mgr.load_from_file(path, strict=False)

    # 명시 매핑도 Manager에 등록해 health 상태를 한 곳에서 관리한다. 단, 아래 자동
    # 풀 배정 시에는 전용 프록시를 제외한다.
    explicit_map = _normalized_account_map()
    for url in explicit_map.values():
        mgr.load_proxies([url], strict=True)

    if len(mgr) == 0:
        location = path or getattr(config, "PROXY_FILE", "proxies.txt")
        raise ProxyConfigurationError(
            "PROXY_ENABLED=True 이지만 사용할 수 있는 프록시가 없습니다. "
            f"프록시 파일({location}) 또는 PROXY_ACCOUNT_MAP을 확인하세요."
        )
    return mgr


def _find_node(mgr: ProxyManager, normalized_url: str) -> Optional[ProxyNode]:
    for node in mgr.proxies:
        if node.raw_url == normalized_url:
            return node
    return None


def _rendezvous_pick(account_id: str, pool: list[ProxyNode]) -> ProxyNode:
    """활성 일반 풀에서 계정별 결정적(rendezvous) 프록시 하나를 선택."""
    if not pool:
        raise ProxyConfigurationError("활성 상태인 일반 프록시가 없습니다.")

    def score(node: ProxyNode) -> bytes:
        material = f"{account_id}\0{node.raw_url}".encode("utf-8")
        return hashlib.sha256(material).digest()

    return max(pool, key=score)


def proxy_for_account(mgr: Optional[ProxyManager], account_id: str) -> Optional[str]:
    """계정에 사용할 고정 프록시 URL을 반환한다.

    OFF일 때만 ``None``(직접 연결)을 반환한다. ON 상태에서는 설정/풀 오류를 예외로
    처리하여 fail-closed를 보장한다.
    """
    if not _enabled():
        return None
    if not account_id:
        raise ProxyConfigurationError("프록시를 배정하려면 account_id가 필요합니다.")
    if mgr is None:
        raise ProxyConfigurationError(
            "PROXY_ENABLED=True 이지만 ProxyManager가 초기화되지 않았습니다."
        )

    explicit_map = _normalized_account_map()
    explicit = explicit_map.get(account_id)
    if explicit:
        node = _find_node(mgr, explicit)
        if node is not None and not node.is_active:
            raise ProxyConfigurationError(
                f"계정 {account_id!r}에 지정된 프록시가 비활성 상태입니다: {node.redacted_url}"
            )
        return explicit

    reserved = set(explicit_map.values())
    pool = [
        node
        for node in mgr.proxies
        if node.is_active and node.raw_url not in reserved
    ]
    if not pool:
        raise ProxyConfigurationError(
            f"계정 {account_id!r}에 배정할 활성 일반 프록시가 없습니다. "
            "PROXY_ACCOUNT_MAP 또는 proxies.txt를 확인하세요."
        )
    return _rendezvous_pick(account_id, pool).raw_url


def redacted(url: Optional[str]) -> str:
    """로그용 자격증명 가린 표기."""
    if not url:
        return "직접연결(프록시 없음)"
    try:
        return ProxyNode(raw_url=url).redacted_url
    except (ProxyConfigurationError, TypeError):
        return "유효하지 않은 프록시"


__all__ = ["load_manager", "proxy_for_account", "proxy_file_path", "redacted"]
