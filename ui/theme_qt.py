"""통합 앱 디자인 테마(QSS 토큰) — 2026-10-03 확정 컨셉. SSOT=메모리 decision-design-concept-261003.

컨셉: 밝은 회색 바탕 + 흰 둥근 카드(얇은 테두리·그림자는 성능 위해 테두리 위주) · **강조색 = 보라 하나**
(선택·주 버튼·그래프, 경고만 빨강/주황) · **왼쪽 흰 사이드바**(회색 섹션 제목·아이콘·메뉴·숫자 배지) ·
상단 흰 바 + 큰 제목. 기존 app_qt(청록 Fluent)는 미접촉 — 이 테마는 통합 앱(app_integrated) 전용.

색은 토큰 상수로 두고 QSS 를 조립한다(유지보수·일관성). objectName 계약: header·headerTitle·headerSub·nav·accent.
"""
from __future__ import annotations

# ── 토큰(보라 컨셉) ───────────────────────────────────────────────
PURPLE = "#7c3aed"          # 강조(선택·주 버튼)
PURPLE_DARK = "#6d28d9"     # 호버/눌림
PURPLE_SOFT = "#ede9fe"     # 선택 배경(옅은 보라)
PURPLE_TINT = "#f5f3ff"     # 호버 배경(더 옅은 보라)
BG = "#f3f4f6"              # 밝은 회색 바탕
CARD = "#ffffff"            # 흰 카드
BORDER = "#e5e7eb"          # 얇은 테두리
TEXT = "#111827"            # 본문 글자
MUTED = "#6b7280"           # 보조 글자(섹션 제목·비활성)
HEAD_BG = "#f9fafb"         # 표 헤더(연회색)

QSS = f"""
* {{ font-family:'Segoe UI','Malgun Gothic'; font-size:13px; color:{TEXT}; }}
QMainWindow, QWidget {{ background:{BG}; }}
QLabel, QRadioButton, QCheckBox {{ background:transparent; }}

/* 상단 바 — 흰 바탕 + 아래 얇은 선(배너 아님) */
#header {{ background:{CARD}; border-bottom:1px solid {BORDER}; }}
#headerTitle {{ color:{TEXT}; font-size:19px; font-weight:800; }}
#headerSub {{ color:{MUTED}; font-size:12px; }}

/* 왼쪽 흰 사이드바 — 선택=옅은 보라+보라 글씨+왼쪽 보라 띠 */
QListWidget#nav {{ background:{CARD}; border:none; border-right:1px solid {BORDER}; outline:none; padding:8px 0; }}
QListWidget#nav::item {{ color:{MUTED}; padding:11px 16px; border-radius:8px; margin:2px 10px;
    border-left:3px solid transparent; }}
QListWidget#nav::item:hover {{ background:{PURPLE_TINT}; color:{TEXT}; }}
QListWidget#nav::item:selected {{ background:{PURPLE_SOFT}; color:{PURPLE}; font-weight:700;
    border-left:3px solid {PURPLE}; }}

/* 흰 둥근 카드 */
QGroupBox {{ background:{CARD}; border:1px solid {BORDER}; border-radius:12px; margin-top:14px; padding:12px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:3px 12px; background:{PURPLE_SOFT};
    color:{PURPLE}; border-radius:7px; font-weight:700; }}
QLabel#muted {{ color:{MUTED}; }}

/* 버튼 — 보통(연회색)·주 버튼(보라 알약) */
QPushButton {{ background:#f9fafb; border:1px solid {BORDER}; border-radius:8px; padding:8px 14px; color:{TEXT}; }}
QPushButton:hover {{ background:{PURPLE_TINT}; border-color:{PURPLE}; }}
QPushButton#accent {{ background:{PURPLE}; border:1px solid {PURPLE}; color:#ffffff; font-weight:700; padding:9px 18px; }}
QPushButton#accent:hover {{ background:{PURPLE_DARK}; border-color:{PURPLE_DARK}; }}
QPushButton#accent:disabled {{ background:#c4b5fd; border-color:#c4b5fd; }}

/* 입력 — 포커스/선택 보라 */
QLineEdit, QComboBox {{ background:{CARD}; border:1px solid #d1d5db; border-radius:8px; padding:6px 10px;
    selection-background-color:{PURPLE}; selection-color:#ffffff; }}
QLineEdit:focus, QComboBox:focus {{ border:1px solid {PURPLE}; }}
QComboBox::drop-down {{ border:none; width:22px; }}
QComboBox QAbstractItemView {{ background:{CARD}; border:1px solid {BORDER};
    selection-background-color:{PURPLE_SOFT}; selection-color:{TEXT}; outline:none; }}

/* 표 — 보라 선택 */
QTableWidget {{ background:{CARD}; border:1px solid {BORDER}; border-radius:12px; gridline-color:#f1f2f4;
    selection-background-color:{PURPLE_SOFT}; selection-color:{TEXT}; outline:none; }}
QHeaderView::section {{ background:{HEAD_BG}; color:{MUTED}; border:none; border-right:1px solid #eef0f3;
    padding:8px 6px; font-weight:700; }}
QTableWidget::item {{ padding:4px 6px; }}

/* 탭 — 선택 흰색+보라 글씨 */
QTabBar::tab {{ background:transparent; color:{MUTED}; padding:9px 18px; margin:6px 3px 0 3px;
    border-top-left-radius:10px; border-top-right-radius:10px; }}
QTabBar::tab:selected {{ background:{CARD}; color:{PURPLE}; font-weight:700; }}
QTabWidget::pane {{ border:none; background:{BG}; }}

/* 스크롤바 — 얇은 회색 */
QScrollBar:vertical {{ background:transparent; width:12px; margin:2px; }}
QScrollBar::handle:vertical {{ background:#d1d5db; border-radius:5px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:#d1d5db; border-radius:5px; min-width:30px; }}
"""
