"""쿠팡 애널리틱스 데스크톱 UI (Tkinter).

현재 연결된 기능:
- 입력 분석용 엑셀 로드 (계정·상품)
- 네이버 검색광고 API 키 로드
- [키워드 추천] 상품/시드 → 추천 → 3~5개 확정 저장
- [순위 조회] 키워드+상품명으로 오가닉 순위 즉시 조회
- [전체 실행] 계정마다 로그인→판매분석→키워드→순위를 완결하고 통합 엑셀 1개로 저장(이어서 하기 지원)

브라우저 작업은 백그라운드 스레드에서 실행해 UI가 멈추지 않게 한다.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coupang_analytics import config, keyword_store  # noqa: E402
from coupang_analytics.apppaths import set_workdir  # noqa: E402
from coupang_analytics.browser import WingBrowser, find_chrome, reap_orphan_chrome  # noqa: E402
from coupang_analytics.input_list import parse_input_list, parse_password_file  # noqa: E402
from coupang_analytics.kw_ai import recommend_title  # noqa: E402
from coupang_analytics.kw_recommend import recommend, recommend_from_title  # noqa: E402
from coupang_analytics.kw_shopping import NaverShopCredentials  # noqa: E402
from coupang_analytics.pipeline import (master_exists, restore_master_from_gsheet,  # noqa: E402
                                        resumable_progress, run_full,
                                        select_keywords_stage, track_ranks_stage)
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.kw_volume import NaverAdApi, NaverCredentials, parse_credentials_file  # noqa: E402
from coupang_analytics.rank import make_matcher, organic_rank, warmup  # noqa: E402

_PROFILE = "data/chrome-ui"


def _shared_setting(group: str, name: str) -> str:
    """app_qt(PySide6 QSettings · 조직 'coupang-analytics' · 앱 'ui')가 저장한 값을 **PySide6 없이** 읽는다.

    Tkinter 폴백은 PySide6 부재 시 쓰이므로 그 의존을 피해야 한다 → Windows 레지스트리(winreg 표준 라이브러리)
    에서 직접 읽는다. QSettings NativeFormat 매핑: 'group/name' → HKCU\\Software\\coupang-analytics\\ui\\group 의
    값 name(실측 확인). 없거나 Windows 아니면 '' 반환(→ 해당 기능 비활성, 정상 — 조용한 실패 아님)."""
    try:
        import winreg
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"Software\coupang-analytics\ui\{group}") as k:
            val, _ = winreg.QueryValueEx(k, name)
        return str(val).strip() if val else ""
    except OSError:
        return ""


class RoundedTabs(ttk.Frame):
    """Windows 11 탐색기 스타일 탭 바(Canvas 직접 그림).

    - 선택 탭: **흰 둥근 카드**(밝게), 텍스트 진하게 — 아래 내용 영역과 이어짐.
    - 비선택 탭: 테두리 없이 텍스트만. 마우스 올리면 연한 둥근 하이라이트.
    - 탭 크기 고정(선택해도 안 커짐), 내용 영역 고정 높이(탭 전환해도 안 출렁임).
    """
    BAR_H = 46

    def __init__(self, master, content_height=320, bar_bg="#e6ebf1", body_bg="#ffffff",
                 sel="#ffffff", sel_fg="#0f172a", unsel_fg="#5b6b7f", hover="#d6dee8"):
        super().__init__(master)
        self._bar_bg, self._sel, self._sel_fg, self._unsel_fg, self._hover = bar_bg, sel, sel_fg, unsel_fg, hover
        self.canvas = tk.Canvas(self, height=self.BAR_H, highlightthickness=0, bg=bar_bg)
        self.canvas.grid(row=0, column=0, sticky="ew")
        self.body = tk.Frame(self, height=content_height, bg=body_bg)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_propagate(False)   # 고정 높이 유지(안 출렁임)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._tabs = []          # [text, frame, x1, x2]
        self._sel_i, self._hover_i = 0, -1
        self._font = tkfont.Font(family="Segoe UI", size=11)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self._set_hover(-1))
        self.canvas.bind("<Configure>", lambda e: self._draw())

    def add(self, frame, text):
        frame.grid(row=0, column=0, sticky="nsew", in_=self.body)
        self._tabs.append([text, frame, 0, 0])
        if len(self._tabs) == 1:
            frame.tkraise()
        self._draw()

    def select(self, i):
        if 0 <= i < len(self._tabs):
            self._sel_i = i
            self._tabs[i][1].tkraise()
            self._draw()

    def _round_top(self, x1, x2, y1, y2, r, fill):
        c = self.canvas
        c.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=fill, outline=fill)
        c.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=fill, outline=fill)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill)
        c.create_rectangle(x1, y1 + r, x2, y2, fill=fill, outline=fill)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        x, pad, r, y1, h = 8, 20, 12, 8, self.BAR_H
        for i, t in enumerate(self._tabs):
            w = self._font.measure(t[0]) + pad * 2
            x1, x2 = x, x + w
            t[2], t[3] = x1, x2
            selected = (i == self._sel_i)
            if selected:
                self._round_top(x1, x2, y1, h, r, self._sel)
            elif i == self._hover_i:
                self._round_top(x1 + 2, x2 - 2, y1 + 3, h, r, self._hover)
            fg = self._sel_fg if selected else self._unsel_fg
            c.create_text((x1 + x2) // 2, (y1 + h) // 2 + 1, text=t[0], fill=fg, font=self._font)
            x = x2 + 3

    def _hit(self, ex):
        for i, t in enumerate(self._tabs):
            if t[2] <= ex <= t[3]:
                return i
        return -1

    def _on_click(self, e):
        i = self._hit(e.x)
        if i >= 0:
            self.select(i)

    def _on_motion(self, e):
        self._set_hover(self._hit(e.x))

    def _set_hover(self, i):
        if i != self._hover_i:
            self._hover_i = i
            self.canvas.configure(cursor="hand2" if i >= 0 else "")
            self._draw()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("쿠팡 애널리틱스")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()   # 화면에 맞춰(밖으로 안 나가게)
        self.geometry(f"{min(1200, sw - 80)}x{min(1040, sh - 120)}")
        self.minsize(980, 720)
        self._setup_style()
        self.input_list = None
        self.naver_creds = None
        self.naver_shop = None   # NaverShopCredentials (경쟁강도용, 선택)
        self.ai_key = os.environ.get("OPENAI_API_KEY", "")
        self.product_business: dict[str, str] = {}
        self.creds_store = CredStore()
        self._build_header()
        self._build_tabs()
        self._build_log()
        # 노트북(탭)은 고정 높이(_NB_HEIGHT), 진행 로그가 나머지 세로 공간을 전부 차지(안 출렁임)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)              # 노트북 — 고정
        self.grid_rowconfigure(2, weight=1, minsize=320)  # 진행 로그 — 최대
        self._load_saved_secrets()

    def _setup_style(self):
        """세련된 통일 테마(색·글꼴·여백). 59세 가독성 위해 기본 글꼴을 키운다."""
        # Windows 11 탐색기 팔레트: 내용 영역 흰색, 크롬(탭바)만 옅은 회색, 파란 악센트
        WHITE, INK, MUTE, BORDER = "#ffffff", "#1f2937", "#5b6b7f", "#e5e9f0"
        self.configure(bg=WHITE)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        base = ("Segoe UI", 12)
        self.option_add("*Font", "{Segoe UI} 12")   # tk 위젯(메시지박스 등) 기본 글꼴(공백 글꼴명 → 중괄호)
        style.configure(".", font=base, background=WHITE, foreground=INK)
        style.configure("TFrame", background=WHITE)
        style.configure("TLabel", background=WHITE, foreground="#334155")
        style.configure("TCheckbutton", background=WHITE)
        style.configure("TRadiobutton", background=WHITE)
        style.configure("TButton", padding=(12, 7))
        style.map("TButton", background=[("active", "#eef2f7")])
        style.configure("Accent.TButton", padding=(16, 10), font=("Segoe UI", 12, "bold"))
        style.map("Accent.TButton",
                  background=[("!disabled", "#2563eb"), ("active", "#1d4ed8"), ("disabled", "#a9c3f2")],
                  foreground=[("!disabled", "white"), ("disabled", "#eef2f7")])
        # 카드(구획): 볼록 groove 대신 플랫 + 연한 테두리(Win11)
        style.configure("TLabelframe", background=WHITE, padding=12, relief="solid",
                        borderwidth=1, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=WHITE,
                        font=("Segoe UI", 11, "bold"), foreground="#1e293b")
        # 입력창: 얇은 테두리, 포커스 시 파랑
        style.configure("TEntry", fieldbackground=WHITE, bordercolor="#cbd5e1", relief="solid")
        style.map("TEntry", bordercolor=[("focus", "#2563eb")])
        style.configure("TCombobox", fieldbackground=WHITE, bordercolor="#cbd5e1")
        # 목록(표) = Win11 리스트: 흰 배경·플랫 헤더·행 높이·선택 하이라이트
        style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK,
                        rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background="#f3f5f8", foreground="#475569",
                        relief="flat", font=("Segoe UI", 10, "bold"), padding=(6, 6))
        style.map("Treeview.Heading", background=[("active", "#e8edf3")])
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", INK)])
        style.configure("Muted.TLabel", background=WHITE, foreground=MUTE)
        style.configure("Header.TFrame", background="#0f172a")
        style.configure("HeaderTitle.TLabel", background="#0f172a", foreground="#ffffff",
                        font=("Segoe UI", 19, "bold"))
        style.configure("HeaderSub.TLabel", background="#0f172a", foreground="#93a4bd",
                        font=("Segoe UI", 10))

    def _scrollable(self, parent):
        """세로 스크롤되는 내부 프레임 반환(내용 긴 탭이 노트북 높이를 밀어내지 않게)."""
        canvas = tk.Canvas(parent, highlightthickness=0, bg="#ffffff")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all(
            "<MouseWheel>", lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _build_header(self):
        head = ttk.Frame(self, style="Header.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        inner = ttk.Frame(head, style="Header.TFrame")
        inner.pack(fill="x", padx=18, pady=14)
        ttk.Label(inner, text="🛒  쿠팡 애널리틱스", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(inner, text="계정별 상품 노출순위(PC·모바일)·판매지표 자동 수집 · AI 키워드 분석",
                  style="HeaderSub.TLabel").pack(anchor="w", pady=(2, 0))

    # ── 레이아웃 ──────────────────────────────────────────────
    # 설정 탭에 노출할 정책값: (라벨, config 속성명, 변환)
    _NB_HEIGHT = 320   # 탭(내용) 영역 고정 높이 — 탭 전환해도 출렁이지 않음. 나머지는 로그창

    def _build_tabs(self):
        self.nb = nb = RoundedTabs(self, content_height=self._NB_HEIGHT,   # Win11 탐색기 스타일 둥근 탭
                                   bar_bg="#f3f5f8", body_bg="#ffffff", sel="#ffffff",
                                   sel_fg="#0f172a", unsel_fg="#64748b", hover="#e4e9f0")
        nb.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)   # 탭바가 폭 전체(탐색기처럼)
        self._build_settings_tab(nb)   # 내용 긴 탭은 스크롤(_scrollable)
        self._build_kw_tab(nb)
        self._build_rank_tab(nb)
        self._build_collect_tab(nb)

    def _build_settings_tab(self, nb):
        outer = ttk.Frame(nb.body)
        nb.add(outer, text="설정")
        tab = self._scrollable(outer)   # 내용이 길어도 노트북 높이를 안 밀어내게 스크롤
        # 파일 · API 키
        fk = ttk.LabelFrame(tab, text="파일 · API 키")
        fk.pack(fill="x", padx=8, pady=6)
        self.input_var = tk.StringVar(value="(입력 분석용 엑셀 미선택)")
        self.naver_var = tk.StringVar(value="(네이버 API 키 미선택)")
        self.openai_var = tk.StringVar(
            value="(OpenAI 키: " + ("환경변수 감지됨)" if self.ai_key else "미설정 — 키워드 추출 불가)"))
        self.shop_var = tk.StringVar(value="(선택) 네이버쇼핑 키 미설정 — 경쟁강도 미반영")
        self.pw_var = tk.StringVar(value="(입력 엑셀에 '비밀번호' 컬럼 있으면 자동 저장 · 별도 파일만 이 버튼)")
        for row, (text, cmd, var) in enumerate((
            ("입력 엑셀 열기", self.load_input, self.input_var),
            ("(선택) 비번 파일", self.load_passwords, self.pw_var),
            ("네이버 API 키 열기", self.load_naver, self.naver_var),
            ("OpenAI(ChatGPT) API 키 입력", self.load_openai, self.openai_var),
            ("(선택) 네이버쇼핑 키 입력", self.load_naver_shop, self.shop_var),
        )):
            ttk.Button(fk, text=text, width=16, command=cmd).grid(row=row, column=0, padx=5, pady=4)
            ttk.Label(fk, textvariable=var, width=58).grid(row=row, column=1, sticky="w")
        # 키워드/순위 등 세부 설정값 입력란은 제거(사용자 미사용 · 영속 저장도 안 됨). 값은 config.py 에서 관리.

    def _build_kw_tab(self, nb):
        tab = ttk.Frame(nb.body)
        nb.add(tab, text="키워드 추천")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4)
        ttk.Label(bar, text="상품:").pack(side="left")
        self.kw_product_var = tk.StringVar()
        self.kw_product_combo = ttk.Combobox(bar, textvariable=self.kw_product_var, width=40, state="readonly")
        self.kw_product_combo.pack(side="left", padx=4)
        self.kw_product_combo.bind("<<ComboboxSelected>>", self._prefill_seed)
        ttk.Label(bar, text="시드(선택·비우면 제목기반):").pack(side="left", padx=(10, 0))
        self.seed_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.seed_var, width=18).pack(side="left", padx=4)
        self.kw_run_btn = ttk.Button(bar, text="추천 실행", command=self.do_recommend, style="Accent.TButton")
        self.kw_run_btn.pack(side="left", padx=6)

        cols = ("키워드", "검색량", "클릭수", "경쟁", "광고깊이", "로켓비율", "광고", "점수", "비고")
        self.kw_tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="extended", height=8)
        for c, w in zip(cols, (200, 70, 70, 55, 75, 70, 55, 60, 70)):
            self.kw_tree.heading(c, text=c)
            self.kw_tree.column(c, width=w, anchor="center")
        self.kw_tree.column("키워드", anchor="w")
        self.kw_tree.pack(fill="both", expand=True, pady=4)
        ttk.Label(tab, text="상품 제목에서 다양한 키워드를 조사해 추천합니다. 3~5개 선택(Ctrl/Shift) 후 저장하세요.").pack(anchor="w")
        btns = ttk.Frame(tab)
        btns.pack(anchor="e", pady=4)
        self.title_btn = ttk.Button(btns, text="상품명 추천(선택 키워드 기반)", command=self.do_recommend_title)
        self.title_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="선택 키워드 저장(3~5개)", command=self.save_keywords).pack(side="left", padx=4)

    def do_recommend_title(self):
        """선택(없으면 상위) 키워드 + 상품 제목 → 검색 최적화 상품명 제안(OpenAI)."""
        if not self.ai_key:
            messagebox.showwarning("키 필요", "상품명 추천은 OpenAI(ChatGPT) API 키가 필요합니다.")
            return
        product = self.kw_product_var.get().strip()
        if not product:
            messagebox.showwarning("입력 필요", "상품을 먼저 선택하세요.")
            return
        sel = self.kw_tree.selection() or self.kw_tree.get_children()
        kws = [self.kw_tree.item(i, "values")[0] for i in sel][:8]
        if not kws:
            messagebox.showwarning("키워드 필요", "먼저 '추천 실행'으로 키워드를 조사하세요.")
            return
        brand = self.product_business.get(product, "")
        key = self.ai_key
        self.log(f"[상품명] '{product[:24]}' + 키워드 {kws} → 추천 생성 중…")

        def task():
            return recommend_title(product, kws, brand=brand, api_key=key)
        self.run_bg(task, on_done=self._show_title, btn=self.title_btn)

    def _show_title(self, title: str):
        self.log(f"[상품명] 추천 → {title}")
        self.clipboard_clear()
        self.clipboard_append(title)
        messagebox.showinfo("상품명 추천", f"제안 상품명(클립보드 복사됨):\n\n{title}")

    def _build_rank_tab(self, nb):
        tab = ttk.Frame(nb.body)
        nb.add(tab, text="순위 조회")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=6)
        ttk.Label(bar, text="키워드:").pack(side="left")
        self.rank_kw_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.rank_kw_var, width=22).pack(side="left", padx=4)
        ttk.Label(bar, text="내 상품명 일부:").pack(side="left", padx=(10, 0))
        self.rank_name_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.rank_name_var, width=22).pack(side="left", padx=4)
        self.rank_btn = ttk.Button(bar, text="순위 조회", command=self.do_rank, style="Accent.TButton")
        self.rank_btn.pack(side="left", padx=6)
        ttk.Label(tab, text=f"광고 제외 오가닉 순위를 조회합니다(상한 {config.RANK_SCAN_MAX}위, 밖이면 "
                            f"{config.RANK_SCAN_MAX}위). 로그인 불필요.").pack(anchor="w", padx=4)

    def _build_collect_tab(self, nb):
        tab = ttk.Frame(nb.body)
        nb.add(tab, text="전체 실행")
        # 전체 실행 (계정마다 로그인 + 수집을 한 번에 완결)
        run = ttk.LabelFrame(tab, text="전체 실행 (계정마다 로그인→판매분석→키워드→순위 → 통합 엑셀)")
        run.pack(fill="x", padx=8, pady=6)
        topbar = ttk.Frame(run)
        topbar.pack(anchor="w", fill="x", padx=6, pady=6)
        # 단계별 실행 — ① 로그인 판매수집(상품ID·지표·재고) / ② 키워드 선정 / ③ 노출순위(②③ 로그인 불필요)
        # ① 판매수집 = 반자동만(보이는 신뢰 창 로그인). 무인 offscreen 방식은 차단 취약으로 폐지(사용자 요청).
        self.sales_semi_btn = ttk.Button(topbar, text="① 판매수집",
                                         command=lambda: self.do_run_full(keywords_off=True, sales_semi=True))
        self.sales_semi_btn.pack(side="left", padx=(0, 4))
        self.kw_btn = ttk.Button(topbar, text="② 키워드 선정", command=self.do_select_keywords)
        self.kw_btn.pack(side="left", padx=4)
        # ③ 순위(자동, 비로그인 검색)은 차단 위험이 커 현실성이 없어 제거(사용자 요청). 반자동만 유지.
        self.track_semi_btn = ttk.Button(topbar, text="③ 순위(반자동)",
                                         command=lambda: self.do_track_ranks(semi=True))
        self.track_semi_btn.pack(side="left", padx=4)
        self.track_stop_btn = ttk.Button(topbar, text="반자동 중지", command=self._stop_semi,
                                         state="disabled")
        self.track_stop_btn.pack(side="left", padx=4)
        self.pipeline_btn = ttk.Button(topbar, text="전체 실행(①반자동→②→③반자동)",
                                       command=lambda: self.do_run_full(keywords_off=False, sales_semi=True),
                                       style="Accent.TButton")
        self.pipeline_btn.pack(side="left", padx=(4, 0))
        ttk.Label(run, justify="left", foreground="#64748b", text=(
            "계정마다 [로그인→판매분석→키워드→PC·모바일 순위]를 완결하고 통합 엑셀에 누적 저장합니다. "
            "로그인은 창 없이 자동, 2차인증 필요할 때만 창이 뜹니다(로그로 예고). 진행상황은 아래 로그에서 확인."
        ), wraplength=980).pack(anchor="w", padx=6, pady=(0, 6))
        # 실행 모드 — 화면에서 3택(하나만 선택). 실행 시 예/아니오만 확인.
        moderow = ttk.Frame(tab)
        moderow.pack(fill="x", padx=10, pady=(2, 2))
        self.run_mode = tk.StringVar(value="resume")   # resume | redo | newall
        ttk.Label(moderow, text="실행 모드:").pack(side="left")
        ttk.Radiobutton(moderow, text="이어서 하기", variable=self.run_mode,
                        value="resume").pack(side="left", padx=(8, 0))
        ttk.Radiobutton(moderow, text="오늘 것만 다시 수집", variable=self.run_mode,
                        value="redo").pack(side="left", padx=(8, 0))
        ttk.Radiobutton(moderow, text="통계 전체 초기화(백업 후)", variable=self.run_mode,
                        value="newall").pack(side="left", padx=(8, 4))
        self.grow_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(moderow, text="새 키워드 발굴 추가 (이어쓰기 시, 상한 7개·하루 2개)",
                        variable=self.grow_var).pack(side="left", padx=(16, 0))
        # 수집 기간 — 한 줄로 압축(로그창을 더 크게)
        box = ttk.Frame(tab)
        box.pack(fill="x", padx=10, pady=(2, 4))
        self.collect_mode = tk.StringVar(value="today")
        yday = (date.today() - timedelta(days=1)).isoformat()   # 기본값=확정일(어제, D-1)
        self.from_var = tk.StringVar(value=yday)
        self.to_var = tk.StringVar(value=yday)
        ttk.Label(box, text="수집 기간:").pack(side="left")
        ttk.Radiobutton(box, text="당일(=어제, 최신 확정일)", variable=self.collect_mode, value="today",
                        command=self._toggle_range).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(box, text="기간", variable=self.collect_mode, value="range",
                        command=self._toggle_range).pack(side="left", padx=(8, 4))
        self.from_entry = ttk.Entry(box, textvariable=self.from_var, width=12)
        self.from_entry.pack(side="left", padx=2)
        ttk.Label(box, text="~").pack(side="left", padx=2)
        self.to_entry = ttk.Entry(box, textvariable=self.to_var, width=12)
        self.to_entry.pack(side="left", padx=2)
        ttk.Label(box, text="(기간: 판매분석=합계 · 노출순위=오늘)", foreground="#94a3b8").pack(side="left", padx=8)
        self._toggle_range()

    def _toggle_range(self):
        state = "normal" if self.collect_mode.get() == "range" else "disabled"
        self.from_entry.config(state=state)
        self.to_entry.config(state=state)

    def _run_dates(self):
        # (판매조회_from, 판매조회_to, 컬럼라벨_실행날짜). 판매는 전일(D-1), 컬럼 제목은 실제 작업한 날(app_qt 와 동일).
        if self.collect_mode.get() == "today":
            today = date.today().isoformat()
            d1 = (date.today() - timedelta(days=1)).isoformat()
            return d1, d1, today
        dt = self.to_var.get().strip()
        return self.from_var.get().strip(), dt, dt

    def do_run_full(self, keywords_off: bool = False, sales_semi: bool = False):
        if self.input_list is None:
            messagebox.showwarning("입력 필요", "설정 탭에서 입력 엑셀을 먼저 여세요.")
            return
        if self.naver_creds is None:
            messagebox.showwarning("키 필요", "설정 탭에서 네이버 API 키를 먼저 여세요.")
            return
        if not self.ai_key:   # 키워드 추출은 AI 필수(토큰 폴백 폐지)
            messagebox.showwarning("키 필요", "키워드 추출에 OpenAI(ChatGPT) API 키가 필요합니다. "
                                   "설정 탭에서 OpenAI API 키를 입력한 뒤 다시 실행하세요.")
            return
        df, dt, dlabel = self._run_dates()
        # 날짜를 직접 지정(당일 자동이 아님)하면 순위 조회 제외 = 그 날짜 판매데이터만 채움(차단 회피)
        skip_ranks = self.collect_mode.get() != "today"
        n = sum(len(a.products) for a in self.input_list.accounts)
        title = (("① 판매수집(반자동)" if sales_semi else "① 판매수집") if keywords_off
                 else ("전체 실행(① 반자동 로그인)" if sales_semi else "전체 실행"))
        # 실행 모드 3택 → 여기선 예/아니오만 확인.
        #  · resume(이어서): 오늘 진행분 있으면 이어서(완료 계정 건너뜀), 아니면 마스터에 오늘 컬럼 추가.
        #  · redo(오늘 처음/다시): carry + redo_today → 오늘 컬럼·완료스탬프 초기화 후 전 계정 재수집(어제까지 유지).
        #  · newall(전체 새로): carry_forward=False → 기존 마스터 백업 후 빈 통계로 새로.
        mode = self.run_mode.get()
        newall, redo = mode == "newall", mode == "redo"
        resume = carry = redo_today = False
        # fix ③: 마스터가 없지만 결과 구글시트가 있으면 복원(첫 실행 오판·과거 통계 유실 방지). 초기화(newall)는 제외.
        gs_out_early = _shared_setting("gsheet", "output_url")
        if not newall and not master_exists() and gs_out_early:
            self.log("[통계] 마스터가 없어 결과 구글시트에서 복원을 시도합니다…")
            restore_master_from_gsheet("output", gs_out_early, self.log)
        meta = resumable_progress() if not (newall or redo) else None
        if newall:
            mode_desc = "통계 전체 초기화(백업 후) — ⚠ 기존 통계 마스터는 백업 후 빈 통계로 새로(누적 시계열 끊김)"
        elif redo:
            if master_exists():
                carry = redo_today = True
                mode_desc = f"오늘 것만 다시 수집 — 오늘({dt}) 초기화 후 전 계정 재수집(어제까지 유지·키워드 동결)"
            else:
                mode_desc = f"새 통계 시작(첫 실행 — 마스터 없음·구글시트 복원 불가), 기간 {df}~{dt}"
        elif meta:
            resume = True
            carry = bool(meta.get("carry", False))
            df, dt = meta["date_from"], meta["date_to"]
            dlabel = meta.get("date_label") or dlabel
            mode_desc = f"이어서 하기 — 오늘 미완료분 이어서(완료 {len(meta['done'])}개 건너뜀), 기간 {df}~{dt}"
        elif master_exists():
            carry = True
            mode_desc = f"이어서 하기 — 오늘({dt}) 컬럼 추가(키워드 동결)"
        else:
            mode_desc = f"새 통계 시작(첫 실행 — 마스터 없음·구글시트 복원 불가), 기간 {df}~{dt}"
        grow = carry and not redo_today and self.grow_var.get()   # 발굴 추가는 이어쓰기 때만
        if not messagebox.askyesno(f"{title} 확인",
                                   f"{mode_desc}\n대상: 상품 {n}개"
                                   f"{' · 새 키워드 발굴 추가' if grow else ''}\n\n실행할까요?"):
            self.log(f"[{title}] 취소됨")
            return
        input_list, naver_creds, key = self.input_list, self.naver_creds, self.ai_key
        gs_out = _shared_setting("gsheet", "output_url")   # app_qt에 등록된 결과 구글시트 링크(있으면 반영)
        mode_txt = ("오늘다시 " if redo_today else "이어서 ") if (resume or redo_today) else \
                   ("통계이어쓰기 " if carry else "새통계 ")
        stage_txt = " · ①판매수집(키워드·순위 없음)" if keywords_off else \
            (" · 순위 제외(판매데이터만)" if skip_ranks and not resume else "")
        self.log(f"[{'판매수집' if keywords_off else '전체실행'}] {mode_txt}시작 — 상품 {n}개, 기간 {df}~{dt}"
                 f"{' · 새 키워드 발굴 추가' if grow else ''}{stage_txt}")
        btn = self.sales_semi_btn if keywords_off else self.pipeline_btn
        self.log("[① 반자동] 보이는 창에서 로그인(2차인증은 직접) 후 판매수집 — 창이 뜨면 두세요")
        # 전체실행은 오프스크린을 전혀 안 쓴다: ①반자동 판매수집 → ②키워드선정(노출측정 없음) → ③반자동 순위.
        stop = None
        if not keywords_off:
            self._semi_stop = threading.Event()
            self.track_stop_btn.config(state="normal")
            stop = self._semi_stop

        def task():
            naver = NaverAdApi(naver_creds)
            # ① 반자동 판매수집 — 순위·키워드·노출측정 전무(offscreen 미사용)
            snap = run_full(input_list, naver, ai_key=key, date_from=df, date_to=dt,
                            get_password=self._account_pw, resume=resume, carry_forward=carry,
                            grow_keywords=False, skip_ranks=True, redo_today=redo_today,
                            sales_semi=True, date_label=dlabel, keywords_off=True, on_log=self.log,
                            gsheet_output_url=gs_out)
            if keywords_off:                        # ① 단독 실행 → 판매데이터만 채우고 종료
                return snap
            if stop is not None and stop.is_set():
                return snap
            # ② 키워드 선정 — 공개검색(노출측정) 없이 AI 선정만(로그인 불필요·동결분 유지)
            self.log("[전체실행] ② 키워드 선정 — 노출측정 없이 AI 선정(동결분 유지)")
            select_keywords_stage(naver, key, grow=grow, on_log=self.log, gsheet_output_url=gs_out)
            if stop is not None and stop.is_set():
                return snap
            # ③ 반자동 순위 — 보이는 창에서 자동 타이핑·검색(차단 회피)
            self.log("[전체실행] ③ 반자동 순위 — 보이는 창 자동 타이핑(중지: '반자동 중지')")
            return track_ranks_stage(semi=True,
                                     should_stop=(stop.is_set if stop is not None else (lambda: False)),
                                     on_log=self.log, gsheet_output_url=gs_out)

        def done(p):
            if not keywords_off:
                self.track_stop_btn.config(state="disabled")
            self._pipeline_done(p)
        self.run_bg(task, on_done=done, btn=btn)

    def do_select_keywords(self):
        """② 키워드 선정 — 로그인 불필요. 최신 결과 워크북 상품에 키워드만 채운다(순위 없음)."""
        if self.input_list is None or self.naver_creds is None or not self.ai_key:
            messagebox.showwarning("키/입력 필요",
                                   "설정 탭에서 입력 엑셀·네이버 API·OpenAI 키를 먼저 준비하세요.")
            return
        if not (master_exists() or resumable_progress()):
            messagebox.showwarning("먼저 ① 판매수집",
                                   "결과 파일이 없습니다. ① 판매수집을 먼저 실행해 상품을 수집하세요.")
            return
        naver_creds, key = self.naver_creds, self.ai_key
        gs_out = _shared_setting("gsheet", "output_url")
        self.log("[키워드 선정] 시작 — 순위 조회 없이 키워드만 선정(로그인 불필요)")

        def task():
            return select_keywords_stage(NaverAdApi(naver_creds), key, grow=False, on_log=self.log,
                                         gsheet_output_url=gs_out)
        self.run_bg(task, on_done=self._pipeline_done, btn=self.kw_btn)

    def do_track_ranks(self, semi: bool = True):
        """③ 노출순위 조회(반자동) — 로그인 불필요. 창이 뜨면 로그에 안내되는 키워드를 그 창에서 직접
        검색, 앱이 화면을 읽어 기록(자동 검색을 안 해 차단이 안 생김). 자동 방식은 차단 위험으로 폐지.
        """
        if not (master_exists() or resumable_progress()):
            messagebox.showwarning("먼저 ①②",
                                   "결과 파일이 없습니다. ① 판매수집·② 키워드 선정을 먼저 실행하세요.")
            return
        self._semi_stop = threading.Event()
        self.track_stop_btn.config(state="normal")
        self.log("[반자동 순위] 시작 — 뜬 창에서 안내 키워드를 직접 검색하세요(중지: '반자동 중지')")
        should_stop = self._semi_stop.is_set
        gs_out = _shared_setting("gsheet", "output_url")

        def task_semi():
            return track_ranks_stage(semi=True, should_stop=should_stop, on_log=self.log,
                                     gsheet_output_url=gs_out)

        def done(p):
            self.track_stop_btn.config(state="disabled")
            self._pipeline_done(p)
        self.run_bg(task_semi, on_done=done, btn=self.track_semi_btn)

    def _stop_semi(self):
        """반자동 순위 중지 요청 — 현재 키워드까지만 처리하고 멈춤."""
        ev = getattr(self, "_semi_stop", None)
        if ev is not None:
            ev.set()
            self.log("[반자동 순위] 중지 요청 — 현재 키워드 처리 후 멈춥니다")
        self.track_stop_btn.config(state="disabled")

    def _pipeline_done(self, path):
        # 팝업 창 없이 로그에만 상태 기록(갑작스러운 창으로 놀라지 않도록)
        self.log("=" * 50)
        if path:
            self.log("[전체실행] ✅ 완료 — 통합 엑셀 생성됨")
            self.log(f"[전체실행] 파일: {path}")
        else:
            self.log("[전체실행] ⏹ 종료(중지 요청 또는 결과 없음) — 진행분은 저장됨")
        self.log("=" * 50)

    def _build_log(self):
        # LabelFrame 대신 슬림 프레임(제목틀 여백 제거 → 콘솔을 더 크게)
        frame = ttk.Frame(self)
        frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 8))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        ttk.Label(bar, text="진행 로그", font=("Segoe UI", 11, "bold"),
                  foreground="#1e293b").pack(side="left", padx=(2, 12))
        ttk.Button(bar, text="복사", command=self.copy_log).pack(side="left", padx=2)
        ttk.Button(bar, text="지우기", command=self.clear_log).pack(side="left", padx=2)
        ttk.Label(bar, text="(드래그 후 Ctrl+C 복사)", foreground="#94a3b8").pack(side="left", padx=8)
        # 콘솔 스타일(다크·모노스페이스). 남는 세로 공간을 전부 차지
        self.log_text = scrolledtext.ScrolledText(
            frame, height=20, wrap="word", bg="#0b1220", fg="#e2e8f0",
            insertbackground="#e2e8f0", font=("Consolas", 11), relief="flat",
            borderwidth=0, padx=10, pady=8)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_text.bind("<Key>", self._log_readonly)   # 편집 차단, 복사·선택은 허용
        for tag, color in (("ok", "#4ade80"), ("err", "#f87171"),
                           ("warn", "#fbbf24"), ("head", "#60a5fa")):
            self.log_text.tag_config(tag, foreground=color)
        self.log_text.tag_config("head", foreground="#60a5fa", font=("Consolas", 11, "bold"))

    @staticmethod
    def _log_readonly(event):
        allow = {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
                 "Shift_L", "Shift_R", "Control_L", "Control_R"}
        if event.keysym in allow:
            return None
        if (event.state & 0x4) and event.keysym.lower() in ("c", "a"):  # Ctrl+C / Ctrl+A
            return None
        return "break"

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log_text.get("1.0", "end-1c"))
        self.log("[로그] 전체 복사됨 (클립보드)")

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    # ── 공통 ─────────────────────────────────────────────────
    @staticmethod
    def _log_tag(msg: str) -> str:
        """로그 한 줄의 색 태그(콘솔 가독성): 구획선/완료/오류/경고 구분."""
        if msg.startswith("==") or "====" in msg:
            return "head"
        if "오류" in msg or "실패" in msg or "차단" in msg or "[오류]" in msg:
            return "err"
        if "✅" in msg or "완료" in msg or "성공" in msg or "통과" in msg or "저장됨" in msg:
            return "ok"
        if "⚠" in msg or "경고" in msg or "미완료" in msg or "건너뜀" in msg or "데이터 없음" in msg:
            return "warn"
        return ""

    def log(self, msg: str):
        def append():
            tag = self._log_tag(msg)
            self.log_text.insert("end", config.format_log(msg) + "\n", (tag,) if tag else ())   # 표준 로그 포맷
            # 24/365 상시가동 메모리 방지: 최근 N줄만 유지(오래된 줄 폐기). Text 는 무한 누적된다.
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > config.UI_LOG_MAX_LINES:
                self.log_text.delete("1.0", f"{lines - config.UI_LOG_MAX_LINES}.0")
            self.log_text.see("end")
        self.after(0, append)

    def run_bg(self, task, on_done=None, btn=None):
        if btn:
            btn.config(state="disabled")

        def worker():
            result, err = None, None
            try:
                result = task()
            except Exception as exc:  # UI로 오류 전달
                err = exc

            def finish():
                if btn:
                    btn.config(state="normal")
                if err is not None:
                    self.log(f"[오류] {err.__class__.__name__}: {err}")
                elif on_done is not None:
                    on_done(result)
            self.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    # ── 설정 로드 ─────────────────────────────────────────────
    def load_input(self):
        path = filedialog.askopenfilename(title="입력 분석용 엑셀", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        il = parse_input_list(path)
        self.input_list = il
        self.product_business.clear()
        products: list[str] = []
        for a in il.accounts:
            for p in a.products:
                products.append(p.name)
                self.product_business[p.name] = a.business_name
        self.kw_product_combo["values"] = products
        self.input_var.set(f"{Path(path).name}  (계정 {len(il.accounts)}, 상품 {len(products)})")
        self.log(f"[입력] {len(il.accounts)}계정 · 상품 {len(products)}개 로드 · 오류 {len(il.errors)}건")
        for e in il.errors[:5]:
            self.log(f"   - 입력오류: {e}")
        self._store_passwords_from(path, quiet=True)   # 같은 파일에 비밀번호 컬럼 있으면 함께 저장

    def _store_passwords_from(self, path, quiet: bool = False) -> int:
        """엑셀에서 계정아이디+비밀번호를 읽어 이 PC 전용 암호화 저장. 반환=저장 개수."""
        try:
            pw_map = parse_password_file(path)
        except Exception as exc:
            if not quiet:
                messagebox.showwarning("비밀번호 파일 오류", str(exc))
            return 0   # 비밀번호 컬럼 없음(입력파일 겸용) → 조용히 넘어감
        saved = 0
        for aid, pw in pw_map.items():
            try:
                self.creds_store.set_password(aid, pw)
                saved += 1
            except Exception as exc:
                self.log(f"[비번] {aid} 저장 실패: {exc.__class__.__name__}")
        if saved:
            self.pw_var.set(f"{Path(path).name}  (계정 {saved}개 비번 암호화 저장)")
            self.log(f"[비번] {saved}개 계정 비밀번호 저장됨 (이 PC 전용 암호화, 공유·git 안 됨). "
                     "순차 로그인 시 자동입력.")
        elif not quiet:
            self.log("[비번] 비밀번호를 찾지 못했습니다 (계정아이디/비밀번호 컬럼 확인).")
        return saved

    def load_passwords(self):
        """계정아이디+비밀번호 엑셀 → 이 PC 전용 암호화 저장(순차 로그인 시 폼 자동입력)."""
        path = filedialog.askopenfilename(
            title="계정 비밀번호 엑셀 (계정아이디+비밀번호 컬럼)",
            filetypes=[("Excel", "*.xlsx"), ("All", "*.*")])
        if path:
            self._store_passwords_from(path, quiet=False)

    def _account_pw(self, account_id: str):
        """저장된 계정 비밀번호 조회(없으면 None → 수동 로그인)."""
        try:
            return self.creds_store.get_password(account_id) or None
        except Exception:
            return None

    def load_naver(self):
        path = filedialog.askopenfilename(title="네이버 검색광고 API 키 파일", filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        c = self.naver_creds = parse_credentials_file(path)
        self.naver_var.set(f"{Path(path).name}  (고객 {c.customer_id})")
        try:
            self.creds_store.set_password("__naver__", json.dumps(
                {"customer_id": c.customer_id, "api_key": c.api_key, "secret_key": c.secret_key}))
            self.log("[네이버] API 키 로드·저장됨 (다음 실행부터 자동)")
        except Exception as exc:
            self.log(f"[네이버] 로드됨(저장 실패: {exc.__class__.__name__})")

    def load_openai(self):
        key = simpledialog.askstring("OpenAI API 키", "sk-... 키를 입력하세요", show="*", parent=self)
        if not key:
            return
        self.ai_key = key.strip()
        self.openai_var.set("(OpenAI 키: 입력됨 — 저장됨)")
        try:
            self.creds_store.set_password("__openai__", self.ai_key)
            self.log("[OpenAI] API 키 입력·저장됨 (다음 실행부터 자동)")
        except Exception as exc:
            self.log(f"[OpenAI] 입력됨(저장 실패: {exc.__class__.__name__})")

    def load_naver_shop(self):
        """네이버쇼핑 검색 OpenAPI 키(개발자센터 Client ID/Secret) 입력 — 경쟁강도용(선택)."""
        cid = simpledialog.askstring("네이버쇼핑 Client ID", "개발자센터 Client ID", parent=self)
        if not cid:
            return
        sec = simpledialog.askstring("네이버쇼핑 Client Secret", "개발자센터 Client Secret", show="*", parent=self)
        if not sec:
            return
        self.naver_shop = NaverShopCredentials(cid.strip(), sec.strip())
        self.shop_var.set("(네이버쇼핑 키: 입력됨 — 경쟁강도 반영)")
        try:
            self.creds_store.set_password("__naver_shop__", json.dumps(
                {"client_id": self.naver_shop.client_id, "client_secret": self.naver_shop.client_secret}))
            self.log("[네이버쇼핑] 키 입력·저장됨 (경쟁강도 선정 반영)")
        except Exception as exc:
            self.log(f"[네이버쇼핑] 입력됨(저장 실패: {exc.__class__.__name__})")

    def _load_saved_secrets(self):
        """저장된 네이버/OpenAI 키를 자동 로드 (한 번 입력하면 계속 사용)."""
        try:
            nj = self.creds_store.get_password("__naver__")
        except Exception:
            nj = None
        if nj:
            d = json.loads(nj)
            self.naver_creds = NaverCredentials(d["customer_id"], d["api_key"], d["secret_key"])
            self.naver_var.set(f"저장된 네이버 키 (고객 {d['customer_id']})")
            self.log("[네이버] 저장된 키 자동 로드됨")
        try:
            sj = self.creds_store.get_password("__naver_shop__")
        except Exception:
            sj = None
        if sj:
            d = json.loads(sj)
            self.naver_shop = NaverShopCredentials(d["client_id"], d["client_secret"])
            self.shop_var.set("(네이버쇼핑 키: 저장됨 — 경쟁강도 반영)")
            self.log("[네이버쇼핑] 저장된 키 자동 로드됨")
        try:
            ak = self.creds_store.get_password("__openai__")
        except Exception:
            ak = None
        if ak:
            self.ai_key = ak
            self.openai_var.set("(OpenAI 키: 저장됨 — 자동 로드)")
            self.log("[OpenAI] 저장된 키 자동 로드됨")

    def _prefill_seed(self, _evt=None):
        self.seed_var.set("")  # 기본은 상품 제목 기반 추천; 시드를 입력하면 그 값을 우선 사용

    # ── 키워드 추천 ───────────────────────────────────────────
    def do_recommend(self):
        if self.naver_creds is None:
            messagebox.showwarning("키 필요", "네이버 API 키를 먼저 불러오세요.")
            return
        seed = self.seed_var.get().strip()
        product = self.kw_product_var.get().strip()
        if not seed and not product:
            messagebox.showwarning("입력 필요", "상품을 선택하거나 시드 키워드를 입력하세요.")
            return
        if not seed and not self.ai_key:   # 상품제목 기반은 AI 앵커+판정 필수
            messagebox.showwarning("키 필요", "상품제목 기반 추천은 OpenAI(ChatGPT) API 키가 필요합니다. "
                                   "설정 탭에서 키를 입력하거나 시드 키워드를 직접 입력하세요.")
            return
        self.kw_tree.delete(*self.kw_tree.get_children())
        basis = "시드" if seed else "상품제목"
        label = seed if seed else product
        self.log(f"[키워드] {basis} '{label[:30]}' 기반 추천"
                 f"{'' if seed else ' (AI 앵커+판정)'} — 다양한 후보 조사 → 쿠팡 경쟁(수십초)")

        key = self.ai_key

        def task():
            api = NaverAdApi(self.naver_creds)
            with WingBrowser(profile_dir=_PROFILE, offscreen=True) as wb:
                if seed:
                    return recommend(seed, api, wb)
                return recommend_from_title(product, api, wb, ai_key=key)
        self.run_bg(task, on_done=self._fill_kw, btn=self.kw_run_btn)

    def _fill_kw(self, recs):
        for r in recs:
            self.kw_tree.insert("", "end", values=(
                r.keyword, r.volume, f"{r.clicks:.0f}", r.comp_idx, r.ad_depth,
                f"{r.rocket_ratio:.2f}", r.ad_count, f"{r.score:.2f}", r.note))
        self.log(f"[키워드] 추천 {len(recs)}개 표시. 3~5개 선택 후 저장하세요.")

    def save_keywords(self):
        sel = self.kw_tree.selection()
        if not (3 <= len(sel) <= 5):
            messagebox.showwarning("선택 개수", "3~5개를 선택하세요.")
            return
        product = self.kw_product_var.get()
        if not product:
            messagebox.showwarning("상품 필요", "상품을 먼저 선택하세요.")
            return
        business = self.product_business.get(product, "")
        keywords = [self.kw_tree.item(i, "values")[0] for i in sel]
        keyword_store.save(business, product, keywords)
        self.log(f"[저장] [{business}] {product} ← {keywords}")
        messagebox.showinfo("저장 완료", f"{len(keywords)}개 키워드를 저장했습니다.")

    # ── 순위 조회 ─────────────────────────────────────────────
    def do_rank(self):
        kw = self.rank_kw_var.get().strip()
        name = self.rank_name_var.get().strip()
        if not kw or not name:
            messagebox.showwarning("입력 필요", "키워드와 상품명 일부를 입력하세요.")
            return
        self.log(f"[순위] '{kw}' 에서 '{name}' 오가닉 순위 조회 중…")

        def task():
            with WingBrowser(profile_dir=_PROFILE, offscreen=True) as wb:
                warmup(wb)
                return organic_rank(wb, kw, make_matcher(name_substr=name))
        self.run_bg(task, on_done=lambda r: self.log(
            f"[순위] 결과: {('오가닉 ' + str(r) + '위') if r else (str(config.RANK_SCAN_MAX) + '위 밖 → ' + str(config.RANK_SCAN_MAX) + '위')}"),
            btn=self.rank_btn)


def main():
    set_workdir()                   # .exe 더블클릭 대비 — 상대경로(output·data)가 exe 폴더에서 해석되게 CWD 고정
    try:                            # Chrome 필수(실제 Chrome+CDP 정책) — 없으면 크래시 대신 안내 후 종료
        find_chrome()
    except FileNotFoundError:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(
            "Google Chrome 필요",
            "이 프로그램은 실제 Google Chrome 으로 동작합니다.\n\n"
            "이 PC 에 Chrome 이 설치돼 있지 않습니다. https://www.google.com/chrome 에서 "
            "Chrome 을 설치한 뒤 다시 실행하세요.")
        return
    reaped = reap_orphan_chrome()   # 이전 실행이 강제종료·크래시로 남긴 좀비 Chrome 정리(누적 원천 차단)
    if reaped:
        print(f"[시작] 잔여(좀비) Chrome {reaped}개 정리함")
    App().mainloop()


if __name__ == "__main__":
    main()
