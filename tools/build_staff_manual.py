"""결과 구글시트 활용 매뉴얼(PDF) 생성 — HTML(캡처+빨간 번호 상자) → Chrome headless 로 PDF.

캡처 = output/직원매뉴얼/캡처/*.jpg(Chrome 화면 1239x538 좌표계·git 밖). 결과 = output/직원매뉴얼/(git 밖·판매 금액 포함).
실행: python tools/build_staff_manual.py  (소유자 2026-10-21 요청·문구 = 화면·파일 이름 그대로)
"""
import os
import subprocess

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "직원매뉴얼")
W, H = 1239, 538
N = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"


def shot(fname, boxes, y0=140, y1=H, width="100%"):
    """boxes = [(번호, x0, y0, x1, y1)] — 빨간 상자 + 왼쪽 위 번호. y0~y1 만 보여 줌(위쪽 구글 메뉴 줄 자르기)."""
    ch = y1 - y0
    parts = [f'<div class="shot" style="width:{width}"><div class="crop" style="padding-top:{ch / W * 100:.3f}%">'
             f'<img src="캡처/{fname}" style="margin-top:-{y0 / W * 100:.3f}%">']
    for n, bx0, by0, bx1, by1 in boxes:
        lf, tp = bx0 / W * 100, (by0 - y0) / ch * 100
        w, h = (bx1 - bx0) / W * 100, (by1 - by0) / ch * 100
        parts.append(f'<div class="box" style="left:{lf:.2f}%;top:{tp:.2f}%;width:{w:.2f}%;height:{h:.2f}%"></div>'
                     f'<div class="num" style="left:{lf:.2f}%;top:{tp:.2f}%">{N[n - 1]}</div>')
    parts.append("</div></div>")
    return "".join(parts)


def notes(items, one_col=False, cols=2):
    c = 1 if one_col else cols
    return (f"<ol class='notes' style='columns:{c}'>" + "".join(f"<li><span class='n'>{N[i]}</span> {t}</li>"
            for i, t in enumerate(items)) + "</ol>")


CSS = """
@page { size: A4 landscape; margin: 12mm 12mm 12mm 12mm; }
* { box-sizing: border-box; }
body { font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; color: #1f2328; font-size: 10.5pt; line-height: 1.5; margin: 0; }
.page { page-break-after: always; height: 185mm; display: flex; flex-direction: column; justify-content: center; overflow: hidden; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 20pt; margin: 0 0 2mm; color: #1d3c78; }
h2 { font-size: 14.5pt; margin: 0 0 3mm; color: #1d3c78; border-bottom: 2px solid #1d3c78; padding-bottom: 1mm; }
h3 { font-size: 11.5pt; margin: 3mm 0 1.5mm; color: #1d3c78; }
.sub { color: #57606a; font-size: 9.5pt; margin-bottom: 4mm; }
.name { background: #eef3fb; border: 1px solid #c9d6ee; border-radius: 3px; padding: 0 3px; font-weight: bold; white-space: nowrap; }
.tab { background: #e9f5ea; border: 1px solid #b9dcbc; border-radius: 3px; padding: 0 3px; font-weight: bold; white-space: nowrap; }
.warn { color: #c62828; font-weight: bold; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
.card { border: 1px solid #d0d7de; border-radius: 4px; padding: 3mm 4mm; }
.card.red { border: 2px solid #c62828; background: #fff6f6; }
.card.blue { background: #f5f8fd; }
ul, ol { margin: 1mm 0; padding-left: 6mm; }
li { margin: 0.6mm 0; }
table { border-collapse: collapse; width: 100%; font-size: 9.6pt; }
th, td { border: 1px solid #c9d1d9; padding: 1.2mm 2mm; vertical-align: top; text-align: left; }
th { background: #eef3fb; }
.shot { position: relative; margin: 1mm auto 2mm; border: 1px solid #aab4c0; }
.crop { position: relative; width: 100%; overflow: hidden; }
.crop img { position: absolute; left: 0; top: 0; width: 100%; }
.box { position: absolute; border: 2.4px solid #e53935; border-radius: 3px; }
.num { position: absolute; transform: translate(-45%, -45%); background: #e53935; color: #fff; font-weight: bold;
       font-size: 11pt; line-height: 1; padding: 2px 3px; border-radius: 50%; min-width: 18px; text-align: center; }
.notes { list-style: none; padding-left: 0; column-gap: 6mm; font-size: 11pt; line-height: 1.55; margin: 2mm 0 0; }
.notes li { break-inside: avoid; margin: 0 0 1.6mm; }
.notes.one { columns: 1; }
.notes .n { color: #e53935; font-weight: bold; }
.flow { display: flex; align-items: center; gap: 2mm; font-size: 9.6pt; }
.flow .f { border: 1px solid #1d3c78; border-radius: 4px; padding: 1.5mm 2.5mm; background: #f5f8fd; text-align: center; }
.flow .a { color: #1d3c78; font-weight: bold; }
.foot { position: fixed; bottom: -7mm; right: 0; font-size: 8pt; color: #8c959f; }
.page.dense { font-size: 9.6pt; line-height: 1.42; }
.page.dense table { font-size: 8.8pt; }
.page.dense th, .page.dense td { padding: 0.7mm 1.6mm; }
.page.dense li { margin: 0.3mm 0; }
.page.dense h3 { margin: 2mm 0 1mm; }
.link { font-size: 9.5pt; margin: 0 0 3mm; color: #57606a; }
.link a { color: #1a5fd0; text-decoration: underline; word-break: break-all; }
.draft { color: #c62828; font-size: 9pt; }
"""

