from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import random
import re
import sys
import time

from accounts import LOGIN_ACCOUNTS, register_login_fail, register_login_success
from targets import TARGET_USERS
from websites import WEBSITES


FOLLOWERS_TOOL_PATH = "/tools/send-follower"
TARGET_DELAY_RANGE = (1.5, 2.5)
RETRY_DELAY_SECONDS = 2
MAX_TARGET_RETRIES = 3
MAX_RELOGIN_ATTEMPTS_PER_SITE = 2


options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-notifications")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)
wait = WebDriverWait(driver, 15)


def log(msg):
    print(msg)
    sys.stdout.flush()


def get_root(url):
    return "/".join(url.split("/")[:3])


def wait_for_page_ready(timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            lambda current_driver: current_driver.execute_script(
                "return document.readyState"
            ) == "complete"
        )
    except Exception:
        pass


def close_popups():
    selectors = [
        "//button[contains(text(),'x')]",
        "//button[contains(text(),'X')]",
        "//button[@class='close']",
        "//div[@class='modal-footer']//button",
        "//a[@class='close']",
    ]

    for xpath in selectors:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            for element in elements:
                if element.is_displayed():
                    driver.execute_script("arguments[0].click();", element)
                    time.sleep(0.2)
        except Exception:
            pass


def open_page(url):
    driver.get(url)
    wait_for_page_ready()
    close_popups()


def is_login_really_success():
    try:
        password_inputs = driver.find_elements(By.NAME, "password")
        for password_input in password_inputs:
            if password_input.is_displayed():
                return False
    except Exception:
        pass

    try:
        if "login" in (driver.current_url or "").lower():
            return False
    except Exception:
        pass

    indicators = [
        "//a[contains(@href, 'logout')]",
        "//span[contains(@id, 'Kredi')]",
        "//div[contains(@class, 'user')]",
    ]

    for xpath in indicators:
        try:
            if driver.find_elements(By.XPATH, xpath):
                return True
        except Exception:
            continue

    return False


def has_zero_credit():
    try:
        credit_el = driver.find_element(By.ID, "takipKrediCount")
        credit_text = credit_el.text.strip()

        if not credit_text:
            return True

        credit = int(re.sub(r"\D", "", credit_text))
        log(f"Current Credit: {credit}")
        return credit <= 0
    except Exception:
        log("Credit element not found. Assuming 0 to skip.")
        return True


def wait_for_login_result(timeout=8):
    end_time = time.time() + timeout

    while time.time() < end_time:
        if is_login_really_success():
            return True
        time.sleep(0.5)

    return is_login_really_success()


def _dispatch_input_events(element):
    try:
        driver.execute_script(
            """
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            """,
            element,
        )
    except Exception:
        pass


def _find_login_button():
    selectors = [
        (By.ID, "login_insta"),
        (By.XPATH, "//button[@type='submit']"),
        (By.XPATH, "//button[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]"),
    ]
    for by, selector in selectors:
        try:
            elements = driver.find_elements(by, selector)
            for element in elements:
                if element.is_displayed():
                    return element
        except Exception:
            continue
    return None


def _click_login_button(login_button, pass_input):
    try:
        login_button.click()
        log("Login click method: selenium.click()")
        return True
    except Exception:
        pass

    try:
        driver.execute_script(
            """
            const btn = arguments[0];
            btn.scrollIntoView({ block: 'center', inline: 'center' });
            btn.removeAttribute('disabled');
            btn.click();
            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            """,
            login_button,
        )
        log("Login click method: JavaScript click")
        return True
    except Exception:
        pass

    try:
        pass_input.send_keys(Keys.ENTER)
        log("Login click method: ENTER key submit")
        return True
    except Exception:
        return False


