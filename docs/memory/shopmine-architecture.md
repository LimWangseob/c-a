---
name: shopmine-architecture
description: "샵마인(ShopMine) 실증 분석 — .NET WinForms + Edge WebView2(임베디드 Chromium) + SQLite, 지문위조 아님"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 4ca6f1ec-575b-4e8e-8476-c3c67cf979b3
  modified: 2026-09-04T08:46:27.537Z
---

ShopMine 설치폴더 실증 분석(2026-09-04, 실행 안 함·파일 구조만 읽음, 제3자 쿠키/Login Data·프로세스메모리 미열람).
설치경로: `C:\Users\user\AppData\Roaming\ShopMine\sm`.

**구조(증거)**: .NET Framework 4.6 WinForms(`shopmine.exe`, `SMWF.*.dll`) + **Edge WebView2 임베디드 Chromium**(`Microsoft.Web.WebView2.*`, `WebView2Loader.dll`, `shopmine.exe.WebView2\EBWebView\Default`) + 로컬 **SQLite/EF6**(계정·주문). 보조 `SMWF.Chrome.exe`/`WebBrowser.dll`, 쿠키 재사용 HTTP `SMWF.HttpWrap.dll`, 몰 자동화 `SMWF.MarketInteraction.dll`(2.9MB)/`MarketAutomation`/`ShippingAgencyAutomation`, `KakaoCrypto.exe`, 설정 암호화(Base64).

**동작**: 계정추가 시 숨은 WebView2(진짜 Chromium)로 로그인(2차인증 1회 사람) → 세션쿠키를 Chromium 프로필에 영속 → "쇼핑몰 연결"은 새 로그인이 아니라 **저장 세션 로드/검증**(1초/계정, 창 없음) → 수집은 그 세션 쿠키를 HttpWrap로 **직접 HTTP** 재사용.

**핵심 결론**: **지문위조 흔적 없음** — 그냥 실제 Chromium을 창만 숨겨 씀. 우리 실제 Chrome+CDP와 같은 계열. 우리 "Access Denied"는 브라우저가 가짜라서가 아니라 IP 플래그 추정.

**우리 적용(정책 내)**: ①세션 영속·킵얼라이브로 재로그인/2차인증 빈도↓([[coupang-session-short-lived]]) ②로그인 세션 컨텍스트의 쿠키로 판매분석 데이터API 직접 호출(page.context.request) — UI 다운로드 대체, Akamai 403은 비로그인 세션만 막으므로 통과 ③수집도 offscreen(2차인증 시만 표시). 금지 유지: ShopMine 실행/의존·세션덤프·지문위조.
