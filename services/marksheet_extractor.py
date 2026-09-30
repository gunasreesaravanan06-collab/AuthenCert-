import re


def clean_value(value):
    if not value:
        return None

    value = re.sub(r"\s+", " ", value).strip()

    return value if value else None


def normalize_name(name):
    if not name:
        return None

    name = clean_value(name)

    if not name:
        return None

    # OCR often reads S as 5 at the end of initials.
    name = re.sub(r"\s+5$", " S", name)
    name = re.sub(r"\s+0$", " O", name)

    return name.title()


def clean_ocr_text(raw_text):
    text = raw_text.upper()

    # Remove invisible Unicode characters that may appear in Tamil OCR.
    text = text.replace("\u200b", "")
    text = text.replace("\u200c", "")
    text = text.replace("\u200d", "")
    text = text.replace("\ufeff", "")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)

    return text


def valid_mark(value):
    try:
        mark = int(value)
        return 0 <= mark <= 100
    except (TypeError, ValueError):
        return False


def extract_tamil_mark(text):
    tamil_match = re.search(
        r"தமிழ்[^\n]{0,80}?0?(\d{2,3})",
        text,
        re.IGNORECASE
    )

    if tamil_match and valid_mark(tamil_match.group(1)):
        return str(int(tamil_match.group(1)))

    tamil_english_match = re.search(
        r"\b0?(\d{2,3})\b[^\n]{0,100}?"
        r"\n[^\n]{0,100}\bTAMIL\b",
        text,
        re.IGNORECASE
    )

    if tamil_english_match and valid_mark(tamil_english_match.group(1)):
        return str(int(tamil_english_match.group(1)))

    return None


def extract_english_mark(text):
    tamil_english_match = re.search(
        r"ஆங்கிலம்[^\n]{0,80}?0?(\d{2,3})",
        text,
        re.IGNORECASE
    )

    if tamil_english_match and valid_mark(tamil_english_match.group(1)):
        return str(int(tamil_english_match.group(1)))

    english_label_match = re.search(
        r"\b0?(\d{2,3})\b[^\n]{0,100}?"
        r"\n[^\n]{0,100}\bENGLISH\b",
        text,
        re.IGNORECASE
    )

    if english_label_match and valid_mark(english_label_match.group(1)):
        return str(int(english_label_match.group(1)))

    return None


def extract_mathematics_mark(text):
    math_match = re.search(
        r"\bMATHEMATICS\b[^\n]{0,80}?0?(\d{2,3})",
        text,
        re.IGNORECASE
    )

    if math_match and valid_mark(math_match.group(1)):
        return str(int(math_match.group(1)))

    tamil_math_match = re.search(
        r"கணிதம்[^\n]{0,80}?0?(\d{2,3})",
        text,
        re.IGNORECASE
    )

    if tamil_math_match and valid_mark(tamil_math_match.group(1)):
        return str(int(tamil_math_match.group(1)))

    return None


def extract_science_mark(text):
    science_match = re.search(
        r"(?<!SOCIAL\s)\bSCIENCE\b([^\n]{0,150})",
        text,
        re.IGNORECASE
    )

    if not science_match:
        return None

    science_line = science_match.group(0)

    marks = re.findall(
        r"(?<!\d)0?(\d{2,3})(?!\d)",
        science_line
    )

    valid_marks = [
        int(mark)
        for mark in marks
        if valid_mark(mark)
    ]

    # Example:
    # SCIENCE 069 025 094
    # Final subject mark is last value: 94.
    if valid_marks:
        return str(valid_marks[-1])

    return None


def extract_social_science_mark(text):
    social_match = re.search(
        r"\bSOCIAL\s+SCIENCE\b[^\n]{0,80}?0?(\d{2,3})",
        text,
        re.IGNORECASE
    )

    if social_match and valid_mark(social_match.group(1)):
        return str(int(social_match.group(1)))

    return None


def extract_subject_marks(text):
    return {
        "Tamil": extract_tamil_mark(text),
        "English": extract_english_mark(text),
        "Mathematics": extract_mathematics_mark(text),
        "Science": extract_science_mark(text),
        "Social Science": extract_social_science_mark(text)
    }


