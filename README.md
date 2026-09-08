# coupang-analytics

쿠팡 셀러 운영 자동화 데스크톱 도구. 관리 계정들의 **상품별 × 일자별** 지표를 수집해
"상품별 노출 및 판매 현황" 워크북을 생성한다. 정책·구조의 단일 기준은 [designs/DESIGN.md](designs/DESIGN.md).

## 수집 지표

| 지표 | 정의 | 출처 |
|---|---|---|
| 노출순위 | 비로그인 검색 시 광고 제외 오가닉 순위 | 쿠팡 검색 (Q2) |
| 노출건수 | 판매분석 `조회` | 쿠팡 윙 판매분석 (Q1) |
| 판매건수 | 판매분석 `판매량` | 쿠팡 윙 판매분석 (Q1) |
| 방문자건수 | 판매분석 `방문자` | 쿠팡 윙 판매분석 (Q1) |

## 핵심 설계

- **입력** = 계정·상품 분석용 엑셀(대표자명/사업자명/계정아이디/상품명, **비번 없음**).
- **비번** = UI 입력 후 **그 PC에만 DPAPI로 암호화 저장**(공유 파일·git에 없음).
- **로그인** = 자동로그인 + 세션 재사용 + **로그인 대상 검증**. CAPTCHA는 수동.
- **매칭** = 입력 내부명 ↔ 쿠팡 등록상품ID는 문자열이 달라, **1회 매핑 후 재사용**(`mapping.py`).
- **출력** = `쿠팡데이타분석_yymmdd_시분초.xlsx` (이어쓰기/신규는 실행 시 선택).
- **배포** = Tkinter GUI → PyInstaller `.exe`.

## 구현 현황

**[완료] 오프라인 코어 (실물 파일 end-to-end 검증)**
- `config.py` 상수·정책값
- `input_list.py` 입력 엑셀 파싱(계정·상품 계층·검증)
- `report.py` 상품별 리포트 파싱(등록상품ID 집계·합산)
- `mapping.py` 내부명 ↔ 등록상품ID 매핑
- `workbook.py` 출력 워크북 시드·일자 컬럼 read/write
- `credstore.py` 비번 DPAPI 암호화 저장

**[예정] 라이브 페이지 1회 분석 후 확정**
- `session.py` / `browser.py` (로그인·검증·리포트 다운로드)
- `rank.py` (검색 순위, 광고 제외)
- `collector.py` (계정 순회 오케스트레이션)
- `ui/app.py` (데스크톱 GUI)

## 설치

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

> Windows 전용(비번 저장에 DPAPI 사용).
