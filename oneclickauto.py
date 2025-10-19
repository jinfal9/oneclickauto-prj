import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =========================
# 사이트/선택자 설정
# =========================
TARGET_URL = "https://deadline-notify.netlify.app/"

# 보내주신 DOM과 1:1 매핑 (필수 4개 + 선택 1개)
TITLE_LOCATORS    = [(By.ID, "title")]
SOURCE_LOCATORS   = [(By.ID, "source")]
CATEGORY_LOCATORS = [(By.ID, "category")]
DUE_LOCATORS      = [(By.ID, "due"), (By.CSS_SELECTOR, "input[type='date']")]  # type=date
LINK_LOCATORS     = [(By.ID, "link")]
SUBMIT_LOCATORS   = [(By.ID, "btnAdd"), (By.XPATH, "//button[normalize-space()='추가']")]

DEFAULT_WAIT_SECONDS = 15

def build_chrome_options():
    opts = webdriver.ChromeOptions()
    # opts.add_argument("--headless=new")  # 확인이 필요 없으면 사용
    opts.add_argument("--start-maximized")
    return opts

def create_chrome_driver():
    """Selenium 4/3 겸용"""
    options = build_chrome_options()
    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                                options=options)
    except TypeError:  # Selenium 3.x
        return webdriver.Chrome(ChromeDriverManager().install(), options=options)

# ---------- 공통 유틸 ----------
def wait_visible_any(driver, locator_list, wait_sec=DEFAULT_WAIT_SECONDS):
    last_err = None
    for by, value in locator_list:
        try:
            el = WebDriverWait(driver, wait_sec).until(
                EC.visibility_of_element_located((by, value))
            )
            return el
        except Exception as e:
            last_err = e
    raise last_err or TimeoutError("요소를 찾지 못했습니다.")

def safe_send_text(driver, element, text):
    """send_keys 실패 대비: JS로 값 주입 + input/change 이벤트"""
    t = "" if text is None else str(text)
    try:
        element.clear()
    except Exception:
        pass
    try:
        element.send_keys(t)
        return
    except Exception:
        pass
    js = """
    const el = arguments[0];
    const val = arguments[1];
    el.value = val;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    """
    driver.execute_script(js, element, t)

def fill_date(driver, element, text):
    """
    type=date 필드에 날짜를 안전하게 주입.
    - 허용 입력 예: "2025-05-22", "2025/05/22", "20250522"
    - 내부적으로 (Y, M, D)를 뽑아 new Date(Y, M-1, D)로 valueAsDate 지정
    - React 등 프레임워크 반영 위해 input/change/blur 이벤트까지 디스패치
    """
    raw = (text or "").strip()

    # 1) 숫자만 남기기 (하이픈/슬래시 등 제거)
    digits = "".join(ch for ch in raw if ch.isdigit())

    # 2) 자리수 보정: YYYYMMDD 형태로 맞추기
    if len(digits) >= 8:
        y = int(digits[0:4])
        m = int(digits[4:6])
        d = int(digits[6:8])
    else:
        # 최소한 YYYY-MM-DD 형태에서 앞 10자만 처리
        try:
            y = int(raw[0:4]); m = int(raw[5:7]); d = int(raw[8:10])
        except Exception:
            # 마지막 안전장치: 그냥 텍스트로 시도
            safe_send_text(driver, element, raw[:10])
            return

    # 3) 브라우저 로캘/타임존 영향을 피하려고 (Y, M-1, D)로 Date 생성
    js = r"""
    const el = arguments[0];
    const y  = arguments[1];
    const m  = arguments[2];  // 1~12
    const d  = arguments[3];
    // valueAsDate는 로컬 타임존 기준 Date 객체를 기대함
    el.valueAsDate = new Date(y, m - 1, d);

    // 혹시 프레임워크가 문자열 value를 감시한다면 동기화
    const mm = String(m).padStart(2,'0');
    const dd = String(d).padStart(2,'0');
    el.value = `${y}-${mm}-${dd}`;

    // 상태 업데이트 이벤트
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur',   { bubbles: true }));
    """
    driver.execute_script(js, element, y, m, d)

