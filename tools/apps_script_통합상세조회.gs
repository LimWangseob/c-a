/**
 * 운영대장 — 통합상세조회 Apps Script
 * ────────────────────────────────────────────────────────────
 * 기능 2가지(단순 트리거라 설치 불필요·저장만 하면 동작):
 *  (1) onSelectionChange : '관리상품' 시트에서 상품(물류)명 셀을 클릭하면
 *      → '통합상세조회'!B2 에 그 상품명을 넣고 시트를 연다(패널 수식이 자동 취합).
 *  (2) onEdit            : '통합상세조회' C열(수정입력)에 값을 넣으면
 *      → A열 라벨이 가리키는 원본 시트/열의 해당 상품 행에 기록(write-back).
 *        기록 후 입력칸을 비우고 '반영됨' 메모를 남긴다.
 *
 * 설치: 구글시트 > 확장프로그램 > Apps Script > 코드 전체 붙여넣기 > 저장.
 *       최초 1회 onEdit 실행 시 권한 승인(이 시트 편집 권한) 필요.
 * 키: 상품코드(통합상세조회!B3) 우선, 없으면 상품(물류)명(B2)으로 원본 행 탐색.
 */

var DETAIL = '통합상세조회';
var LIST   = '관리상품';
var SEL    = 'B2';   // 선택 상품(물류)명
var CODE   = 'B3';   // 선택 상품코드(자동)

// 수정입력(C열) 라벨 → [원본시트, 원본열이름]
var WRITEBACK = {
  '노출상품명': [LIST,   '노출상품명'],
  '판매방식':   [LIST,   '판매방식'],
  '카테고리':   [LIST,   '카테고리'],
  '관리상태':   [LIST,   '관리상태'],
  '키워드':     ['체험단', '키워드'],
};

/** (1) 관리상품에서 상품명 클릭 → 통합상세조회 로드 */
function onSelectionChange(e) {
  var rng = e.range, sh = rng.getSheet();
  if (sh.getName() !== LIST) return;
  if (rng.getNumRows() !== 1 || rng.getNumColumns() !== 1) return;
  if (rng.getRow() < 2) return;                          // 헤더 제외
  if (rng.getColumn() !== colIndex(LIST, '상품(물류)명')) return;
  var name = rng.getValue();
  if (!name) return;
  var ss = e.source, d = ss.getSheetByName(DETAIL);
  d.getRange(SEL).setValue(name);
  d.activate();
}

/** (2) 통합상세조회 C열 수정 → 원본 시트 반영 */
function onEdit(e) {
  var rng = e.range, sh = rng.getSheet();
  if (sh.getName() !== DETAIL) return;
  if (rng.getColumn() !== 3 || rng.getNumRows() !== 1) return;   // C열=수정입력
  var label = sh.getRange(rng.getRow(), 1).getValue();          // A열 라벨
  var map = WRITEBACK[label];
  if (!map) return;
  var val = rng.getValue();
  if (val === '' || val === null) return;

  var ss = e.source;
  var name = sh.getRange(SEL).getValue();
  var code = sh.getRange(CODE).getValue();
  var srcName = map[0], srcCol = map[1];
  var src = ss.getSheetByName(srcName);
  var row = findRow(src, srcName, name, code);
  if (row < 0) { rng.setNote('원본 행을 찾지 못함'); return; }

  src.getRange(row, colIndex(srcName, srcCol)).setValue(val);
  rng.clearContent();                                           // 반영 후 입력칸 비움
  rng.setNote('반영됨 → ' + srcName + '!' + srcCol + ' (행 ' + row + ')');
}

/** 헤더이름 → 열번호(1-base). 열이 이동해도 안전. */
function colIndex(sheetName, header) {
  var sh = SpreadsheetApp.getActive().getSheetByName(sheetName);
  var hdr = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  return hdr.indexOf(header) + 1;   // 0이면 없음
}

/** 원본 행 탐색: 상품코드 우선, 없으면 상품(물류)명 */
function findRow(src, sheetName, name, code) {
  var codeC = colIndex(sheetName, '상품코드');
  var nameC = colIndex(sheetName, '상품(물류)명');
  var data = src.getDataRange().getValues();
  for (var r = 1; r < data.length; r++) {
    if (codeC > 0 && code && data[r][codeC - 1] === code) return r + 1;
    if (nameC > 0 && name && data[r][nameC - 1] === name) return r + 1;
  }
  return -1;
}