P = []
# ── 1쪽: 한눈에 보기 ───────────────────────────────────────────────
P.append(f"""
<div class="page">
<h1>[쿠팡] 데이터 분석 통계 구글 파일 — 활용 매뉴얼</h1>
<div class="link">관련 파일 링크(클릭): <a href="https://docs.google.com/spreadsheets/d/1BzzlNd7sM3fMEgajsPW5xqxtaVdyhyf8xnWFlpPx7E0/edit?gid=1967107600#gid=1967107600">https://docs.google.com/spreadsheets/d/1BzzlNd7sM3fMEgajsPW5xqxtaVdyhyf8xnWFlpPx7E0/edit?gid=1967107600#gid=1967107600</a></div>
<h2>한눈에 보기</h2>
<div class="grid2">
 <div>
  <div class="card blue">
   <b>이 파일은</b> — 우리가 관리하는 위탁 계정의 <b>관리 상품 판매·재고·쿠팡 노출 순위</b>를 앱이 <b>매일 저녁 자동으로</b> 모아 보여 주는 구글 시트입니다. 위탁자가 직접 등록해 파는 다른 상품은 들어가지 않습니다.
  </div>
  <h3>파일과 시트 처리 흐름</h3>
  <div class="flow">
   <div class="f">원천 데이터<br><span class="name">[셀독] 관리 대장</span><br>시트 <span class="tab">셀독리스트</span> <span class="tab">체험단</span><br><span class="name">[재고] 현황</span></div>
   <div class="a">→</div>
   <div class="f">앱<br>매일 <b>18:00</b> 시작<br>쿠팡·네이버에서<br>자료 수집</div>
   <div class="a">→</div>
   <div class="f">결과(보는 곳)<br><span class="name">[쿠팡] 데이터 분석 통계</span><br><span class="tab">통합판매현황</span> → <span class="tab">계정목록</span> → 사업자명 시트<br>(예 <span class="tab">휴라엘</span>)</div>
  </div>
  <h3>하루 흐름</h3>
  <ul>
   <li><b>18:00</b> 앱이 <span class="name">[셀독] 관리 대장</span> 을 읽고 시작 → 판매 수집 → 키워드 → 노출 순위 → <b>다음 날 아침</b>까지 결과 파일 갱신</li>
   <li>판매 숫자 = <b>전일</b>(어제) 자료 · 노출 순위 = <b>실행한 날</b> 저녁에 잰 값</li>
  </ul>
  <h3>결과 파일에서 직원이 직접 입력하는 곳</h3>
  <ul>
   <li>사업자명 시트의 <span class="name">키워드</span> 칸 (상품당 최대 10개 · 8쪽)</li>
   <li>그 밖의 칸은 앱이 매일 다시 쓰므로 고쳐도 다음 날 원래대로 돌아갑니다. 계정·상품·판매중지는 <span class="name">[셀독] 관리 대장</span> 에서 고칩니다.</li>
  </ul>
 </div>
 <div>
  <div class="card red">
   <b class="warn">꼭 지킬 것 4가지</b>
   <ol>
    <li><b><span class="name">[셀독] 관리 대장</span> 의 상품명은 쿠팡에 노출되는 상품명과 등록상품명으로 적어 주세요.</b> 앱(AI)이 이 상품명으로 쿠팡 계정에 접속해 상품을 찾아 연결(매칭)합니다. 상품명을 임의로 적으면 쿠팡에 등록된 상품과 매칭할 수 없어 판매·순위가 비게 됩니다.</li>
    <li><b><span class="name">[셀독] 관리 대장</span> 수정은 18:00 전에.</b> 18:00 이후에 고친 내용은 그날이 아니라 <b>다음 날</b> 결과에 반영됩니다(사라지지는 않음).</li>
    <li><b>키워드는 사업자명 시트에서 추가합니다(상품당 최대 10개).</b> 그 상품의 '키워드' 머리줄이 있는 블록에서 마지막 키워드 아래에 행을 넣고 A열에 적으면, 다음 18:00 실행부터 검색량·노출 순위가 채워집니다(추가·변경·삭제 가능 · 11번째부터는 반영 안 됨 · 자세한 방법 8쪽).
     <br><b>키워드 칸을 지우면</b> 그 키워드의 <b>지난 순위 기록도 함께 지워집니다.</b></li>
    <li><b><span class="name">[셀독] 관리 대장</span> 에서 한 계정의 줄을 모두 지우거나 모두 숨기면</b> 결과 파일에서 그 계정 이력이 <b>완전히 삭제</b>됩니다. 계정 정지는 계정아이디 칸 <b>취소선</b>으로 표시하세요.</li>
   </ol>
  </div>
  <h3>이 매뉴얼의 순서</h3>
  <table>
   <tr><th>쪽</th><th>내용</th></tr>
   <tr><td>2</td><td>원천 데이터와 반영 시점(18시 규칙)</td></tr>
   <tr><td>3~6</td><td><span class="tab">통합판매현황</span> — 요약·월별 누계·차트·계정 순위·일별 상세</td></tr>
   <tr><td>7</td><td><span class="tab">계정목록</span> — 계정별 상품 내역, 체험단 내역</td></tr>
   <tr><td>8</td><td>사업자명 시트(예 <span class="tab">휴라엘</span>) — 상품별 판매 현황, 노출 순위, 재고 현황 상세</td></tr>
   <tr><td>9</td><td>자주 묻는 질문</td></tr>
  </table>
 </div>
</div>
</div>""")

