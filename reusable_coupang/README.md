# reusable_coupang

쿠팡의 **자동 로그인**과 **자동 노출순위 검색**을 다른 프로젝트에서 바로 가져다 쓰도록 뽑아낸 **자립 패키지**입니다.
핵심은 "Akamai 봇탐지를 통과하는 실제 브라우저 제어"이며, 원본 프로젝트(coupang-analytics)에서 라이브로 검증된 로직을
그대로 이식하고 **상세 주석**을 달았습니다.

> ⚠️ 자기 계정/자기 상품 조회 용도입니다. 대량·공격적 사용은 계정 밴/IP 차단 위험이 있습니다.
> 순위 대량 조회는 `parse_serp_rank`(반자동, 봇 신호 최소) 쪽을 권장합니다.

---

## 구성

| 파일 | 역할 |
|---|---|
| `auto_login.py` | **자동 로그인** — 실제 Chrome + CDP(`WingBrowser`). 자동입력·2차인증 대기·세션 재사용·화면분류. |
| `rank_search.py` | **자동 노출순위 검색** — 사람 타이핑 검색 + 광고 제외 오가닉 순위 파싱. |
| `human_typing.py` | 사람처럼 한 글자씩 실제 키보드 입력(한글 = CDP IME 자모 조합). 로그인·검색어 공용. |
| `human_mouse.py` | 사람처럼 마우스 이동/스크롤/호버(클릭 없음). |
| `config.py` | 타이핑 리듬·순위 스캔 상한·상호작용 스위치. |
| `example.py` | 실행 데모(login / rank). |

## 요구사항

- **Python 3.10+**, `pip install playwright` (브라우저 바이너리는 설치 불필요 — **시스템에 설치된 Google Chrome** 사용).
- **실제 Google Chrome** 설치.
- **Windows 권장**: 화면 중앙 좌표(`ctypes.windll`)·잔여 Chrome 정리(PowerShell)·프로세스 종료(`taskkill`)가 Windows 기준입니다.
  다른 OS 로 옮기려면 `auto_login.py` 의 `_center_pos` / `_kill_profile_chrome` / `reap_orphan_chrome` / `_kill_tree` 를 그 OS 방식으로 교체하세요(나머지 로직은 OS 무관).

## 설치

폴더 `reusable_coupang/` 를 대상 프로젝트 루트에 통째로 복사한 뒤:

```python
from reusable_coupang import WingBrowser, organic_ranks, make_matcher, parse_serp_rank, warmup
```

## 사용법

### 1) 자동 로그인
```python
from reusable_coupang import WingBrowser, WING_URL

# profile_dir 는 계정마다 다른 폴더 → 세션이 계정별로 유지(재실행 시 재로그인 생략).
with WingBrowser(profile_dir="data/acct_foo", offscreen=False) as b:
    b.goto(WING_URL)
    if not b.authenticated():                       # 세션 없으면 로그인
        b.autofill_login("myid", "mypw", on_log=print)   # ID/비번 자동입력·제출
        b.wait_for_login(on_log=print, on_need_user=b.show)  # 2차인증 필요 시에만 창 표시
    print("로그인:", b.authenticated())
```
- **비밀번호**는 예제처럼 평문으로 넘기지 말고, 실전에선 OS 자격증명 관리자/DPAPI 등 **안전 저장소에서 그때만** 받아 넘기세요.
- 로그인 완료 판정(`authenticated()`) = **윙 대시보드 URL(xauth/sso 아님) AND `KEYCLOAK_IDENTITY` 쿠키** 둘 다(둘 중 하나만으로 판정하면 오판).
- 2차인증은 **위치/환경 기반 조건부**입니다(신뢰 환경은 없이 통과, 낯선 환경은 요구). 자동제출이 Akamai 에 차단(`blocked`)되면 그 창에서 사람이 직접 로그인해야 합니다.