# =========================
# GUI 앱
# =========================
class AutoInputApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("데드라인 5필드 자동 입력 (Chrome + Selenium)")
        self.geometry("680x520")
        self.resizable(False, False)

        frm = ttk.LabelFrame(self, text="입력 정보 (제목/출처/카테고리/마감일/링크)")
        frm.pack(fill="x", padx=12, pady=10)

        # 1) 제목
        ttk.Label(frm, text="제목:").grid(row=0, column=0, sticky="e", padx=8, pady=6)
        self.ent_title = ttk.Entry(frm)
        self.ent_title.grid(row=0, column=1, sticky="we", padx=8, pady=6)

        # 2) 출처
        ttk.Label(frm, text="출처:").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        self.ent_source = ttk.Entry(frm)
        self.ent_source.grid(row=1, column=1, sticky="we", padx=8, pady=6)

        # 3) 카테고리
        ttk.Label(frm, text="카테고리:").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.ent_category = ttk.Entry(frm)
        self.ent_category.grid(row=2, column=1, sticky="we", padx=8, pady=6)

        # 4) 마감일 (input[type=date])
        ttk.Label(frm, text="마감일 (YYYY-MM-DD):").grid(row=3, column=0, sticky="e", padx=8, pady=6)
        self.ent_due = ttk.Entry(frm)
        self.ent_due.grid(row=3, column=1, sticky="we", padx=8, pady=6)

        # 5) 링크 (선택)
        ttk.Label(frm, text="링크(선택):").grid(row=4, column=0, sticky="e", padx=8, pady=6)
        self.ent_link = ttk.Entry(frm)
        self.ent_link.grid(row=4, column=1, sticky="we", padx=8, pady=6)

        frm.grid_columnconfigure(1, weight=1)

        # 옵션
        opt = ttk.LabelFrame(self, text="옵션")
        opt.pack(fill="x", padx=12, pady=(0,10))
        self.keep_open_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="완료 후 브라우저 유지", variable=self.keep_open_var).pack(anchor="w", padx=8, pady=6)

        # 버튼
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(0,10))
        self.btn_start = ttk.Button(btns, text="시작", command=self.on_start)
        self.btn_start.pack(side="left", padx=(0,6))
        self.btn_stop = ttk.Button(btns, text="중지(창 닫기)", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left")

        # 로그
        logfrm = ttk.LabelFrame(self, text="진행 상태")
        logfrm.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.txt_log = tk.Text(logfrm, height=12, wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt_log.configure(state="disabled")

        self.driver = None
        self.worker = None
        self.running = False

    def log(self, msg: str):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"{msg}\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
        self.update_idletasks()

    def set_running(self, running: bool):
        self.running = running
        self.btn_start.configure(state=("disabled" if running else "normal"))
        self.btn_stop.configure(state=("normal" if (running or self.driver) else "disabled"))

    def on_start(self):
        if self.running:
            self.log("이미 실행 중입니다.")
            return

        title    = self.ent_title.get().strip()
        source   = self.ent_source.get().strip()
        category = self.ent_category.get().strip()
        due      = self.ent_due.get().strip()
        link     = self.ent_link.get().strip()

        # 필수값 검증 (링크는 선택)
        if not (title and source and category and due):
            messagebox.showwarning("입력 확인", "제목/출처/카테고리/마감일을 모두 입력하세요. (링크는 선택)")
            return

        self.set_running(True)
        self.log("크롬을 준비합니다…")
        self.worker = threading.Thread(
            target=self.run_flow,
            args=(title, source, category, due, link),
            daemon=True
        )
        self.worker.start()

    def on_stop(self):
        self.log("브라우저 종료를 시도합니다…")
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.log("크롬 종료 완료.")
        except Exception:
            pass
        self.set_running(False)

    # ---------- Selenium 수행 ----------
    def run_flow(self, title, source, category, due, link):
        try:
            self.driver = create_chrome_driver()
            self.log(f"페이지 이동: {TARGET_URL}")
            self.driver.get(TARGET_URL)

            # 제목
            self.log("제목(#title) 입력 중…")
            el = wait_visible_any(self.driver, TITLE_LOCATORS)
            safe_send_text(self.driver, el, title)

            # 출처
            self.log("출처(#source) 입력 중…")
            el = wait_visible_any(self.driver, SOURCE_LOCATORS)
            safe_send_text(self.driver, el, source)

            # 카테고리
            self.log("카테고리(#category) 입력 중…")
            el = wait_visible_any(self.driver, CATEGORY_LOCATORS)
            safe_send_text(self.driver, el, category)

            # 마감일(type=date)
            self.log("마감일(#due) 입력 중…")
            el = wait_visible_any(self.driver, DUE_LOCATORS)
            fill_date(self.driver, el, due)

            # 링크(선택)
            if link:
                self.log("링크(#link) 입력 중…")
                el = wait_visible_any(self.driver, LINK_LOCATORS)
                safe_send_text(self.driver, el, link)
            else:
                self.log("링크는 비워둠(선택).")

            # [추가] 버튼
            self.log("추가 버튼 클릭 중…")
            btn = wait_visible_any(self.driver, SUBMIT_LOCATORS)
            try:
                btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", btn)

            time.sleep(1.2)
            self.log("모든 입력을 마쳤습니다.")

        except Exception as e:
            self.log("⚠ 오류 발생:\n" + "".join(traceback.format_exception_only(type(e), e)).strip())
        finally:
            if self.keep_open_var.get():
                self.log("설정에 따라 브라우저를 유지합니다. 필요 시 [중지(창 닫기)] 버튼을 누르세요.")
            else:
                try:
                    if self.driver:
                        self.log("설정에 따라 브라우저를 닫습니다…")
                        self.driver.quit()
                        self.driver = None
                        self.log("크롬 종료 완료.")
                except Exception:
                    pass
            self.set_running(False)

# =========================
# 진입점
# =========================
if __name__ == "__main__":
    app = AutoInputApp()
    app.mainloop()