# ── 2쪽: 원천 데이터와 반영 시점 ───────────────────────────────────
P.append("""
<div class="page dense">
<h2>원천 데이터와 반영 시점</h2>
<div class="grid2">
<div>
<h3>결과 파일의 값은 어디서 오나</h3>
<table>
 <tr><th>결과 파일에 보이는 것</th><th>원천</th><th>고치는 사람</th></tr>
 <tr><td>계정·상품 목록, 대표자·사업자·계정ID, 판매중지 여부</td><td><span class="name">[셀독] 관리 대장</span> › <span class="tab">셀독리스트</span></td><td>직원</td></tr>
 <tr><td>체험단 시작일</td><td><span class="name">[셀독] 관리 대장</span> › <span class="tab">체험단</span> 시트의 요청일</td><td>직원</td></tr>
 <tr><td>회사보유재고</td><td><span class="name">[재고] 현황</span> 의 '현재고'</td><td>직원</td></tr>
 <tr><td>판매량·방문자·노출량·판매금액·수량</td><td>쿠팡 WING 각 계정 판매분석(전일 자료)</td><td>자동</td></tr>
 <tr><td>재고현황·그로스재고·판매상태·판매가</td><td>쿠팡 WING 각 계정 재고·상품 정보</td><td>자동</td></tr>
 <tr><td>노출 순위</td><td>쿠팡 검색 화면(광고 제외, 그날 저녁 측정)</td><td>자동</td></tr>
 <tr><td>검색량</td><td>네이버 월간 검색수(PC+모바일·매일 새로 받음)</td><td>자동</td></tr>
 <tr><td>키워드</td><td>처음엔 AI 가 고름 → 이후 직원이 사업자명 시트에 추가</td><td>직원·자동</td></tr>
</table>
<h3><span class='name'>[셀독] 관리 대장</span>에서 앱이 직접 쓰는 칸 — 고치지 마세요</h3>
<ul>
 <li><span class="name">[셀독] 관리 대장</span> 의 <b>그로스 재고 칸(AD열)</b>, <b>'회사보유재고 (자동갱신 MM.DD)'</b> 칸 — 앱이 매일 덮어씁니다.</li>
 <li>파일 <span class="name">셀독계정상품이력관리원장_자동화</span> 는 앱 기록용입니다. 열어 보기만 하고 고치지 마세요.</li>
</ul>
</div>
<div>
<h3>언제 반영되나 — 18시 규칙</h3>
<table>
 <tr><th>언제 고쳤나</th><th>무엇을</th><th>결과</th></tr>
 <tr><td><b>18:00 전</b></td><td><span class='name'>[셀독] 관리 대장</span>·체험단·재고현황</td><td>그날 밤 결과에 반영</td></tr>
 <tr><td><b>18:00 이후</b></td><td><span class='name'>[셀독] 관리 대장</span>·체험단</td><td><b>다음 날 18:00</b> 실행에 반영(내용은 그대로 남음)</td></tr>
 <tr><td>18:00 이후</td><td>재고현황</td><td>실행 도중 결과를 다시 쓸 때 일부 반영될 수 있음 → 확실히 하려면 18:00 전에</td></tr>
 <tr><td class="warn">18:00 ~ 아침</td><td class="warn">결과 파일(키워드 등)</td><td class="warn">사라짐 — 앱이 끝날 때 통째로 다시 씀</td></tr>
 <tr><td>낮(아침 완료 후~18:00)</td><td>결과 파일 키워드</td><td>다음 실행부터 검색량·순위 측정</td></tr>
</table>
<h3><span class='name'>[셀독] 관리 대장</span> 수정 규칙</h3>
<div class="card red" style="padding:2mm 3mm; margin-bottom:1.5mm"><b class="warn">중요 — 상품명은 쿠팡 노출 상품명으로</b><br><span class='name'>[셀독] 관리 대장</span> 의 상품명은 <b>쿠팡에 노출되는 상품명(과 등록상품명)</b>으로 적어야 앱(AI)이 쿠팡 계정의 상품과 <b>매칭</b>합니다. 임의로 줄이거나 바꿔 적으면 매칭되지 않아 그 상품의 판매·재고·노출 순위가 결과 파일에 나오지 않습니다.</div>
<ul>
 <li><b>상품 판매중지</b> = 그 상품 행을 <b>숨기기</b>, 또는 '상태' 칸에 판매중지 → 결과 파일에 '⛔ 판매중지'·순위 조사 중단(이력은 남음)</li>
 <li><b>계정 정지</b>(관리 중단) = 계정아이디 칸에 <b>취소선</b> → 이력은 남음</li>
 <li><span class="warn">한 계정의 줄을 모두 지우거나 모두 숨기면 → 결과 파일 이력 완전 삭제(되돌릴 수 없음)</span></li>
 <li>쿠팡이 정지했지만 <b>복구할 계정</b>은 그대로 두세요(취소선·숨기기 하지 않음). 판매 0 으로 수집되고, 상품이 판매중지 상태라 순위는 자동으로 건너뜁니다.</li>
 <li>사업자명을 바꿔도 계정아이디가 같으면 이력이 이어집니다(옛 이름 시트은 새 이름으로 합쳐짐).</li>
</ul>
</div>
</div>
</div>""")

