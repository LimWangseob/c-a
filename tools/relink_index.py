"""경량 재링크 도구 — 결과 구글시트 `계정목록`의 상품명 링크(C열)만 즉시 재작성.

배경: 옛 코드가 계정목록 C열 링크를 **자기참조**(`#gid=<계정목록 자신>&range=A1`)로 써서, 상품명을
눌러도 그 사업자 통계 시트로 안 가는 계정이 남았다. 현재 코드는 올바른 링크(사업자 통계 시트 gid + 블록
헤더행)를 만들지만, **다시 써야** 반영된다. 전체 실행(로그인·판매수집·순위, 수 시간)을 돌리지 않고
**링크만** 고치기 위한 도구.

동작(로그인·수집·순위·통계 미러링 **없음**, 구글시트만 접근):
  1) 마스터 통계 xlsx 로드
  2) SA 키 확인 → 결과 구글시트 클라이언트 연결
  3) 사업자 통계 시트의 gid 를 **조회만**(client.sheet_id — 없으면 스킵, 새 시트 생성 안 함)
  4) roster_from_workbook 로 계정목록 로스터 산출(링크 gid+헤더행 포함)
  5) sync_index 로 계정목록 A·B·C·D·H 갱신(**마케팅 E~G·직원 키워드 미접촉** — 기존 함수 보장)

⚠ 다른 PC/세션에서 결과 시트에 쓰는 실행이 도는 중이면 **금지**(동시접근 충돌). 실행 종료 후에만.
⚠ 통계 시트 내용은 안 건드린다 — 이 도구는 계정목록 링크·상태·밴드색만 갱신한다.

사용: python tools/relink_index.py                 # 출력 URL=설정(gsheet/output_url)·마스터=기본 경로
      python tools/relink_index.py <출력시트 URL>    # URL 직접 지정
      python tools/relink_index.py <출력시트 URL> <마스터.xlsx>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from coupang_analytics import appconfig, config, gsheet_api, gsheet_index  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    output_url = args[0] if len(args) >= 1 else appconfig.get("gsheet/output_url", "")
    master = Path(args[1]) if len(args) >= 2 else Path("output") / f"{config.OUTPUT_FILE_PREFIX}_통계.xlsx"

    if not output_url:
        print("[중단] 결과(출력) 구글시트 URL 이 없습니다. 인자로 주거나 설정(gsheet/output_url)에 넣으세요.")
        return 1
    if not master.exists():
        print(f"[중단] 마스터가 없습니다: {master}")
        return 1
    if not gsheet_api.load_sa_info():
        print("[중단] 서비스계정(SA) 키가 없습니다. 앱 설정 탭에서 SA 키를 먼저 등록하세요.")
        return 1

    print(f"[재링크] 마스터={master.name} · 출력시트=…{str(output_url)[-24:]}")
    wb = OutputWorkbook.load(master)
    client = gsheet_api.GSheetClient(output_url)

    # 사업자 통계 시트 gid 를 **조회만** — 없는 시트는 스킵(roster 가 link_gid=None → 텍스트 폴백).
    biz_sheets = wb.account_sheets()          # 특수시트·계정목록 이미 제외됨(workbook.account_sheets)
    gids = {b: client.sheet_id(b) for b in biz_sheets}
    gids = {b: g for b, g in gids.items() if g is not None}
    missing = [b for b in biz_sheets if b not in gids]
    if missing:
        print(f"  [주의] 통계 시트 없는 사업자 {len(missing)}개는 링크 없이 텍스트로 둠(먼저 전체 실행 필요): {missing}")

    roster = gsheet_index.roster_from_workbook(wb, gids)
    plan = gsheet_index.sync_index(client, roster)

    linked = sum(1 for r in roster if r.link_gid is not None)
    print("\n=== 계정목록 재링크 완료 ===")
    print(f"  로스터 {len(roster)}행 · 링크 부여 {linked}행(사업자 통계 시트로 연결)")
    print(f"  갱신 {len(plan.updates)} · 신규 {len(plan.inserts)} · 판매중지 {len(plan.discontinue)}")
    print("  (마케팅 E~G·직원 키워드는 건드리지 않음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
