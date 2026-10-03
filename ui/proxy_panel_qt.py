"""노출순위 프록시 — 설정 탭 '노출순위 프록시' 카드(Qt 믹스인). app_qt.App 이 상속한다.

config.json 의 `proxy/enabled`·`proxy/allow_auth`·`rank/block_images` 를 화면에서 켜고 끈다(예전엔 파일 직접 편집).
값의 의미·적용은 백엔드 그대로(config.apply_proxy_override·apply_rank_images_override 가 ③ 순위 진입 때 읽음).
⚠ 로그인·판매수집엔 프록시를 쓰지 않는다(③ 순위 전용). 프록시 주소 목록은 proxies.txt(평문 비밀이라 화면에 안 보임).
"""
from __future__ import annotations

import os
from typing import Any, Callable

from PySide6 import QtWidgets

from coupang_analytics import appconfig, proxy_pool

KEY_PROXY_ENABLED = "proxy/enabled"        # 미설정(빈값)=ON (config.apply_proxy_override 와 같은 해석)
KEY_PROXY_ALLOW_AUTH = "proxy/allow_auth"  # true 일 때만 HTTP user:pass 프록시 인증 허용
KEY_BLOCK_IMAGES = "rank/block_images"     # true 면 순위 브라우저 이미지 로드 끔(실험·기본 OFF)
PROXY_KEYS = (KEY_PROXY_ENABLED, KEY_PROXY_ALLOW_AUTH, KEY_BLOCK_IMAGES)
_ON = ("true", "1", "on", "yes")


def _is_on(key: str) -> bool:
    v = appconfig.get(key, "").strip().lower()
    if key == KEY_PROXY_ENABLED:
        return v not in ("false", "0", "off", "no")
    return v in _ON


class ProxyPanelMixin:
    # App 이 제공하는 것(정적검사용 선언)
    _card: Callable[[str], Any]
    _save_shared: Callable[[str, str], None]
    log: Callable[[str], None]

    def _proxy_card(self):
        card = self._card("노출순위 프록시 (③ 순위 조회 전용 — 로그인·판매수집엔 안 씀)")
        g = QtWidgets.QGridLayout(card)
        g.setColumnStretch(1, 1)
        self.proxy_enabled_chk = QtWidgets.QCheckBox("노출순위 검색에 프록시 사용")
        self.proxy_enabled_chk.setToolTip("끄면 순위 검색이 이 PC 인터넷으로 직접 나갑니다(사무실 IP 차단 이력 — 주의).\n"
                                          "켰는데 쓸 프록시가 없으면 순위만 건너뜁니다(직접 연결로 우회 안 함).")
        self.proxy_auth_chk = QtWidgets.QCheckBox("프록시 아이디·비밀번호 인증 허용")
        self.proxy_auth_chk.setToolTip("proxies.txt 주소에 아이디:비밀번호가 들어 있으면 켜야 합니다(HTTP 방식만).")
        self.rank_block_images_chk = QtWidgets.QCheckBox("순위 검색 때 이미지 끄기 (실험 — 데이터 절약)")
        self.rank_block_images_chk.setToolTip("차단을 늘리는지 아직 검증 전이라 기본은 꺼 둡니다.")
        rows = ((self.proxy_enabled_chk, KEY_PROXY_ENABLED), (self.proxy_auth_chk, KEY_PROXY_ALLOW_AUTH),
                (self.rank_block_images_chk, KEY_BLOCK_IMAGES))
        for i, (chk, key) in enumerate(rows):
            chk.setChecked(_is_on(key))
            chk.toggled.connect(lambda on, k=key: self._on_proxy_toggled(k, on))
            g.addWidget(chk, i, 0, 1, 2)
        self.proxy_file_lbl = QtWidgets.QLabel()
        self.proxy_file_lbl.setWordWrap(True)
        g.addWidget(self.proxy_file_lbl, len(rows), 0, 1, 2)
        self._refresh_proxy_file_state()
        return card

    def _on_proxy_toggled(self, key: str, on: bool) -> None:
        self._save_shared(key, "true" if on else "false")
        self.log(f"[설정] {key} = {'켬' if on else '끔'} (다음 ③ 순위 조회부터 적용)")

    def _proxy_values(self) -> dict[str, str]:
        """[설정값 저장]용 — 화면 체크 상태 그대로."""
        return {KEY_PROXY_ENABLED: "true" if self.proxy_enabled_chk.isChecked() else "false",
                KEY_PROXY_ALLOW_AUTH: "true" if self.proxy_auth_chk.isChecked() else "false",
                KEY_BLOCK_IMAGES: "true" if self.rank_block_images_chk.isChecked() else "false"}

    def _refresh_proxy_file_state(self) -> None:
        """proxies.txt 유무·줄 수만 보여 준다(주소·비밀번호는 화면에 안 띄움)."""
        path = proxy_pool.proxy_file_path() or "proxies.txt"
        n = 0
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                n = sum(1 for ln in f if ln.strip() and not ln.lstrip().startswith("#"))
        if n:
            text, style = f"✅ 프록시 목록 {n}줄 — {path}", "color: #047857;"
        else:
            text, style = (f"⚠ 프록시 목록 없음({path}) — 프록시를 켜 두면 순위 조회를 건너뜁니다",
                           "color: #b91c1c; font-weight: 700;")
        self.proxy_file_lbl.setText(text)
        self.proxy_file_lbl.setStyleSheet(style)