def login_with_account(account):
    close_popups()

    if is_login_really_success():
        return True

    try:
        user_input = wait.until(
            EC.visibility_of_element_located((By.NAME, "username"))
        )
        pass_input = wait.until(
            EC.visibility_of_element_located((By.NAME, "password"))
        )

        user_input.clear()
        user_input.send_keys(account["user"])
        _dispatch_input_events(user_input)
        pass_input.clear()
        pass_input.send_keys(account["pass"])
        _dispatch_input_events(pass_input)

        close_popups()
        login_button = _find_login_button()
        if not login_button:
            raise RuntimeError("Login button not found")

        if not _click_login_button(login_button, pass_input):
            raise RuntimeError("Could not click login button")

        if wait_for_login_result():
            log(f"LOGIN SUCCESS: {account['user']}")
            if "_id" in account:
                register_login_success(account["_id"])
            return True

        log(f"LOGIN FAILED: {account['user']}")
        if "_id" in account:
            register_login_fail(account["_id"])
        return False

    except Exception as error:
        log(f"Login Error: {error}")
        if "_id" in account:
            register_login_fail(account["_id"])
        return False


def send_followers_single_target(root, target):
    try:
        open_page(root + FOLLOWERS_TOOL_PATH)
    except Exception:
        return False

    if not is_login_really_success():
        log("Session expired. Login required again.")
        return "LOGIN_REQUIRED"

    if has_zero_credit():
        log("Credit is 0.")
        return "NO_CREDIT"

    try:
        username_box = wait.until(
            EC.element_to_be_clickable((By.NAME, "username"))
        )
        username_box.clear()
        username_box.send_keys(target)

        find_button = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(text(),'User') or contains(text(),'Bul') or contains(text(),'Find')]"
            ))
        )
        driver.execute_script("arguments[0].click();", find_button)

        start_button = wait.until(
            EC.element_to_be_clickable((By.ID, "formTakipSubmitButton"))
        )
        driver.execute_script("arguments[0].click();", start_button)
        time.sleep(1)

        log(f"Sent Request -> {target}")
        return True

    except Exception as error:
        log(f"Failed to send to {target}: {error}")
        return False


def process_site_until_no_credit(account, site, target_counter):
    root = get_root(site["login_url"])
    relogin_attempts = 0
    consecutive_failures = 0

    log("")
    log(f"Site: {site['name']}")
    open_page(site["login_url"])

    if not login_with_account(account):
        log(f"Skipping {site['name']} because login failed.")
        return target_counter

    while True:
        current_target = TARGET_USERS[target_counter % len(TARGET_USERS)]
        log(f"Target: {current_target}")

        result = send_followers_single_target(root, current_target)

        if result == "NO_CREDIT":
            log(f"{site['name']} credit finished. Moving to next site.")
            return target_counter

        if result == "LOGIN_REQUIRED":
            if relogin_attempts >= MAX_RELOGIN_ATTEMPTS_PER_SITE:
                log(f"{site['name']} session could not recover. Moving to next site.")
                return target_counter

            relogin_attempts += 1
            log(f"Re-login attempt {relogin_attempts} on {site['name']}...")
            open_page(site["login_url"])

            if not login_with_account(account):
                log(f"Re-login failed on {site['name']}. Moving to next site.")
                return target_counter

            continue

        if result is True:
            target_counter += 1
            consecutive_failures = 0
            relogin_attempts = 0

            delay = random.uniform(*TARGET_DELAY_RANGE)
            log(f"Waiting {delay:.1f}s...")
            time.sleep(delay)
            continue

        consecutive_failures += 1

        if consecutive_failures < MAX_TARGET_RETRIES:
            log(f"Retry same target: {current_target}")
            time.sleep(RETRY_DELAY_SECONDS)
            continue

        if relogin_attempts >= MAX_RELOGIN_ATTEMPTS_PER_SITE:
            log(f"{site['name']} is failing repeatedly. Moving to next site.")
            return target_counter

        relogin_attempts += 1
        consecutive_failures = 0

        log(f"Refreshing {site['name']} and trying again...")
        open_page(site["login_url"])

        if not login_with_account(account):
            log(f"Re-login failed on {site['name']}. Moving to next site.")
            return target_counter

        time.sleep(RETRY_DELAY_SECONDS)


if __name__ == "__main__":
    try:
        for account in LOGIN_ACCOUNTS:
            log("")
            log("==========================================")
            log(f"LOGGING IN ACCOUNT: {account['user']}")
            log("==========================================")

            target_counter = 0

            for site in WEBSITES:
                target_counter = process_site_until_no_credit(
                    account,
                    site,
                    target_counter,
                )

            log("")
            log(f"Finished all websites for {account['user']}")

    except KeyboardInterrupt:
        log("Script stopped by user.")
    finally:
        log("Exiting...")
        driver.quit()