# ── 3쪽: 통합판매현황 ① 요약 ──────────────────────────────────────
P.append("<div class='page'><h2><span class='tab'>통합판매현황</span> ① 요약·월별 누계</h2>"
         "<div class='sub'>파일을 열면 처음 보이는 시트입니다. 숫자는 모두 <b>관리 상품</b>만 더한 값입니다.</div>"
         + shot("01_통합판매현황_요약.jpg", [
             (1, 45, 186, 1170, 207), (2, 45, 272, 693, 333), (3, 693, 272, 872, 333), (4, 872, 272, 1170, 333),
             (5, 45, 333, 700, 352), (6, 45, 353, 1170, 490), (7, 130, 503, 1010, 537)], y0=0, width="96%")
         + notes([
             "<b>기준 전일</b>(판매 날짜) · <b>갱신</b> 시각",
             "<b>전일 · 지난주 · 이번 달 누계</b> 금액·수량",
             "<b>증감</b>: ▲ 늘어남 · ▼ 줄어듦",
             "<b>비교 기준</b>: 무엇과 비교했는지",
             "<b>미수집 계정</b>: 어제 자료를 못 받은 계정",
             "<b>월별 누계</b>: 4월부터 달마다",
             "<b>시트 이동</b>: 아래 시트 이름 클릭",
         ], cols=3) + "</div>")

