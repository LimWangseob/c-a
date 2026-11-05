# CLAUDE.md 축소 이동 대조표 (2026-11-05 · D-151)

소유자 조건: **축소할 때 그간 결정된 정책이 삭제되면 안 된다.** 전역 규칙: 200줄 미만·20KB 미만, 축소는 이동만 허용.

## 결과
- 원본: 커밋 `923f057` 의 `CLAUDE.md` — 59,590B·152줄·SHA-256 `487a1a74d3a517c702565f442973190298117902f98109c77fc3fae01e99ec09`
- 축소 후 `D:\coupang-analytics\CLAUDE.md`: 11,948B·87줄
- **내용 줄 141개 전부가 글자 하나 다르지 않게 이동처에 있음 — 누락 0**. 빈 줄 11개(구분용)만 위치가 바뀜.
- **제거한 내용 0건**(중복 제거도 하지 않음 — '같은 내용이 SSOT 에 있어 제거' 항목 없음). 그래서 `DECISIONS.md` 본문 변경도 없음(D-151 추가만).
- 이동은 문서 편집이 아니라 스크립트가 원본 줄을 잘라 붙이는 방식으로 함(타이핑 변형 없음).

| 위치 | 원문 줄 수 |
|---|---|
| `CLAUDE.md` | 47 |
| `docs/ARCHITECTURE.md` | 10 |
| `docs/PITFALLS.md` | 13 |
| `docs/CONSTRAINTS.md` | 15 |
| `docs/STATUS_HISTORY.md` | 36 |
| `docs/OPERATIONS_POLICY.md` | 20 |

## 다시 검증하는 법
`D:\coupang-analytics` 에서 실행. 출력이 `누락 0` 이어야 한다(이후 문서가 수정되면 그 줄은 누락으로 나올 수 있음 — 그때는 커밋 R91 기준으로 확인).

```bash
py -3.12 -c "import subprocess;L=[t for t in subprocess.run(['git','show','923f057:CLAUDE.md'],capture_output=True).stdout.decode().split(chr(10)) if t.strip()];D=''.join(open(f,encoding='utf-8').read()+chr(10) for f in ['CLAUDE.md','docs/ARCHITECTURE.md','docs/PITFALLS.md','docs/CONSTRAINTS.md','docs/STATUS_HISTORY.md','docs/OPERATIONS_POLICY.md']).split(chr(10));S=set(D);print('누락',sum(t not in S for t in L),'/',len(L))"
```

## 상시 규칙 한 줄 ↔ 원문
`CLAUDE.md` '상시 규칙' 절은 **새로 쓴 요약**이다(요약이 원문을 대체하지 않음 — 원문은 아래 표 이동처에 그대로). 요약과 원문이 다르면 원문이 기준.

| 상시 규칙 | 원본 줄 |
|---|---|
| 로그인 = 실제 Chrome+CDP·완료 판정 | 46, 32~34 |
| 비밀번호 거부 값·공백·최대 2회 | 55, 142 |
| 비밀번호 평문 금지·대장 로컬 백업 안 함 | 57, 112 |
| 프록시 = 비로그인 공개검색만·fail-closed·IP 정책 | 50, 53, 54 |
| 쿠팡 순위 = 반자동·간격 | 49, 133, 134 |
| 브라우저 동시 개방·세션 재사용·2차인증 | 46, 58, 56 |
| 지문/TLS 위조 = 소유자 판단 | 47, 48 |
| 라이브 사무실·전체실행 조합·강제종료 금지 | 146, 132 |
| output·data·config 삭제 금지·폴더 동일 | 42 |
| 구글 대장 실패 = 실행 중단 | 130 |
| 계정 삭제 비가역·숨김·취소선 | 28, 136, 137 |
| 사람 승인 대기열 금지 | 131 |
| 매칭·결과 상품명·순위 VID | 141, 142, 133 |
| 체험단 자동값·원장 링크·키워드 동결 | 139, 137, 135 |
| fallback 금지·판매데이터 없음·한국어 | 59, 46 |

