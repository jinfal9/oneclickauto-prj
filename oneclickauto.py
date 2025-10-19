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
# 🔧 [필수 설정] 여러분 사이트에 맞게 바꾸세요
# =========================
TARGET_URL = "https://deadline-notify.netlify.app/"   # 자동 입력할 대상 URL

# 아래 3개는 '어떻게 요소를 찾을지'를 정합니다.
# 방법: By.ID / By.NAME / By.CSS_SELECTOR / By.XPATH 중 택1
NUMBER_FIELD = (By.NAME, "phone")          # 예: (By.ID, "userNumber"), (By.NAME, "phone"), (By.CSS_SELECTOR, "input[name='phone']")
NAME_FIELD   = (By.NAME, "username")       # 예: (By.ID, "userName"), (By.XPATH, "//input[@placeholder='이름']")
SUBMIT_BTN   = (By.CSS_SELECTOR, "button[type='submit']")  # 없으면 None 로 두세요 (자동 클릭 스킵)

# 대기(타임아웃) 기본값
DEFAULT_WAIT_SECONDS = 15

# 크롬 옵션 (원하면 프로필 사용/헤드리스 등 추가 가능)
def build_chrome_options():
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")   # 창 숨김 모드 (원하면 주석 해제)
    options.add_argument("--start-maximized")
    # options.add_argument("--user-data-dir=C:/ChromeProfile")  # 로그인 유지가 필요할 경우 프로필 경로 사용
    return options
# =========================


class AutoInputApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("웹 자동 입력 매크로 (Chrome + Selenium)")
        self.geometry("520x360")
        self.resizable(False, False)

        # 입력 폼
        frm = ttk.LabelFrame(self, text="입력 정보")
        frm.pack(fill="x", padx=12, pady=10)

        ttk.Label(frm, text="번호:").grid(row=0, column=0, sticky="e", padx=8, pady=8)
        self.entry_number = ttk.Entry(frm)
        self.entry_number.grid(row=0, column=1, sticky="we", padx=8, pady=8)

        ttk.Label(frm, text="이름:").grid(row=1, column=0, sticky="e", padx=8, pady=8)
        self.entry_name = ttk.Entry(frm)
        self.entry_name.grid(row=1, column=1, sticky="we", padx=8, pady=8)

        frm.grid_columnconfigure(1, weight=1)

        # 실행/중지 버튼
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(0,10))

        self.btn_start = ttk.Button(btns, text="시작", command=self.on_start)
        self.btn_start.pack(side="left", padx=(0,6))

        self.btn_stop = ttk.Button(btns, text="중지(창 닫기)", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left")

        # 상태 로그
        logfrm = ttk.LabelFrame(self, text="진행 상태")
        logfrm.pack(fill="both", expand=True, padx=12, pady=(0,12))

        self.txt_log = tk.Text(logfrm, height=12, wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt_log.configure(state="disabled")

        self.driver = None
        self.worker = None
        self.stop_flag = False

    def log(self, msg: str):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"{msg}\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
        self.update_idletasks()

    def set_running(self, running: bool):
        self.btn_start.configure(state=("disabled" if running else "normal"))
        self.btn_stop.configure(state=("normal" if running else "disabled"))

    def on_start(self):
        number = self.entry_number.get().strip()
        name = self.entry_name.get().strip()

        if not number or not name:
            messagebox.showwarning("입력 확인", "번호와 이름을 모두 입력하세요.")
            return

        self.stop_flag = False
        self.set_running(True)
        self.log("작업 시작… 크롬을 준비합니다.")

        # 백그라운드 스레드에서 셀레니움 작업 수행 (GUI 멈춤 방지)
        self.worker = threading.Thread(target=self.run_selenium_flow, args=(number, name), daemon=True)
        self.worker.start()

    def on_stop(self):
        self.stop_flag = True
        self.log("중지 신호 전송됨. 브라우저를 닫습니다…")
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.log("크롬 종료 완료.")
        except Exception:
            pass
        self.set_running(False)

    def wait_and_find(self, locator, wait_sec=DEFAULT_WAIT_SECONDS):
        by, value = locator
        wait = WebDriverWait(self.driver, wait_sec)
        return wait.until(EC.presence_of_element_located((by, value)))

    def wait_and_clickable(self, locator, wait_sec=DEFAULT_WAIT_SECONDS):
        by, value = locator
        wait = WebDriverWait(self.driver, wait_sec)
        return wait.until(EC.element_to_be_clickable((by, value)))

    def safe_send_keys(self, element, text):
        try:
            element.clear()
        except Exception:
            pass
        try:
            element.send_keys(text)
        except Exception:
            # 최후의 수단: JS로 값 주입
            self.driver.execute_script("arguments[0].value = arguments[1];", element, text)

    def run_selenium_flow(self, number: str, name: str):
        try:
            # 1) 드라이버 실행
            options = build_chrome_options()
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                                           options=options)

            self.log(f"페이지 이동: {TARGET_URL}")
            self.driver.get(TARGET_URL)

            # 2) 요소 대기 및 입력
            self.log("번호 입력칸 찾는 중…")
            number_el = self.wait_and_find(NUMBER_FIELD)
            self.safe_send_keys(number_el, number)
            self.log(f"번호 입력 완료: {number}")

            self.log("이름 입력칸 찾는 중…")
            name_el = self.wait_and_find(NAME_FIELD)
            self.safe_send_keys(name_el, name)
            self.log(f"이름 입력 완료: {name}")

            # 3) 제출(선택)
            if SUBMIT_BTN is not None:
                self.log("제출 버튼 찾는 중…")
                try:
                    submit_el = self.wait_and_clickable(SUBMIT_BTN)
                except Exception:
                    # 클릭 불가 시 presence로라도 찾아서 JS 클릭 시도
                    submit_el = self.wait_and_find(SUBMIT_BTN)
                try:
                    submit_el.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", submit_el)
                self.log("제출 버튼 클릭 완료.")
            else:
                self.log("제출 버튼 설정이 None이라 클릭을 건너뜁니다.")

            # 4) 결과 확인을 위해 잠시 대기
            time.sleep(3)
            self.log("완료되었습니다. 브라우저를 직접 확인하세요.")

        except Exception as e:
            self.log("⚠ 오류 발생:\n" + "".join(traceback.format_exception_only(type(e), e)).strip())
            self.log("자세한 스택 트레이스는 콘솔에서 확인하거나 코드 상단 설정을 점검하세요.")
        finally:
            # 자동 종료를 원치 않으면 주석 처리
            try:
                if self.driver:
                    self.log("브라우저를 닫습니다…")
                    self.driver.quit()
                    self.driver = None
                    self.log("크롬 종료 완료.")
            except Exception:
                pass
            self.set_running(False)


if __name__ == "__main__":
    app = AutoInputApp()
    app.mainloop()