# ── 4쪽: 차트 ② ③ ④ ──────────────────────────────────────────────
P.append("<div class='page'><h2><span class='tab'>통합판매현황</span> ② 월별 · ③ 주간 · ④ 일별 차트</h2>"
         + shot("02_통합판매현황_월별주간차트.jpg", [(1, 47, 233, 682, 490), (2, 690, 233, 1172, 490)], y0=210, y1=492, width="88%")
         + shot("03_통합판매현황_일별차트.jpg", [(3, 47, 233, 1172, 490)], y0=210, y1=492, width="88%")
         + notes([
             "<b>월별</b>: 진한 파랑 = 끝난 달 · 연한 파랑 = 진행 중인 달",
             "<b>주간</b>: 최근 8주(월~일)",
             "<b>일별</b>: 최근 31일 · 회색 = 일부 계정 미수집",
         ], cols=3) + "</div>")

# ── 5쪽: ⑤ 계정 순위 ─────────────────────────────────────────────
P.append("<div class='page'><h2><span class='tab'>통합판매현황</span> ⑤ 계정 순위</h2>"
         + shot("04_통합판매현황_계정순위차트.jpg", [(1, 47, 233, 1172, 490)], y0=210, y1=492, width="88%")
         + shot("05_통합판매현황_계정순위표.jpg", [(2, 45, 272, 1052, 292), (3, 1052, 272, 1172, 490)], y0=255, y1=492, width="88%")
         + notes([
             "<b>막대</b>: 최근 1개월(어제까지 30일) 누계가 큰 계정부터",
             "<b>표</b>: 순위 · 계정 · 최근 1개월 누계 · 지난주",
             "<b>전주 대비</b>: ▲ 늘어남 · ▼ 줄어듦 · '미수집' = 자료 없음",
         ], cols=3) + "</div>")

# ── 6쪽: 일별 상세 ───────────────────────────────────────────────
P.append("<div class='page'><h2><span class='tab'>통합판매현황</span> 상세 — 일별 판매</h2>"
         "<div class='sub'>차트 아래로 내려가면 나옵니다. 최근 31일 · <b>최신 날짜가 왼쪽</b>.</div>"
         + shot("06_통합판매현황_일별상세.jpg", [
             (1, 693, 232, 1172, 252), (2, 45, 253, 1172, 292), (3, 45, 293, 1172, 312), (4, 45, 313, 1172, 352),
             (5, 247, 353, 575, 490), (6, 575, 353, 693, 490)], y0=140, y1=492, width="100%")
         + notes([
             "<b>날짜</b>: 왼쪽이 최신",
             "<b>전체 합계</b>: 수량 · 금액",
             "<b>미수집 계정 수</b>: 그날 못 받은 계정",
             "<b>계정 소계</b>: 계정마다 한 블록",
             "<b>상품</b>: 쿠팡 노출 상품명",
             "<b>구분</b>: 로켓그로스 / 윙(판매자배송) · 음수 = 반품",
         ], cols=3) + "</div>")

