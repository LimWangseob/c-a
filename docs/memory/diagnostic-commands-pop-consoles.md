---
name: diagnostic-commands-pop-consoles
description: 진단 명령은 사용자 실제 PC에서 돌아 콘솔창을 띄움 — 최소화하고 PowerShell은 bash로 감싸지 말 것(따옴표·한글 깨짐)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2e84ec15-ec5e-47e8-a0f5-e93a370e0385
  modified: 2026-09-17T00:04:43.761Z
---

이 세션의 Bash/PowerShell 도구 명령은 **사용자의 실제 Windows PC에서 실행**되어 화면에 **콘솔창을 잠깐 띄운다**. 무인 자동실행을 모니터링하던 중, PowerShell을 bash로 감싸(`powershell -c "..."`) 돌렸더니 **따옴표가 깨져 한글 오류가 깨진 채** 콘솔창에 떴고(예: `=== : '===' 는 cmdlet...`), 사용자가 이를 "앱이 띄운 깨진 콘솔창"으로 오해해 혼란·불안을 느꼈다(2026-09-16).

**⚠정정(2026-09-17)**: 사용자가 본 "깨진 글씨+아무 키나 누르십시오" 콘솔창의 **진짜 원인은 내 명령이 아니라 배포 스크립트**였다. `deploy/uninstall_schedule.ps1`(·install)이 **한글 작업 이름을 문자열 리터럴로 하드코딩** → BOM 없는 상태로 `powershell`(Windows PS **5.1**)이 **cp949로 읽어** 한글 깨짐 → 따옴표·괄호 망가져 문법 오류 → `.bat`이 `pause`에서 멈춤. **수정(커밋 093b068)**: uninstall을 **순수 ASCII**로 재작성(작업을 한글 이름 대신 `--auto/--resume` 인자로 찾음). install은 BOM 보호. **평소 실행(--auto=pythonw·바탕화면 아이콘=pythonw)은 콘솔 안 뜸**(browser.py 보조명령 `CREATE_NO_WINDOW`). 콘솔은 **설치/해제 .bat 수동 더블클릭 때만** 정상. 교훈=콘솔 원인을 **내 명령만 의심 말고 프로젝트 .bat/.ps1도** 볼 것(스크린샷의 `~dp0`·`pause`가 결정적 단서였음).

**Why**: 사용자 화면에 뜨는 창은 전부 사용자에게 보인다. 깨진/불필요한 콘솔창은 앱 오작동으로 오해되고 거슬린다.
**How to apply**:
- 상태 확인 명령을 **꼭 필요할 때만·최소 횟수**로. 무인 실행 모니터링은 한 번에 필요한 것만 모아서.
- Windows에서 PowerShell이 필요하면 **PowerShell 도구로 직접**(깨끗한 따옴표) 실행. **bash로 감싸지 말 것**(따옴표·cp949 한글 깨짐).
- 앱 자체(pythonw --auto)는 콘솔 없음·입력 대기 없음. browser.py 보조명령은 `CREATE_NO_WINDOW`로 콘솔 숨김([[date-column-run-date-rule]] 세션에서 처리). 화면에 콘솔이 떴다면 **내 진단 명령**을 먼저 의심.
관련 [[plain-language-no-jargon]] [[fix-from-real-evidence]]
