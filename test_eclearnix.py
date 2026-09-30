import re
from playwright.sync_api import sync_playwright

VERIFY_URL = "https://www.eclearnix.com/certificate-validation"
CERTIFICATE_ID = "XXC5POW13EI19"


def find_and_fill_credential_input(page, certificate_id):
    selectors = [
        "input[type='text']",
        "input[type='search']",
        "input:not([type])"
    ]

    for selector in selectors:
        inputs = page.locator(selector)
        count = inputs.count()

        for index in range(count):
            input_field = inputs.nth(index)

            try:
                if input_field.is_visible() and input_field.is_enabled():
                    input_field.fill(certificate_id)
                    return True
            except Exception:
                continue

    return False


def find_and_click_verify_button(page):
    buttons = page.locator("button, input[type='submit']")

    for index in range(buttons.count()):
        button = buttons.nth(index)

        try:
            if not button.is_visible() or not button.is_enabled():
                continue

            button_text = (
                button.inner_text()
                or button.get_attribute("value")
                or ""
            ).strip()

            if "verify" in button_text.lower():
                button.click()
                return True

        except Exception:
            continue

    return False


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=False)

    page = browser.new_page(viewport={
        "width": 1440,
        "height": 1000
    })

    page.goto(
        VERIFY_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(3000)

    input_found = find_and_fill_credential_input(
        page,
        CERTIFICATE_ID
    )

    if not input_found:
        print("ERROR: Credential ID input field was not found.")
        page.screenshot(path="eclearnix_input_not_found.png")
        browser.close()
        raise SystemExit

    verify_button_found = find_and_click_verify_button(page)

    if not verify_button_found:
        print("ERROR: Verify button was not found.")
        page.screenshot(path="eclearnix_button_not_found.png")
        browser.close()
        raise SystemExit

    page.wait_for_timeout(5000)

    result_text = page.locator("body").inner_text()

    with open(
        "eclearnix_result.txt",
        "w",
        encoding="utf-8"
    ) as result_file:
        result_file.write(result_text)

    page.screenshot(
        path="eclearnix_result.png",
        full_page=True
    )

    print("\n----- ECLEARNIX RESULT TEXT -----\n")
    print(result_text)
    print("\n---------------------------------\n")
    print("Result screenshot saved: eclearnix_result.png")
    print("Result text saved: eclearnix_result.txt")

    browser.close()