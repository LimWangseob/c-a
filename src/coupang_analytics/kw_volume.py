"""네이버 검색광고 키워드도구 API — 월 검색량 + 연관 키워드.

키워드 하나(힌트)를 넣으면 연관 키워드 목록을 월간 검색수(PC/모바일)와 함께 돌려준다.
→ 키워드 '후보 발굴'과 '검색량' 을 동시에 제공. 검색량은 네이버 기준(쿠팡 미공개의 대용치).
자격증명(CUSTOMER_ID/API_KEY/SECRET_KEY)은 그 PC에만 두고 공유·git 금지.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import requests

_HINT_BATCH = 5  # keywordstool 한 요청당 최대 힌트 수
_NAVER_CONCURRENCY = 4  # 연관어 배치 동시 요청 상한(과하면 429)

BASE_URL = "https://api.searchad.naver.com"
_PATH = "/keywordstool"


@dataclass
class KeywordVolume:
    keyword: str
    pc: int
    mobile: int
    comp_idx: str          # 경쟁정도 높음/중간/낮음 (아이템스카우트 '경쟁')
    pc_clicks: float = 0.0     # 월 평균 클릭수 PC
    mobile_clicks: float = 0.0  # 월 평균 클릭수 모바일
    pl_avg_depth: int = 0      # 광고 노출 개수(평균) — 아이템스카우트 '광고'

    @property
    def total(self) -> int:
        return self.pc + self.mobile

    @property
    def total_clicks(self) -> float:
        return self.pc_clicks + self.mobile_clicks


@dataclass
class NaverCredentials:
    customer_id: str
    api_key: str
    secret_key: str


def parse_credentials_file(path: str | Path) -> NaverCredentials:
    """'라벨 값' 형식(줄당 1개) 파일에서 자격증명 추출."""
    fields: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        value = line.rsplit(None, 1)[-1]
        if "CUSTOMER" in line.upper() or "광고계정" in line:
            fields["customer"] = value
        elif "라이선스" in line:
            fields["key"] = value
        elif "비밀" in line:
            fields["secret"] = value
    missing = {"customer", "key", "secret"} - fields.keys()
    if missing:
        raise ValueError(f"자격증명 파일에서 누락된 항목: {missing}")
    return NaverCredentials(fields["customer"], fields["key"], fields["secret"])


def _to_int(value) -> int:
    """월검색수. '< 10' 같은 문자열은 9로 근사."""
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if s.startswith("<"):
        return 9
    return int(s.replace(",", "")) if s and s.replace(",", "").isdigit() else 0


def _to_float(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    if s.startswith("<"):
        return 9.0
    try:
        return float(s)
    except ValueError:
        return 0.0


class NaverAdApi:
    def __init__(self, creds: NaverCredentials):
        self.creds = creds

    def _headers(self) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        msg = f"{ts}.GET.{_PATH}"
        sig = base64.b64encode(
            hmac.new(self.creds.secret_key.encode(), msg.encode(), hashlib.sha256).digest()).decode()
        return {
            "X-Timestamp": ts,
            "X-API-KEY": self.creds.api_key,
            "X-Customer": self.creds.customer_id,
            "X-Signature": sig,
        }

    def _query(self, hints: list[str]) -> list[KeywordVolume]:
        params = {"hintKeywords": ",".join(h.replace(" ", "") for h in hints), "showDetail": "1"}
        r = None
        for attempt in range(3):        # 병렬 호출 시 429/5xx 대비 소폭 백오프 재시도
            r = requests.get(BASE_URL + _PATH, headers=self._headers(), params=params, timeout=15)
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue
            break
        r.raise_for_status()
        out: list[KeywordVolume] = []
        for k in r.json().get("keywordList", []):
            out.append(KeywordVolume(
                keyword=k["relKeyword"],
                pc=_to_int(k.get("monthlyPcQcCnt")),
                mobile=_to_int(k.get("monthlyMobileQcCnt")),
                comp_idx=k.get("compIdx", ""),
                pc_clicks=_to_float(k.get("monthlyAvePcClkCnt")),
                mobile_clicks=_to_float(k.get("monthlyAveMobileClkCnt")),
                pl_avg_depth=_to_int(k.get("plAvgDepth")),
            ))
        return out

    def related_keywords(self, hint: str) -> list[KeywordVolume]:
        """힌트 키워드 1개의 연관 키워드 + 월 검색량."""
        return self._query([hint])

    def related_keywords_multi(self, hints: list[str]) -> list[KeywordVolume]:
        """여러 힌트의 연관 키워드를 모아 중복 제거 — 배치(5힌트)를 **동시 요청**(속도).

        기존엔 배치마다 순차+0.3초 sleep이라 힌트가 많으면 느렸다. requests는 스레드 안전이라
        ThreadPoolExecutor로 병렬 호출(과도한 동시성은 429 유발 → 상한 _NAVER_CONCURRENCY, _query에 재시도).
        결과는 먼저 온 순서와 무관하게 배치 순서대로 병합해 재현성 유지.
        """
        if not hints:
            return []
        batches = [hints[i:i + _HINT_BATCH] for i in range(0, len(hints), _HINT_BATCH)]
        seen: dict[str, KeywordVolume] = {}
        with ThreadPoolExecutor(max_workers=min(_NAVER_CONCURRENCY, len(batches))) as ex:
            for kvs in ex.map(self._query, batches):   # 배치 순서 보존
                for kv in kvs:
                    seen.setdefault(kv.keyword, kv)
        return list(seen.values())