def extract_student_name(text):
    name_match = re.search(
        r"NAME\s+OF\s+THE\s+CANDIDATE"
        r".{0,700}?"
        r"\b([A-Z]{3,}(?:\s+[A-Z0-9]{1,})?)\s+"
        r"(?:MAY|JUNE|MARCH|APRIL|NOVEMBER|DECEMBER)"
        r"\s+\d{4}\b",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if name_match:
        return normalize_name(name_match.group(1))

    return None


def extract_exam_session(text):
    session_match = re.search(
        r"\b(MAY|JUNE|MARCH|APRIL|NOVEMBER|DECEMBER)"
        r"\s+(\d{4})\b",
        text,
        re.IGNORECASE
    )

    if session_match:
        return (
            session_match.group(1).title()
            + " "
            + session_match.group(2)
        )

    return None


def extract_date_of_birth(text):
    dob_match = re.search(
        r"(?:DATE\s+OF\s+BIRTH|BIRTH)"
        r".{0,180}?"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if dob_match:
        return dob_match.group(1)

    return None


def extract_roll_number(text):
    roll_match = re.search(
        r"(?:ROLL\s*NO|தேர்வெண்|BIRTH)"
        r".{0,180}?"
        r"\b(\d{6,8})\b"
        r"\s+(?:ENGLISH|TAMIL)",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if roll_match:
        return roll_match.group(1)

    candidates = re.findall(r"\b\d{6,8}\b", text)

    ignored_numbers = {
        "600006",
        "2007",
        "2022"
    }

    for number in candidates:
        if number not in ignored_numbers:
            return number

    return None


def extract_register_number(text):
    register_match = re.search(
        r"PERMANENT\s+REGISTER\s+NO\.?"
        r".{0,200}?"
        r"\b([A-Z]\d{5,15})\b",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if register_match:
        return register_match.group(1).upper()

    general_register_match = re.search(
        r"\b([A-Z]\d{6,12})\b",
        text
    )

    if general_register_match:
        return general_register_match.group(1).upper()

    return None


def extract_school_name(text):
    school_match = re.search(
        r"NAME\s+OF\s+THE\s+SCHOOL"
        r".{0,400}?"
        r"(SUBIKSHA\s+ENGLISH\s+HIGH\s+SCHOOL"
        r"[A-Z0-9 ,.'()/\-]{0,120})",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if school_match:
        return clean_value(school_match.group(1)).title()

    for line in text.splitlines():
        if "HIGH SCHOOL" in line.upper():
            return clean_value(line).title()

    return None


def extract_result(text):
    result_match = re.search(
        r"\b(PASS|FAIL)\b",
        text,
        re.IGNORECASE
    )

    if result_match:
        return result_match.group(1).title()

    return None


def extract_marksheet_details(raw_text):
    text = clean_ocr_text(raw_text)

    subject_marks = extract_subject_marks(text)

    valid_marks = []

    for mark in subject_marks.values():
        if mark and valid_mark(mark):
            valid_marks.append(int(mark))

    calculated_total = None

    if len(valid_marks) == 5:
        calculated_total = sum(valid_marks)
    ocr_total_match = re.search(
        r"TOTAL\s+MARKS\s*[:\-]?\s*(\d{2,3})",
        text,
        re.IGNORECASE
    )

    ocr_total_marks = (
        ocr_total_match.group(1)
        if ocr_total_match else None
    )

    board_name = None

    if "STATE BOARD OF SCHOOL EXAMINATIONS" in text:
        board_name = "State Board of School Examinations, Tamil Nadu"

    return {
        "student_name": extract_student_name(text),
        "exam_session": extract_exam_session(text),
        "date_of_birth": extract_date_of_birth(text),
        "roll_number": extract_roll_number(text),
        "register_number": extract_register_number(text),
        "total_marks": (
            str(calculated_total)
            if calculated_total else ocr_total_marks
        ),
        "ocr_total_marks": ocr_total_marks,
        "calculated_total_marks": (
            str(calculated_total)
            if calculated_total else None
        ),
        "result": extract_result(text),
        "school_name": extract_school_name(text),
        "board_name": board_name,
        "subject_marks": subject_marks
    }