# ── 7쪽: 계정목록 ────────────────────────────────────────────────
P.append("<div class='page'><h2><span class='tab'>계정목록</span> — 계정별 상품 내역, 체험단 내역</h2>"
         + shot("07_계정목록_왼쪽.jpg", [(1, 47, 166, 1170, 192), (2, 47, 194, 448, 226), (3, 448, 230, 880, 404), (4, 985, 230, 1172, 404)], y1=406, width="94%")
         + shot("08_계정목록_오른쪽.jpg", [(5, 476, 400, 582, 421), (6, 772, 192, 873, 226), (7, 873, 230, 969, 445), (8, 1066, 422, 1172, 443)], y0=160, y1=450, width="94%")
         + notes([
             "제목: 관리 상품 수(판매중지 제외)",
             "<b>대표자 · 사업자 · 계정ID</b>",
             "<b><u>상품명(클릭 이동)</u></b>: <b><u>누르면 사업자명 시트로 이동</u></b>",
             "<b>회사보유재고</b>: [재고] 현황의 현재고",
             "<b>상태</b>: 빈칸 = 정상 · ⛔ 판매중지 · 미수집",
             "<b>그로스재고</b>: 쿠팡 로켓그로스 재고",
             "<b>체험단 시작일</b>: '체험단' 시트에서 자동",
             "<b>체험단효과</b>: 초록 = 좋아짐 · 빨강 = 나빠짐",
         ], cols=3) + "</div>")

# ── 8쪽: 사업자명 시트 ──────────────────────────────────────────────
P.append("<div class='page'><h2>사업자명 시트 (예: <span class='tab'>휴라엘</span>) — 상품별 판매 현황, 노출 순위, 재고 현황 상세</h2>"
         + shot("09_사업자시트_휴라엘.jpg", [
             (1, 45, 164, 523, 193), (2, 524, 164, 626, 193), (3, 733, 164, 1172, 193), (4, 45, 218, 626, 346),
             (5, 626, 218, 732, 366), (6, 733, 218, 1172, 240), (7, 523, 366, 626, 490), (8, 733, 388, 1172, 490)],
             y1=492, width="88%")
         + "<div class='grid2' style='grid-template-columns: 11fr 9fr; margin-top:2mm'><div>"
         + notes([
             "제목: 대표자 · 사업자 · 계정ID",
             "<b>👈 계정목록으로 이동</b>",
             "<b><u>옵션 상품 블록에는 키워드·검색량·노출 순위가 없습니다 — 기본(대표) 상품 블록에만 표시 · 판매중지 상품은 순위 조사 안 함</u></b>",
             "<b>상품명</b>(쿠팡 페이지) · <b>VID</b> · 판매방식",
             "<b>지표</b>: 판매량 · 방문자 · 노출량 · 재고 · 판매가",
             "<b>날짜</b>: 왼쪽이 최신 · 판매는 전날 하루치",
             "<b>검색량</b>: 네이버 월간 검색수",
             "<b>노출 순위</b>: '40위' · '49위밖'(49개 안에 없음) · 빈칸 = 측정 전",
         ], cols=2)
         + "</div><div class='card blue'><b>키워드 추가 · 변경 · 삭제</b> (상품당 <b>최대 10개</b>)"
         "<div style='margin:1mm 0 1.5mm'>업무시간(<b>18:00 전</b>)에 바꾸면 <b>그날 18:00 실행</b>에서 새 키워드의 <b>검색량과 노출 순위</b>를 조사합니다.</div>"
         "<ul><li><b>추가</b>: '키워드' 머리줄이 있는 기본 상품 블록의 마지막 키워드 아래에 행을 넣고 <b>A열</b>에 적기</li>"
         "<li><b>변경</b>: A열의 키워드 글자를 고치기</li>"
         "<li><b>삭제</b>: A열의 키워드를 지우기</li></ul>"
         "<span class='warn'>변경·삭제하면 이전 키워드의 지난 순위 기록은 지워집니다.</span> 11번째부터는 반영되지 않습니다.</div>"
         "</div></div>")

