import re

import requests
from bs4 import BeautifulSoup


REQUEST_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


FIELD_KEYS = {
    "student_name",
    "exam_session",
    "roll_number",
    "register_number",
    "total_marks",
    "result",
}


def clean_value(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" :;-|\t\r\n")


def clean_qr_url(value):
    if not value:
        return ""

    value = str(value).strip()

    markdown_match = re.search(
        r"\]\((https?://[^)]+)\)",
        value,
        re.IGNORECASE,
    )

    if markdown_match:
        return markdown_match.group(1).strip()

    url_match = re.search(
        r"https?://[^\s)\]]+",
        value,
        re.IGNORECASE,
    )

    if url_match:
        return url_match.group(0).strip()

    return value


def normalize_spaces(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def normalize_label(label):
    label = normalize_spaces(label).lower()

    label = label.replace(":", "")
    label = label.replace("/", " ")
    label = label.replace(".", "")
    label = re.sub(r"\s+", " ", label).strip()

    replacements = {
        "name of the candidate": "student_name",
        "candidate name": "student_name",
        "student name": "student_name",
        "name": "student_name",
        "session": "exam_session",
        "exam session": "exam_session",
        "roll no": "roll_number",
        "roll number": "roll_number",
        "roll": "roll_number",
        "register no": "register_number",
        "register number": "register_number",
        "permanent register no": "register_number",
        "permanent register number": "register_number",
        "total marks": "total_marks",
        "marks obtained": "total_marks",
        "result": "result",
        "status": "result",
    }

    return replacements.get(label, label)


def add_detected_field(fields, label, value):
    key = normalize_label(label)
    value = clean_value(value)

    if key in FIELD_KEYS and value:
        fields[key] = value


def extract_table_fields(soup):
    fields = {}

    for row in soup.find_all("tr"):
        cells = row.find_all(
            ["th", "td"],
            recursive=False,
        )

        if len(cells) < 2:
            continue

        label = clean_value(
            cells[0].get_text(
                " ",
                strip=True,
            )
        )

        value = clean_value(
            cells[1].get_text(
                " ",
                strip=True,
            )
        )

        add_detected_field(
            fields,
            label,
            value,
        )

    return fields


def get_page_text(soup):
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
        ]
    ):
        tag.decompose()

    return normalize_spaces(
        soup.get_text(
            " ",
            strip=True,
        )
    )


def extract_tndge_fields(text):
    fields = {}

    text = normalize_spaces(text)

    # Example:
    # Name of the Candidate ... GUNASREE S MAY 2022
    name_match = re.search(
        r"Name of the Candidate\s+"
        r".{0,100}?"
        r"([A-Z][A-Z .'-]{2,70})\s+"
        r"(?:MAY|JUNE|APRIL|MARCH|JANUARY|"
        r"FEBRUARY|SEPTEMBER|OCTOBER|NOVEMBER|"
        r"DECEMBER)\s+\d{4}",
        text,
        re.IGNORECASE,
    )

    if name_match:
        candidate_name = clean_value(
            name_match.group(1)
        )

        candidate_name = re.sub(
            r"^(?:NAME OF THE CANDIDATE)\s*",
            "",
            candidate_name,
            flags=re.IGNORECASE,
        )

        fields["student_name"] = candidate_name

    # Example:
    # MAY 2022
    session_match = re.search(
        r"\b"
        r"(MAY|JUNE|APRIL|MARCH|JANUARY|"
        r"FEBRUARY|SEPTEMBER|OCTOBER|NOVEMBER|"
        r"DECEMBER)"
        r"\s+(\d{4})"
        r"\b",
        text,
        re.IGNORECASE,
    )

    if session_match:
        fields["exam_session"] = (
            f"{session_match.group(1).title()} "
            f"{session_match.group(2)}"
        )

    # Example:
    # ROLL NO. 1954276
    roll_match = re.search(
        r"\bROLL\s*NO\.?\s*"
        r"([0-9]{4,20})\b",
        text,
        re.IGNORECASE,
    )

    if roll_match:
        fields["roll_number"] = (
            roll_match.group(1)
        )

    # Example:
    # R2911427
    register_match = re.search(
        r"\b([A-Z]\d{7})\b",
        text,
        re.IGNORECASE,
    )

    if register_match:
        fields["register_number"] = (
            register_match.group(1).upper()
        )

    # Example:
    # TOTAL MARKS ... 448 ... PASS
    total_marks_match = re.search(
        r"TOTAL\s+MARKS"
        r".{0,150}?"
        r"\b([0-9]{2,4})\b"
        r".{0,35}?"
        r"\b(?:PASS|FAIL)\b",
        text,
        re.IGNORECASE,
    )

    if total_marks_match:
        fields["total_marks"] = (
            total_marks_match.group(1)
        )

    # Example:
    # TOTAL MARKS ... 448 ... PASS
    result_match = re.search(
        r"TOTAL\s+MARKS"
        r".{0,150}?"
        r"\b(?:[0-9]{2,4})\b"
        r".{0,35}?"
        r"\b(PASS|FAIL)\b",
        text,
        re.IGNORECASE,
    )

    if result_match:
        fields["result"] = (
            result_match.group(1).title()
        )

    return fields