## 발견한 어긋남 (이번에 안 고침 — 원문 그대로 옮김·소유자 판단 대기)
축소 중 눈에 띈 것만 적었다. 전수 대조가 아니다.
| 원본 줄 | 내용 | 근거(사실) |
|---|---|---|
| 23·136 | 그로스 재고 역기록 매칭키 = 계정+등록상품명 유사도(`_best_inventory_match`) | 줄 103 은 D-047·D-048 로 이름 유사도 삭제. `src/` 에 그 함수 없음(`.pyc` 에만) |
| 27 | 노출순위 프록시 '기본 OFF'·'③순위 전용' | 줄 50 '키 없으면 ON', `config.py:306` 빈값=ON, D-031 ②·탭도 사용 |
| 145 | '지문위조 금지라 우회 없음' | 줄 47 '하드 금지 아님·소유자 판단'. 상시 규칙은 줄 47 을 따름 |
| 18 | 입출력 정의서 128칸 | 줄 106 은 137칸 |
| 99 | 체험단 시작일 = 요청일 | D-122 로 '체험단시작일' 칸으로 바뀜(줄 94·139). 경위 기록이라 동결 문서에 그대로 둠 |

## 줄별 대조표
| 원본 줄 | 바이트 | 절 | 시작 문구 | 이동처 | 처리 |
|---|---|---|---|---|---|
| 1 | 19 | 머리 | # coupang-analytics | `CLAUDE.md:1` | 유지(원문) |
| 3 | 150 | 머리 | ⛔불변 정책 — 모든 도메인·세션·worktree·향후 세션에 영구 적용(소유자 | `CLAUDE.md:3` | 유지(원문) |
| 4 | 149 | 머리 | ①메모리(MEMORY.md 색인) 30~50줄·초과분 CLAUDE.md 이관.  | `CLAUDE.md:4` | 유지(원문) |
| 5 | 156 | 머리 | ③핸드오프 = STATE.md 한 곳(repo 루트·100줄 이하·세션마다 전체 | `CLAUDE.md:5` | 유지(원문) |
| 6 | 237 | 머리 | docs/DECISIONS.md D-번호 블록·추가 전용(기존 수정·삭제 금지· | `CLAUDE.md:6` | 유지(원문) |
| 7 | 340 | 머리 | ⑤세션 시작 = STATE.md+docs/DECISIONS_INDEX.md(자동 | `CLAUDE.md:7` | 유지(원문) |
| 8 | 130 | 머리 | R{n} 요약. 되돌림·완화 금지. 전역 SSOT = ~/.claude/CLAU | `CLAUDE.md:8` | 유지(원문) |
| 10 | 134 | 머리 | 관리 쿠팡 판매자 계정들의 상품별×일자별 지표(노출순위·노출건수·판매건수·방문자 | `CLAUDE.md:10` | 유지(원문) |
| 11 | 125 | 머리 | 통합 엑셀(쿠팡데이타분석_yymmdd_시분초.xlsx)을 생성하는 Windows | `CLAUDE.md:11` | 유지(원문) |
| 13 | 9 | 실행 | ## 실행 | `CLAUDE.md:13` | 유지(원문) |
| 14 | 3 | 실행 |  | `CLAUDE.md:14` | 유지(원문) |
| 15 | 23 | 실행 | cd D:\coupang-analytics | `CLAUDE.md:15` | 유지(원문) |
| 16 | 79 | 실행 | python ui/app_qt.py     # 기본 UI = PySide6(Qt | `CLAUDE.md:16` | 유지(원문) |
| 17 | 3 | 실행 |  | `CLAUDE.md:14` | 유지(원문) |
| 18 | 217 | 실행 | 설계 SSOT: designs/DESIGN.md, designs/KEYWORD_ | `CLAUDE.md:18` | 유지(원문) |
| 20 | 31 | 아키텍처 | ## 아키텍처 (핵심 모듈) | `docs/ARCHITECTURE.md:58` | 이동(원문) |
| 21 | 119 | 아키텍처 | - src/coupang_analytics/browser.py — 실제 Chro | `docs/ARCHITECTURE.md:61` | 이동(원문) |
| 22 | 1997 | 아키텍처 | - pipeline.py — run_full=①판매수집(계정마다 로그인→판매분석 | `docs/ARCHITECTURE.md:62` | 이동(원문) |
| 23 | 299 | 아키텍처 | - input_list.py — 입력 파싱(parse_input_list/par | `docs/ARCHITECTURE.md:63` | 이동(원문) |
| 24 | 329 | 아키텍처 | - collector.py(판매분석 데이터 API 직접조회 fetch_sales | `docs/ARCHITECTURE.md:64` | 이동(원문) |
| 25 | 755 | 아키텍처 | - detail_images.py — 상세페이지 이미지 추출(A안 CDP att | `docs/ARCHITECTURE.md:65` | 이동(원문) |
| 26 | 344 | 아키텍처 | - rank.py(비로그인 오가닉 순위) · kw_(키워드: AI 앵커·판정·선 | `docs/ARCHITECTURE.md:66` | 이동(원문) |
| 27 | 850 | 아키텍처 | - 노출순위 프록시(③순위 전용·기본 OFF): proxy_manager.py( | `docs/ARCHITECTURE.md:67` | 이동(원문) |
| 28 | 2651 | 아키텍처 | - 구글 시트 통합(입력=관리대장 구글시트·출력=결과 구글시트, SSOT=des | `docs/ARCHITECTURE.md:68` | 이동(원문) |
| 29 | 927 | 아키텍처 | - ui/app_qt.py — PySide6(Qt) GUI + Windows 1 | `docs/ARCHITECTURE.md:69` | 이동(원문) |
| 31 | 59 | 이미 해결한 함정 — 다시 깨지  | ## ⚠️ 이미 해결한 함정 — 다시 깨지 말 것 | `docs/PITFALLS.md:5` | 이동(원문) |
| 32 | 153 | 이미 해결한 함정 — 다시 깨지  | 1. 로그인 완료 판정: WingBrowser.authenticated() =  | `docs/PITFALLS.md:6` | 이동(원문) |
| 33 | 146 | 이미 해결한 함정 — 다시 깨지  | - seller-uid 쿠키는 로그인 폼(xauth) 단계에도 존재 → 단독 사 | `docs/PITFALLS.md:7` | 이동(원문) |
| 34 | 74 | 이미 해결한 함정 — 다시 깨지  | - URL 단독 판정도 금지(전환 중 transient wing.coupang. | `docs/PITFALLS.md:8` | 이동(원문) |
| 35 | 189 | 이미 해결한 함정 — 다시 깨지  | 2. 포트: WingBrowser(port=None) → _free_port() | `docs/PITFALLS.md:9` | 이동(원문) |
| 36 | 145 | 이미 해결한 함정 — 다시 깨지  | 3. 프로세스 정리: __exit__ → _kill_tree()(taskkill | `docs/PITFALLS.md:10` | 이동(원문) |
| 37 | 76 | 이미 해결한 함정 — 다시 깨지  | 4. 복원창 억제: --hide-crash-restore-bubble 등 플래그 | `docs/PITFALLS.md:11` | 이동(원문) |
| 38 | 111 | 이미 해결한 함정 — 다시 깨지  | 5. 로그인 창: 화면 정중앙(_center_pos). 화면 밖으로 숨으면 입력 | `docs/PITFALLS.md:12` | 이동(원문) |
| 39 | 217 | 이미 해결한 함정 — 다시 깨지  | 6. 자동입력: WingBrowser.autofill_login() — 리다이렉 | `docs/PITFALLS.md:13` | 이동(원문) |
| 40 | 249 | 이미 해결한 함정 — 다시 깨지  | 7. 비밀번호 출처: 입력 파일(쿠팡 계정과 등록 상품리스트(분석용).xlsx) | `docs/PITFALLS.md:14` | 이동(원문) |
| 41 | 502 | 이미 해결한 함정 — 다시 깨지  | 8. 콘솔창 깜빡임(2026-09-16 해결): 무인 --auto는 콘솔 없는  | `docs/PITFALLS.md:15` | 이동(원문) |
| 42 | 2267 | 이미 해결한 함정 — 다시 깨지  | 9. 폴더/경로 = 개발·운용 동일·평평한 한 폴더, output·data·co | `docs/PITFALLS.md:16` | 이동(원문) |
| 43 | 898 | 이미 해결한 함정 — 다시 깨지  | 10. 미서명 PyInstaller exe = Windows Defender 오 | `docs/PITFALLS.md:17` | 이동(원문) |
| 45 | 26 | 제약 | ## 제약 (보안·정책) | `docs/CONSTRAINTS.md:5` | 이동(원문) |
| 46 | 783 | 제약 | - 🔒 로그인 정책 고정(DESIGN §4 — 변경 금지): 실제 Chrome  | `docs/CONSTRAINTS.md:6` | 이동(원문) |
| 47 | 547 | 제약 | - 지문/TLS 위조(stealth/fingerprint spoofing) =  | `docs/CONSTRAINTS.md:7` | 이동(원문) |
| 48 | 398 | 제약 | - 진행 승인(2026-09-14 소유자): 낮은위험 1·2단계 착수 = ①UA | `docs/CONSTRAINTS.md:8` | 이동(원문) |
| 49 | 738 | 제약 | - 🔒 순위 조회 정책(2026-09-15 고정, DESIGN §5.2·§4.6 | `docs/CONSTRAINTS.md:9` | 이동(원문) |
| 50 | 913 | 제약 | - 🔌 노출순위 프록시(2026-10-01, config.json 키 없으면 O | `docs/CONSTRAINTS.md:10` | 이동(원문) |
| 51 | 732 | 제약 | - egress 재회전 + 차단 egress IP 목록(2026-10-02 구현 | `docs/CONSTRAINTS.md:11` | 이동(원문) |
| 52 | 406 | 제약 | - 이미지 OFF 실험: config.json rank/block_images= | `docs/CONSTRAINTS.md:12` | 이동(원문) |
| 53 | 323 | 제약 | - 🔒 IP 정책=맥락별 반대(proxy-ip-policy-by-context) | `docs/CONSTRAINTS.md:13` | 이동(원문) |
| 54 | 367 | 제약 | - 🔒 흔적은 IP 따라(D-058·설계 원칙): 프록시로 IP 를 바꾸는 비로 | `docs/CONSTRAINTS.md:14` | 이동(원문) |
| 55 | 1089 | 제약 | - 🔒 비밀번호 1회 오류 = 재시도 금지(2026-09-15, 계정잠금 방지) | `docs/CONSTRAINTS.md:15` | 이동(원문) |
| 56 | 183 | 제약 | - 폼에 incogniaRequestToken(Incognia 기기지문) + A | `docs/CONSTRAINTS.md:16` | 이동(원문) |
| 57 | 149 | 제약 | - 비밀번호 = DPAPI로 이 PC 전용 암호화(%LOCALAPPDATA%\c | `docs/CONSTRAINTS.md:17` | 이동(원문) |
| 58 | 166 | 제약 | - 쿠키 주입한 새 브라우저는 판매분석 데이터API가 Akamai에 막힘 → 수 | `docs/CONSTRAINTS.md:18` | 이동(원문) |
| 59 | 66 | 제약 | - fallback 금지(try/except pass, silent None). | `docs/CONSTRAINTS.md:19` | 이동(원문) |
| 61 | 90 | 코드 건강 규칙 | ## 코드 건강 규칙 (회귀 방지 — 2026-09-22, SSOT=design | `CLAUDE.md:54` | 유지(원문) |
| 62 | 123 | 코드 건강 규칙 | 배경: 잦은 수정으로 4파일(pipeline.py·workbook.py·app_ | `CLAUDE.md:55` | 유지(원문) |
| 63 | 124 | 코드 건강 규칙 | "과거 정상→오류" 회귀가 반복됨. 이를 막는 게이트를 뒀다. 아래는 매 작업에 | `CLAUDE.md:56` | 유지(원문) |
| 64 | 134 | 코드 건강 규칙 | ✅ 정비 완료(2026-09-22): 4파일의 D/E/F 괴물함수 전멸(전부 C | `CLAUDE.md:57` | 유지(원문) |
| 65 | 191 | 코드 건강 규칙 | 신설(pin_login_ranks·pin_apply_style·pin_run_p | `CLAUDE.md:58` | 유지(원문) |
| 66 | 200 | 코드 건강 규칙 | - 커밋/푸시 전 게이트 통과 필수: python tools/run_checks | `CLAUDE.md:59` | 유지(원문) |
| 67 | 137 | 코드 건강 규칙 | git 훅이 자동 검사(pre-commit=--quick시뮬+핀3+구글시트+정밀 | `CLAUDE.md:60` | 유지(원문) |
| 68 | 308 | 코드 건강 규칙 | 구성 = 시뮬레이션·핀4(로그인발견/apply_style/실행모드+단계조립/L1 | `CLAUDE.md:61` | 유지(원문) |
| 69 | 127 | 코드 건강 규칙 | 새 PC/클론 후 python tools/install_hooks.py 1회.  | `CLAUDE.md:62` | 유지(원문) |
| 70 | 131 | 코드 건강 규칙 | - 테스트에서 실 API 금지: 검증 3종은 로그인·OpenAI·네이버 호출 없 | `CLAUDE.md:63` | 유지(원문) |
| 71 | 139 | 코드 건강 규칙 | 키워드 선정도 기본은 결정적 모킹(경계만 페이크). 실 API 실증이 필요하면  | `CLAUDE.md:64` | 유지(원문) |
| 72 | 122 | 코드 건강 규칙 | - 새 함수 CC ≤ 15 지향 · 파일 ≤ ~600줄 지향: check_com | `CLAUDE.md:65` | 유지(원문) |
| 73 | 135 | 코드 건강 규칙 | 괴물함수를 경고하고, 건강하던 파일이 MI C로 떨어지면 차단(exit 1).  | `CLAUDE.md:66` | 유지(원문) |
| 74 | 137 | 코드 건강 규칙 | - A등급(건강) 파일은 건드리지 말 것: 불필요 변경=새 회귀. 4개 썩은 파 | `CLAUDE.md:67` | 유지(원문) |
| 75 | 117 | 코드 건강 규칙 | (그 행동을 simulate_pipeline/verify_offline이 덮는지 | `CLAUDE.md:68` | 유지(원문) |
| 76 | 141 | 코드 건강 규칙 | - 되돌림/정책 변경은 실측 근거 메모 필수(플립플롭 방지, fix-from-r | `CLAUDE.md:69` | 유지(원문) |
| 77 | 88 | 코드 건강 규칙 | 로직처럼 왕복(A→B→A)한 이력이 있음 — 근거 없는 되돌림 금지. | `CLAUDE.md:70` | 유지(원문) |
| 78 | 150 | 코드 건강 규칙 | - 분해는 행동 불변(로직 바꾸지 말고 위치만): 정책·엣지케이스(로그인 판정· | `CLAUDE.md:71` | 유지(원문) |
| 79 | 86 | 코드 건강 규칙 | 게이트) 보존. 매 추출 후 게이트 초록 유지, 커밋은 작게·자주. | `CLAUDE.md:72` | 유지(원문) |
| 81 | 71 | 병렬 개발 | ## 병렬 개발 (응답 대기 단축 — SSOT=docs/PARALLEL_DEV. | `CLAUDE.md:74` | 유지(원문) |
| 82 | 617 | 병렬 개발 | 🧭 2026-10-11 분리(D-035·D-036): 이 저장소 = R0(쿠팡  | `CLAUDE.md:75` | 유지(원문) |
| 83 | 165 | 병렬 개발 | 여러 세션이 코드 편집만 병렬. ⚠런타임은 병렬화 금지(단일 브라우저·위탁계정· | `CLAUDE.md:76` | 유지(원문) |
| 84 | 133 | 병렬 개발 | 야간 단일 순차·라이브 테스트도 한 번에 한 세션). 상세·레인표·병합 프로토콜 | `CLAUDE.md:77` | 유지(원문) |
| 85 | 161 | 병렬 개발 | - 격리: 세션마다 자기 worktree+브랜치에서 편집(master 직접 편집 | `CLAUDE.md:78` | 유지(원문) |
| 86 | 372 | 병렬 개발 | - 레인(편집 소유): A 수집/판매(collector·pipeline_sale | `CLAUDE.md:79` | 유지(원문) |
| 87 | 248 | 병렬 개발 | - 공유=직렬화(한 번에 한 세션 or 통합 세션): config.py·pipe | `CLAUDE.md:80` | 유지(원문) |
| 88 | 151 | 병렬 개발 | - 충돌 핫스팟: 게이트/핀 파일(tools/verify_offline.py 등 | `CLAUDE.md:81` | 유지(원문) |
| 89 | 186 | 병렬 개발 | - 병합: 각 레인 run_checks 초록 후 push → master 병합은 | `CLAUDE.md:82` | 유지(원문) |
| 90 | 346 | 병렬 개발 | - ⛔배포 zip 생성·결과 구글시트 반영 = 통제 세션('Coupang Ana | `CLAUDE.md:83` | 유지(원문) |
| 92 | 61 | 현재 상태 | ## 현재 상태 (상세는 각 메모·SSOT·git, 최신순) | `docs/STATUS_HISTORY.md:7` | 이동(원문) |
| 93 | 242 | 현재 상태 | - ✅2026-10-27 정산 로그인 정합(D-123): (DW)커머스 정산만  | `docs/STATUS_HISTORY.md:8` | 이동(원문) |
| 94 | 380 | 현재 상태 | - ✅2026-10-27 체험단 시작일 표시(D-121·D-122): 결과 사업 | `docs/STATUS_HISTORY.md:9` | 이동(원문) |
| 95 | 1048 | 현재 상태 | - ✅2026-10-26 위탁정산 1원 정산(D-115~D-119·SSOT=do | `docs/STATUS_HISTORY.md:10` | 이동(원문) |
| 96 | 494 | 현재 상태 | - ✅2026-10-23~26 모바일 링크·승인반려 순위(D-113·D-114) | `docs/STATUS_HISTORY.md:11` | 이동(원문) |
| 97 | 909 | 현재 상태 | - ✅2026-10-22 ⑤ 최근 1개월·셀독전환자 로그인 확인(D-110~D- | `docs/STATUS_HISTORY.md:12` | 이동(원문) |
| 98 | 1471 | 현재 상태 | - ✅2026-10-21 공란·압축 오류 분석 후속(D-089~D-095·SSO | `docs/STATUS_HISTORY.md:13` | 이동(원문) |
| 99 | 747 | 현재 상태 | - ✅2026-10-19 대장 개편 대응·결과 정합·체험단(D-079~D-087 | `docs/STATUS_HISTORY.md:14` | 이동(원문) |
| 100 | 658 | 현재 상태 | - ✅2026-10-16 정산·로그인·원장 정비(D-068~D-078·SSOT= | `docs/STATUS_HISTORY.md:15` | 이동(원문) |
| 101 | 795 | 현재 상태 | - ✅2026-10-15 쿠팡 정산 계산 방식 확정(D-065·D-066·SSO | `docs/STATUS_HISTORY.md:16` | 이동(원문) |
| 102 | 595 | 현재 상태 | - ✅2026-10-15 통합 판매현황(D-064·SSOT=designs/SAL | `docs/STATUS_HISTORY.md:17` | 이동(원문) |
| 103 | 1255 | 현재 상태 | - ✅2026-10-12 결과시트 점검 수정 D-040~D-050(SSOT=do | `docs/STATUS_HISTORY.md:18` | 이동(원문) |
| 104 | 909 | 현재 상태 | - ✅2026-10-09 소유자 결정 D-009~D-015(SSOT=docs/D | `docs/STATUS_HISTORY.md:19` | 이동(원문) |
| 105 | 919 | 현재 상태 | - ✅구현 Wave1 통합 착수(2026-10-06, 진입점=handoff-se | `docs/STATUS_HISTORY.md:20` | 이동(원문) |
| 106 | 295 | 현재 상태 | - ✅화면 시안(커머스 판로) 설계 완료(2026-10-06): 메뉴 v3.3  | `docs/STATUS_HISTORY.md:21` | 이동(원문) |
| 107 | 1353 | 현재 상태 | - 🧭커머스 판로 = 멀티플랫폼 통합 관리 앱 설계(2026-10-05·⛔전부  | `docs/STATUS_HISTORY.md:22` | 이동(원문) |
| 108 | 836 | 현재 상태 | - ✅설정 st.sync 재발방지 + 배포 config 씨앗 전환 + 결과시트  | `docs/STATUS_HISTORY.md:23` | 이동(원문) |
| 109 | 660 | 현재 상태 | - ✅설정 일원화(2026-10-03, H_ui 256d932·SSOT=runt | `docs/STATUS_HISTORY.md:24` | 이동(원문) |
| 110 | 1083 | 현재 상태 | - ✅로그인 대기 단축 + 18시 무인 즉시종료 원인규명(2026-10-03,  | `docs/STATUS_HISTORY.md:25` | 이동(원문) |
| 111 | 1080 | 현재 상태 | - ✅야간 ~10h 멈춤 근본차단 + 링크 중복붙여넣기 방어(2026-10-03 | `docs/STATUS_HISTORY.md:26` | 이동(원문) |
| 112 | 660 | 현재 상태 | - ✅작업 전 백업 401 근본수정(2026-10-02, SSOT=gsheet- | `docs/STATUS_HISTORY.md:27` | 이동(원문) |
| 113 | 546 | 현재 상태 | - ✅반자동 순위 자동제출 이중 검색요청 제거(2026-10-02, SSOT=D | `docs/STATUS_HISTORY.md:28` | 이동(원문) |
| 114 | 557 | 현재 상태 | - 🔌 노출순위 egress 재회전+차단IP목록+이미지OFF실험(2026-10- | `docs/STATUS_HISTORY.md:29` | 이동(원문) |
| 115 | 822 | 현재 상태 | - 🔌 노출순위 프록시 라이브 실측(2026-10-02, 메모 proxy-liv | `docs/STATUS_HISTORY.md:30` | 이동(원문) |
| 116 | 567 | 현재 상태 | - ✅매칭 5원인·AI 의미매칭·회사보유재고·정산2단계(2026-09-29, S | `docs/STATUS_HISTORY.md:31` | 이동(원문) |
| 117 | 399 | 현재 상태 | - 🆕셀독계정상품이력관리원장 1단계(2026-09-28, SSOT=LEDGER_ | `docs/STATUS_HISTORY.md:32` | 이동(원문) |
| 118 | 208 | 현재 상태 | - ✅대장↔결과 정합성 근본수정(2026-09-27, input-ledger-f | `docs/STATUS_HISTORY.md:33` | 이동(원문) |
| 119 | 453 | 현재 상태 | - ✅코드건강 대정비 Tier A/B(2026-09-26, handoff-cod | `docs/STATUS_HISTORY.md:34` | 이동(원문) |
| 120 | 392 | 현재 상태 | - ✅결과파일 이미지 9이슈(2026-09-26, 메모 handoff-9issu | `docs/STATUS_HISTORY.md:35` | 이동(원문) |
| 121 | 542 | 현재 상태 | - ✅소유자 9+6요구(2026-09-25~26, 메모 handoff-9item | `docs/STATUS_HISTORY.md:36` | 이동(원문) |
| 122 | 340 | 현재 상태 | - ⏳상품 블록 헤더 레이아웃 v4(2026-09-24 확정·미구현, 메모 ha | `docs/STATUS_HISTORY.md:37` | 이동(원문) |
| 123 | 222 | 현재 상태 | - ✅3대 결정(2026-09-24, 메모 handoff-3decisions-2 | `docs/STATUS_HISTORY.md:38` | 이동(원문) |
| 124 | 219 | 현재 상태 | - ✅구글시트 공통 재시도(2026-09-24): GSheetClient._ex | `docs/STATUS_HISTORY.md:39` | 이동(원문) |
| 125 | 482 | 현재 상태 | - 🔒재고 규칙(2026-09-24, 메모 handoff-inventory-bl | `docs/STATUS_HISTORY.md:40` | 이동(원문) |
| 126 | 414 | 현재 상태 | - 🔒VID 출처=상품조회(vendor-inventory/search)(2026 | `docs/STATUS_HISTORY.md:41` | 이동(원문) |
| 127 | 169 | 현재 상태 | - 판매상태 불일치 경고(2026-09-17, feature-sale-statu | `docs/STATUS_HISTORY.md:42` | 이동(원문) |
| 129 | 33 | 운영 정책 | ### 운영 정책 (상시 유효) | `docs/OPERATIONS_POLICY.md:5` | 이동(원문) |
| 130 | 336 | 운영 정책 | - 입력·계정목록(D-134·D-135): 구글 관리대장을 못 읽으면 ❌ 실행  | `docs/OPERATIONS_POLICY.md:6` | 이동(원문) |
| 131 | 311 | 운영 정책 | - 사람 승인 대기열 금지(소유자 2026-10-16): '확인필요·승인/반려' | `docs/OPERATIONS_POLICY.md:7` | 이동(원문) |
| 132 | 519 | 운영 정책 | - 전체실행 = ①반자동 → ②키워드선정(offscreen 없음) → ③반자동, | `docs/OPERATIONS_POLICY.md:8` | 이동(원문) |
| 133 | 934 | 운영 정책 | - 순위조회 = 자동+반자동(현재 기본=반자동 autosubmit, 앱이 타이핑 | `docs/OPERATIONS_POLICY.md:9` | 이동(원문) |
| 134 | 347 | 운영 정책 | - 검색 간격 = RANK_NAV_DELAY_MIN/MAX_SEC 현재 45~7 | `docs/OPERATIONS_POLICY.md:10` | 이동(원문) |
| 135 | 369 | 운영 정책 | - 키워드 이원화: product_keywords 비면 AI 선정·1건이라도 있 | `docs/OPERATIONS_POLICY.md:11` | 이동(원문) |
| 136 | 268 | 운영 정책 | - 관리대장 그로스 재고 역기록(AD열)(매칭키=계정+등록상품명 유사도)·계정  | `docs/OPERATIONS_POLICY.md:12` | 이동(원문) |
| 137 | 842 | 운영 정책 | - 관리대장 읽기(D-079·D-082): 헤더 비교 = input_list._ | `docs/OPERATIONS_POLICY.md:13` | 이동(원문) |
| 138 | 198 | 운영 정책 | - 사업자명 변경(D-080): 계정ID 같으면 ① 수집 전에 옛 시트를 새 이 | `docs/OPERATIONS_POLICY.md:14` | 이동(원문) |
| 139 | 798 | 운영 정책 | - 체험단 시작일(D-086·D-087·D-122): 대장 '체험단' 시트 '체 | `docs/OPERATIONS_POLICY.md:15` | 이동(원문) |
| 140 | 1256 | 운영 정책 | - 통합판매현황(D-064·D-094·D-128): 첫 시트 = 위 대시보드(요 | `docs/OPERATIONS_POLICY.md:16` | 이동(원문) |
| 141 | 294 | 운영 정책 | - 대장↔쿠팡 매칭 = AI 중심 + VID 고정(D-009·D-011, 202 | `docs/OPERATIONS_POLICY.md:17` | 이동(원문) |
| 142 | 843 | 운영 정책 | - 결과 상품명 = 현행 노출상품명(D-015): 같은 VID 개명=이력 승계· | `docs/OPERATIONS_POLICY.md:18` | 이동(원문) |
| 143 | 544 | 운영 정책 | - 날짜 넘긴 중단 작업: 진행 파일·단계 기록은 오늘 시작분 + 같은 날짜 칸 | `docs/OPERATIONS_POLICY.md:19` | 이동(원문) |
| 144 | 164 | 운영 정책 | - 재부팅 자동복구(2026-09-16): 야간 재부팅 시 '로그온' 트리거 - | `docs/OPERATIONS_POLICY.md:20` | 이동(원문) |
| 145 | 271 | 운영 정책 | - 로그인 2차인증: ID/비번 단일단계(별도 OTP 페이지 없음). 2차인증= | `docs/OPERATIONS_POLICY.md:21` | 이동(원문) |
| 146 | 196 | 운영 정책 | - 라이브 검증됨: 반자동 밤샘 무인 완주(2026-09-14: 22계정·271 | `docs/OPERATIONS_POLICY.md:22` | 이동(원문) |
| 147 | 157 | 운영 정책 | - 구글시트 계정목록 서식: 제목줄 동일색(B7C9E8)+사업자별 밴드8색(판매 | `docs/OPERATIONS_POLICY.md:23` | 이동(원문) |
| 148 | 227 | 운영 정책 | - 검증도구: tools/simulate_pipeline.py(운영 조합 시나리 | `docs/OPERATIONS_POLICY.md:24` | 이동(원문) |
| 150 | 9 | 환경 | ## 환경 | `CLAUDE.md:85` | 유지(원문) |
| 151 | 231 | 환경 | - Windows, Python, Playwright(sync) + 실제 Goo | `CLAUDE.md:86` | 유지(원문) |
| 152 | 331 | 환경 | - ⛔ 네이버쇼핑 검색 API(shop.json)는 2026-07-31자로 완전 | `CLAUDE.md:87` | 유지(원문) |

## 토큰 비교
`py -3.12 tools/measure_first_tokens.py` — 이 저장소에서 연 세션의 첫 응답 입력 토큰(최근 10개). 축소 전 기준 = 11-02 세션 104,107 · R91 이후 새 세션 값과 비교한다. 이 표를 만든 날에는 R91 이후 시작한 세션이 없어 미측정.
