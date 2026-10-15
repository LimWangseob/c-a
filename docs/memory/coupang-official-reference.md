---
name: coupang-official-reference
description: 쿠팡 WING 도움말 133편 전부 학습(2026-10-15) — 상세 SSOT=repo docs/COUPANG_WING_HELP_KB.md. 재학습 금지·수정일 바뀐 글만 갱신
metadata:
  type: reference
---

**쿠팡 공식 운영지식의 SSOT = repo `docs/COUPANG_WING_HELP_KB.md`** (2026-10-15 WING 도움말 133편 전부 읽고 우리 말로 요약 — 정산13·주문배송16·상품관리36·로켓그로스23·이용안내25·판매자정보5·기타15). 같은 내용을 **다시 학습하지 말 것** — 문서 §0-2 '읽은 글 목록'의 수정일과 비교해 바뀐 글만 다시 읽고 해당 절만 고친다(읽기 API·분류번호는 §0).

자주 쓰는 결론(상세·근거는 문서):
- 통장 입금 4갈래: 윙 정산 / 로켓그로스 월렛 인출 / **우대수수료 환급(쿠팡페이, ≈17일·≈2일)** / 재고 손실 보상(월 단위·CFS와 상계). 대사 때 메뉴 4곳 모두 확인.
- 판매자서비스이용료 5만+VAT는 **주정산이면 최종액(30%) 때 차감**. 광고비·밀크런·CFS·정산차감은 각 메뉴 엑셀이 증빙. 정산 > **지급내역** 엑셀 = 지급분 주문별 상세.
- 원본에 구매자 개인정보 → 암호화 보관·캡처 금지.
- 옛 메모 수치 정정: 상품명 **최대 120자**(2026-09-14 정책), 대표이미지 최소 1000×1000, 판매자점수 우수 기준 정시출고 98·정시배송 95·주문이행 98·24h답변 95. 2차 인증 2026-03-19부터 SMS만.
- ID 모델: 옵션ID=vendorItemId(변경추적 기준) · 등록상품ID=sellerProductId · 노출상품ID=productId. 노출상품명은 쿠팡이 바꿀 수 있음([[product-name-convention-ledger-vs-result]]).

관련: [[settlement-domain-knowledge]] [[settlement-batch-download-decisions]] [[settlement-statement-rules]]