def extract_generic_text_fields(text):
    fields = {}

    patterns = {
        "student_name": [
            r"(?:Student Name|Candidate Name|"
            r"Name of the Candidate|Name)"
            r"\s*[:\-]\s*"
            r"([A-Za-z][A-Za-z .'-]{2,80})",
        ],
        "exam_session": [
            r"(?:Exam Session|Session)"
            r"\s*[:\-]\s*"
            r"([A-Za-z0-9 /-]{3,40})",
        ],
        "roll_number": [
            r"(?:Roll Number|Roll No|Roll)"
            r"\s*[:\-]\s*"
            r"([A-Za-z0-9/-]{3,30})",
        ],
        "register_number": [
            r"(?:Register Number|Register No|"
            r"Permanent Register No)"
            r"\s*[:\-]\s*"
            r"([A-Za-z0-9/-]{3,40})",
        ],
        "total_marks": [
            r"(?:Total Marks|Marks Obtained)"
            r"\s*[:\-]\s*"
            r"([0-9]{1,4})",
        ],
        "result": [
            r"(?:Result|Status)"
            r"\s*[:\-]\s*"
            r"(Pass|Fail|P|F)",
        ],
    }

    for key, key_patterns in patterns.items():
        for pattern in key_patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if match:
                value = clean_value(
                    match.group(1)
                )

                if key == "result":
                    if value.upper() == "P":
                        value = "Pass"

                    elif value.upper() == "F":
                        value = "Fail"

                fields[key] = value
                break

    return fields


def extract_script_json_fields(soup):
    fields = {}

    for script in soup.find_all("script"):
        script_text = script.get_text(
            " ",
            strip=True,
        )

        if not script_text:
            continue

        patterns = {
            "student_name": (
                r"(?:studentName|student_name|candidateName)"
                r"\s*['\"]?\s*[:=]\s*['\"]"
                r"([^'\"]{2,80})"
            ),
            "exam_session": (
                r"(?:examSession|exam_session|session)"
                r"\s*['\"]?\s*[:=]\s*['\"]"
                r"([^'\"]{2,40})"
            ),
            "roll_number": (
                r"(?:rollNumber|roll_no|roll)"
                r"\s*['\"]?\s*[:=]\s*['\"]"
                r"([A-Za-z0-9/-]+)"
            ),
            "register_number": (
                r"(?:registerNumber|register_no|register)"
                r"\s*['\"]?\s*[:=]\s*['\"]"
                r"([A-Za-z0-9/-]+)"
            ),
            "total_marks": (
                r"(?:totalMarks|total_marks|total)"
                r"\s*['\"]?\s*[:=]\s*['\"]"
                r"([0-9]{1,4})"
            ),
            "result": (
                r"(?:result|status)"
                r"\s*['\"]?\s*[:=]\s*['\"]"
                r"(Pass|Fail|P|F)"
            ),
        }

        for key, pattern in patterns.items():
            match = re.search(
                pattern,
                script_text,
                re.IGNORECASE,
            )

            if not match:
                continue

            value = clean_value(
                match.group(1)
            )

            if key == "result":
                if value.upper() == "P":
                    value = "Pass"

                elif value.upper() == "F":
                    value = "Fail"

            if key not in fields:
                fields[key] = value

    return fields


def extract_official_fields(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    fields = {}

    table_fields = extract_table_fields(soup)

    for key, value in table_fields.items():
        fields[key] = value

    visible_text = get_page_text(soup)

    tndge_fields = extract_tndge_fields(
        visible_text
    )

    for key, value in tndge_fields.items():
        if not fields.get(key):
            fields[key] = value

    generic_fields = extract_generic_text_fields(
        visible_text
    )

    for key, value in generic_fields.items():
        if not fields.get(key):
            fields[key] = value

    script_fields = extract_script_json_fields(
        soup
    )

    for key, value in script_fields.items():
        if not fields.get(key):
            fields[key] = value

    return fields


def verify_qr_content(verification_url):
    verification_url = clean_qr_url(
        verification_url
    )

    result = {
        "source_url": verification_url,
        "detected_fields": {},
        "page_title": "",
        "raw_official_text": "",
        "error": None,
    }

    if not verification_url:
        result["error"] = (
            "QR content is empty."
        )
        return result

    if not (
        verification_url.startswith("http://")
        or verification_url.startswith("https://")
    ):
        result["error"] = (
            "QR content is not a valid web URL."
        )
        return result

    try:
        response = requests.get(
            verification_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": (
                    "en-US,en;q=0.9"
                ),
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        html = response.text

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        page_title = ""

        if soup.title:
            page_title = clean_value(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )

        raw_official_text = normalize_spaces(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        detected_fields = extract_official_fields(
            html
        )

        result.update(
            {
                "source_url": response.url,
                "detected_fields": detected_fields,
                "page_title": page_title,
                "raw_official_text": raw_official_text,
                "error": None,
            }
        )

        return result

    except requests.RequestException as error:
        result["error"] = (
            "Official website request failed: "
            f"{error}"
        )
        return result

    except Exception as error:
        result["error"] = (
            "Official details extraction failed: "
            f"{error}"
        )
        return result