### 2-a) 자동 노출순위 검색 (이 모듈이 직접 검색)
```python
from reusable_coupang import WingBrowser, warmup, organic_ranks, make_matcher

with WingBrowser(profile_dir="data/rank", offscreen=True) as b:   # 로그인 불필요
    warmup(b)                                                      # 홈 1회 방문(신뢰 쿠키 유지)
    matchers = {"내상품": make_matcher(vendor_item_ids={"12345678"})}
    ranks = organic_ranks(b, "빌베리", matchers, log=print)         # {"내상품": 3 or None}
```
- 반환값은 `{라벨: 순위(int) 또는 None}`. `None` = 스캔 상한(`config.RANK_SCAN_MAX`, 기본 50) 밖/미노출.
- 검색어를 **URL 로 직접 넣지 않고 검색창에 사람처럼 타이핑 + Enter** 합니다(붙여넣기는 봇으로 차단됨).
- 차단(Akamai 챌린지) 감지 시 `RankBlocked` 예외 → 호출부가 잠시 쉬고 재시도/공란 처리.

### 2-b) 반자동 파싱 (이미 열린 검색결과만 읽기 — 차단 회피 우선)
```python
from reusable_coupang.rank_search import parse_serp_rank, make_matcher

# 사람(또는 다른 로직)이 이미 검색결과 페이지를 띄워둔 상태의 page 를 넘긴다.
res = parse_serp_rank(page, {"내상품": make_matcher(vendor_item_ids={"12345678"})})
rank, item = res["내상품"]        # (순위 or None, 매칭 SearchItem or None)
```
- 우리가 네비게이션/타이핑을 안 하므로 봇 신호가 가장 적습니다. **대량 조회·차단 회피에 유리.**

## 매칭 우선순위(중요)
`make_matcher(product_ids, vendor_item_ids, name_substr)` — 하나라도 맞으면 내 상품:
1. **vendorItemId(옵션ID) 앵커 권장** — 불변(재등록해도 유지).
2. productId — 가변(재등록 시 바뀜)이라 보조.
3. 상품명 부분일치 — vid 없을 때만 폴백(부정확).

## Akamai 통과의 핵심(왜 이렇게 하나)
- **실제 Chrome + CDP**(자동화 플래그 없음). Playwright 가 띄운 브라우저는 webdriver 흔적으로 차단됨.
- **검색어/로그인 입력 = 신뢰 키이벤트로 한 글자씩**(붙여넣기·value setter 는 isTrusted=false 로 감지·차단).
- **신뢰 쿠키(`_abck` 등) 유지**(`warmup`) → '재방문 신뢰 브라우저'로 인식돼 챌린지↓.
- (선택) 사람 같은 마우스/스크롤 재현(`human_mouse`, 위조 아님·실제 Input). `config.RANK_HUMAN_INTERACT` 로 on/off.
- **대량·버스트는 위험** — 사람 속도 간격을 두고, 대량이면 반자동 파싱(2-b)을 쓰세요.

## 설정(`config.py`)
- 순위: `RANK_SCAN_MAX`(스캔 상한), `RANK_PAGE_DELAY_MIN/MAX`(페이지 간 지연), `RANK_INCLUDE_MOBILE`.
- 타이핑: `TYPE_KEY_DELAY_MIN/MAX`, `TYPE_HESITATE_*`, `TYPE_LONGPAUSE_*`, `TYPE_JAMO_IME`, `TYPE_JAMO_COMMIT_MODE`.
- 상호작용: `RANK_HUMAN_INTERACT`(마우스/스크롤 on/off).
- 기본값은 라이브로 튜닝된 '사람 속도'입니다. **급하게 낮추면 봇탐지에 불리**하니 주의.

## 유지보수 주의
- 쿠팡 검색결과 **DOM 클래스명**(`ProductUnit_productUnit` 등)은 사이트 개편 시 바뀔 수 있습니다 → `rank_search.py` 상단 셀렉터 상수 갱신.
- 로그인 폼은 **xauth.coupang.com Keycloak 표준 폼**(`#username`/`#password`/`#kc-login`) 기준입니다.

## 데모 실행
```bash
# 패키지 상위 폴더에서
python -m reusable_coupang.example login  data/acct_foo  <아이디> <비번>
python -m reusable_coupang.example rank   data/rank      "빌베리"  <vendorItemId>
```