# ── 8쪽: FAQ ─────────────────────────────────────────────────────
P.append("""
<div class="page">
<h2>자주 묻는 질문</h2>
<table style='font-size:10.5pt'>
 <tr><th style="width:32%">질문</th><th>답</th></tr>
 <tr><td>오늘 고친 <span class='name'>[셀독] 관리 대장</span>이 결과에 안 보여요</td><td>18:00 이후에 고쳤다면 <b>다음 날 18:00 실행</b>에 반영됩니다. 18:00 전에 고쳤다면 다음 날 아침 결과를 보세요.</td></tr>
 <tr><td>밤에 넣은 키워드가 사라졌어요</td><td>실행 중(18:00~아침)에 결과 파일을 고치면 앱이 끝날 때 다시 써서 사라집니다. <b>낮에 다시 넣어 주세요.</b></td></tr>
 <tr><td>'미수집'과 0 은 뭐가 다른가요</td><td>0 = 자료를 받았는데 판매가 없음 · 미수집 = 자료를 아직 못 받음(비밀번호 오류·쿠팡 접속 실패 등). 미수집 계정은 <span class="tab">통합판매현황</span> ① 요약 '미수집 계정(전일)'에 이름이 나옵니다.</td></tr>
 <tr><td>판매 수량이 마이너스예요</td><td>그날 반품·취소가 판매보다 많았다는 뜻입니다(쿠팡 판매분석 값 그대로).</td></tr>
 <tr><td>계정 매출이 쿠팡 WING 화면보다 작아요</td><td>결과 파일은 <b>관리 상품만</b> 더합니다. 위탁자가 직접 등록해 파는 다른 상품은 빠집니다.</td></tr>
 <tr><td>노출 순위가 '49위밖'이에요</td><td>그날 쿠팡 검색 결과에서 살펴본 49개 안에 우리 상품이 없었다는 뜻입니다(광고 제외).</td></tr>
 <tr><td>상품이 계정목록에서 '⛔ 판매중지'로 바뀌었어요</td><td><span class='name'>[셀독] 관리 대장</span>에서 그 상품 행을 숨겼거나 상태를 판매중지로 했거나 <span class='name'>[셀독] 관리 대장</span> 에서 빠진 경우입니다. 다시 관리하려면 <span class='name'>[셀독] 관리 대장</span>에서 되돌리세요(다음 실행에 원복).</td></tr>
 <tr><td>쿠팡이 계정을 정지했어요</td><td>복구할 계정이면 <span class='name'>[셀독] 관리 대장</span>을 그대로 두세요. 관리를 끝낼 계정이면 계정아이디 칸에 취소선. 줄 삭제·전부 숨기기는 이력 삭제이니 하지 마세요.</td></tr>
 <tr><td>월초에 이번 달 숫자가 너무 작아요</td><td>① '이번 달 누계'는 1일부터 어제까지의 합이라 월초 며칠은 작게 보이는 것이 정상입니다. ⑤ 계정 순위는 최근 1개월(어제까지 30일) 합이라 월초에도 한 달치가 보입니다.</td></tr>
</table>
</div>""")

doc = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>[쿠팡] 데이터 분석 통계 구글 파일 활용 매뉴얼</title>"
       f"<style>{CSS}</style></head><body>{''.join(P)}</body></html>")
src = os.path.join(OUT, "매뉴얼_초안.html")
with open(src, "w", encoding="utf-8") as f:
    f.write(doc)
pdf = os.path.join(OUT, "[쿠팡] 데이터 분석 통계_활용 매뉴얼_초안.pdf")
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", "file:///" + src.replace("\\", "/")], capture_output=True, text=True, timeout=120)
print("chrome rc", r.returncode, (r.stderr or "")[-300:])
print(pdf, os.path.getsize(pdf) if os.path.exists(pdf) else "없음")
