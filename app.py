import io
import os
import re
import sqlite3
import uuid
from datetime import datetime

import cv2
import numpy as np
import pymupdf as fitz
import pytesseract
import zxingcpp

from PIL import Image, ImageEnhance
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

from services.document_detector import detect_document_type
from services.marksheet_extractor import extract_marksheet_details
from services.verification_service import verify_qr_content


pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


try:
    available_languages = pytesseract.get_languages(
        config=""
    )
except Exception:
    available_languages = ["eng"]


OCR_LANGUAGE = (
    "eng+tam"
    if "tam" in available_languages
    else "eng"
)


app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "authencert.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

ALLOWED_EXTENSIONS = {
    "pdf",
    "jpg",
    "jpeg",
    "png",
}

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PDF_PAGES_TO_PROCESS = 5

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_db_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            file_extension TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            processing_status TEXT NOT NULL,
            final_status TEXT,
            confidence_score REAL,
            uploaded_at TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS certificate_ocr_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verification_request_id INTEGER NOT NULL,
            raw_ocr_text TEXT,
            extracted_name TEXT,
            extracted_certificate_id TEXT,
            extracted_issue_date TEXT,
            extracted_marks TEXT,
            extracted_course TEXT,
            extracted_issuer TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (verification_request_id)
                REFERENCES verification_requests(id)
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS qr_scan_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verification_request_id INTEGER NOT NULL,
            qr_detected INTEGER NOT NULL,
            qr_content TEXT,
            qr_type TEXT,
            scanned_at TEXT NOT NULL,
            FOREIGN KEY (verification_request_id)
                REFERENCES verification_requests(id)
        )
        """
    )

    connection.commit()
    connection.close()


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def preprocess_image(image):
    image = image.convert("L")

    image = image.resize(
        (
            image.width * 2,
            image.height * 2,
        ),
        Image.Resampling.LANCZOS,
    )

    return ImageEnhance.Contrast(image).enhance(2.5)


def extract_text_from_image(image_path):
    image = Image.open(image_path)
    processed_image = preprocess_image(image)

    return pytesseract.image_to_string(
        processed_image,
        lang=OCR_LANGUAGE,
        config="--oem 3 --psm 6",
    )


def extract_text_from_pdf(pdf_path):
    document = fitz.open(pdf_path)
    extracted_pages = []

    try:
        page_count = min(
            len(document),
            MAX_PDF_PAGES_TO_PROCESS,
        )

        for page_number in range(page_count):
            page = document[page_number]
            text_layer = page.get_text().strip()

            if text_layer:
                extracted_pages.append(text_layer)
                continue

            pixmap = page.get_pixmap(dpi=300)
            image_bytes = pixmap.tobytes("png")
            image = Image.open(
                io.BytesIO(image_bytes)
            )

            processed_image = preprocess_image(image)

            page_text = pytesseract.image_to_string(
                processed_image,
                lang=OCR_LANGUAGE,
                config="--oem 3 --psm 6",
            )

            extracted_pages.append(page_text)

    finally:
        document.close()

    return "\n\n".join(extracted_pages)


def extract_certificate_details(raw_text):
    cleaned_text = re.sub(
        r"[ \t]+",
        " ",
        raw_text,
    )

    cleaned_text = re.sub(
        r"\n{2,}",
        "\n",
        cleaned_text,
    ).strip()

    lines = [
        line.strip()
        for line in cleaned_text.splitlines()
        if line.strip()
    ]

    certificate_id_match = re.search(
        r"(?:Certificate\s*(?:ID|No|Number)?|"
        r"Cert(?:ificate)?\s*No)"
        r"\s*[:#\-]?\s*([A-Z0-9\-\/]+)",
        cleaned_text,
        re.IGNORECASE,
    )

    date_match = re.search(
        r"(?:Issue(?:d)?\s*Date|Date\s*of\s*Issue|Date)"
        r"\s*[:\-]?\s*"
        r"([0-9]{1,2}[-\/][0-9]{1,2}[-\/][0-9]{2,4})",
        cleaned_text,
        re.IGNORECASE,
    )

    marks_match = re.search(
        r"(?:Marks|Score|Percentage|CGPA|Grade)"
        r"\s*[:\-]?\s*([A-Z0-9.\s%]+)",
        cleaned_text,
        re.IGNORECASE,
    )

    name_match = re.search(
        r"(?:Name|Awarded\s*to|This\s*is\s*to\s*certify\s*that)"
        r"\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{2,60})",
        cleaned_text,
        re.IGNORECASE,
    )

    course_match = re.search(
        r"(?:Course|Program|Programme)"
        r"\s*[:\-]?\s*([A-Za-z0-9&,.()' -]{3,100})",
        cleaned_text,
        re.IGNORECASE,
    )

    issuer_match = re.search(
        r"(?:Issued\s*By|Issuer|Institute|Organization|Organisation)"
        r"\s*[:\-]?\s*([A-Za-z0-9&,.()' -]{3,100})",
        cleaned_text,
        re.IGNORECASE,
    )

    certificate_id = (
        certificate_id_match.group(1).strip().upper()
        if certificate_id_match
        else None
    )

    name = (
        name_match.group(1).strip()
        if name_match
        else None
    )

    qr_url_from_ocr = None

    for line in lines:
        url_match = re.search(
            r"https?://[^\s]+",
            line,
            re.IGNORECASE,
        )

        if url_match:
            qr_url_from_ocr = (
                url_match.group(0).strip()
            )
            break

    if not certificate_id:
        for line in lines:
            possible_id = re.fullmatch(
                r"(?=.*[A-Z])(?=.*[0-9])[A-Z0-9]{8,}",
                line.upper(),
            )

            if possible_id:
                certificate_id = line.upper()
                break

    if not name:
        for line in lines:
            possible_name = re.fullmatch(
                r"[A-Z][a-z]+(?:\s+[A-Z](?:[a-z]+)?){1,4}",
                line,
            )

            if possible_name:
                name = line
                break

    return {
        "name": name,
        "certificate_id": certificate_id,
        "issue_date": (
            date_match.group(1).strip()
            if date_match
            else None
        ),
        "marks": (
            marks_match.group(1).strip()
            if marks_match
            else None
        ),
        "course": (
            course_match.group(1).strip()
            if course_match
            else None
        ),
        "issuer": (
            issuer_match.group(1).strip()
            if issuer_match
            else None
        ),
        "qr_url_from_ocr": qr_url_from_ocr,
    }


def decode_qr_with_zxing(image):
    if image is None:
        return None

    try:
        results = zxingcpp.read_barcodes(image)

        for result in results:
            qr_content = result.text.strip()

            if qr_content:
                return qr_content

    except Exception:
        pass

    return None


def decode_qr_with_opencv(image):
    if image is None:
        return None

    detector = cv2.QRCodeDetector()

    try:
        qr_content, _, _ = (
            detector.detectAndDecode(image)
        )

        if qr_content:
            return qr_content.strip()

    except cv2.error:
        pass

    try:
        success, decoded_info, _, _ = (
            detector.detectAndDecodeMulti(image)
        )

        if success and decoded_info:
            for qr_content in decoded_info:
                if qr_content:
                    return qr_content.strip()

    except cv2.error:
        pass

    try:
        qr_content, _, _ = (
            detector.detectAndDecodeCurved(image)
        )

        if qr_content:
            return qr_content.strip()

    except cv2.error:
        pass

    return None


def get_qr_scan_versions(image):
    if image is None:
        return []

    versions = [image]

    if len(image.shape) == 3:
        grayscale = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )
    else:
        grayscale = image

    versions.append(grayscale)

    enlarged = cv2.resize(
        image,
        None,
        fx=2,
        fy=2,
        interpolation=cv2.INTER_CUBIC,
    )

    versions.append(enlarged)

    enlarged_grayscale = cv2.resize(
        grayscale,
        None,
        fx=4,
        fy=4,
        interpolation=cv2.INTER_CUBIC,
    )

    versions.append(enlarged_grayscale)

    blurred = cv2.GaussianBlur(
        enlarged_grayscale,
        (3, 3),
        0,
    )

    versions.append(blurred)

    threshold = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )[1]

    versions.append(threshold)

    versions.append(
        cv2.bitwise_not(threshold)
    )

    adaptive = cv2.adaptiveThreshold(
        enlarged_grayscale,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        51,
        8,
    )

    versions.append(adaptive)

    return versions


def get_qr_crops(image):
    if image is None:
        return []

    height, width = image.shape[:2]

    crop_height = int(height * 0.60)
    crop_width = int(width * 0.60)

    return [
        image[
            0:crop_height,
            0:crop_width,
        ],
        image[
            0:crop_height,
            max(0, width - crop_width):width,
        ],
        image[
            max(0, height - crop_height):height,
            0:crop_width,
        ],
        image[
            max(0, height - crop_height):height,
            max(0, width - crop_width):width,
        ],
        image[
            int(height * 0.15):int(height * 0.85),
            int(width * 0.15):int(width * 0.85),
        ],
    ]


def scan_qr_from_image_array(image):
    if image is None:
        return None

    qr_content = decode_qr_with_zxing(image)

    if qr_content:
        return qr_content

    qr_content = decode_qr_with_opencv(image)

    if qr_content:
        return qr_content

    for scan_image in get_qr_scan_versions(image):
        qr_content = decode_qr_with_zxing(
            scan_image
        )

        if qr_content:
            return qr_content

        qr_content = decode_qr_with_opencv(
            scan_image
        )

        if qr_content:
            return qr_content

    for crop in get_qr_crops(image):
        for scan_image in get_qr_scan_versions(crop):
            qr_content = decode_qr_with_zxing(
                scan_image
            )

            if qr_content:
                return qr_content

            qr_content = decode_qr_with_opencv(
                scan_image
            )

            if qr_content:
                return qr_content

    return None


def get_qr_content_from_image(image_path):
    image = cv2.imread(image_path)

    if image is None:
        return None

    return scan_qr_from_image_array(image)


def get_qr_content_from_pdf(pdf_path):
    document = fitz.open(pdf_path)

    try:
        page_count = min(
            len(document),
            MAX_PDF_PAGES_TO_PROCESS,
        )

        for page_number in range(page_count):
            page = document[page_number]
            pixmap = page.get_pixmap(dpi=600)
            image_bytes = pixmap.tobytes("png")

            image_array = cv2.imdecode(
                np.frombuffer(
                    image_bytes,
                    dtype=np.uint8,
                ),
                cv2.IMREAD_COLOR,
            )

            if image_array is None:
                continue

            qr_content = scan_qr_from_image_array(
                image_array
            )

            if qr_content:
                return qr_content

    finally:
        document.close()

    return None


def clean_qr_content(qr_content):
    if not qr_content:
        return ""

    qr_content = str(qr_content).strip()

    markdown_match = re.search(
        r"\]\((https?://[^)]+)\)",
        qr_content,
        re.IGNORECASE,
    )

    if markdown_match:
        return markdown_match.group(1).strip()

    url_match = re.search(
        r"https?://[^\s)\]]+",
        qr_content,
        re.IGNORECASE,
    )

    if url_match:
        return url_match.group(0).strip()

    return qr_content


def get_qr_type(qr_content):
    if not qr_content:
        return "No QR Found"

    if (
        qr_content.startswith("http://")
        or qr_content.startswith("https://")
    ):
        return "URL"

    return "Text or Certificate Token"


def normalize_compare_value(value):
    if value is None:
        return ""

    value = str(value).strip().lower()

    for character in [
        " ",
        ",",
        ".",
        "-",
        "_",
        "/",
    ]:
        value = value.replace(character, "")

    return value


def compare_certificate_details(
    document_details,
    official_details,
):
    document_details = document_details or {}
    official_details = official_details or {}

    official_fields = official_details.get(
        "detected_fields",
        {},
    )

    fields = [
        (
            "Student Name",
            "student_name",
            "student_name",
        ),
        (
            "Exam Session",
            "exam_session",
            "exam_session",
        ),
        (
            "Roll Number",
            "roll_number",
            "roll_number",
        ),
        (
            "Register Number",
            "register_number",
            "register_number",
        ),
        (
            "Total Marks",
            "total_marks",
            "total_marks",
        ),
        (
            "Result",
            "result",
            "result",
        ),
    ]

    rows = []
    match_count = 0
    mismatch_count = 0
    unavailable_count = 0

    for label, document_key, official_key in fields:
        document_value = document_details.get(
            document_key,
            "",
        )

        official_value = official_fields.get(
            official_key,
            "",
        )

        document_normalized = normalize_compare_value(
            document_value
        )

        official_normalized = normalize_compare_value(
            official_value
        )

        if (
            not document_normalized
            or not official_normalized
        ):
            status = "Unavailable"
            unavailable_count += 1

        elif document_normalized == official_normalized:
            status = "Match"
            match_count += 1

        else:
            status = "Mismatch"
            mismatch_count += 1

        rows.append(
            {
                "field": label,
                "document_value": document_value,
                "official_value": official_value,
                "status": status,
            }
        )

    if mismatch_count:
        result_class = "mismatch"
        overall_status = "Potential mismatch detected"

    elif match_count and unavailable_count == 0:
        result_class = "verified"
        overall_status = "All details matched"

    else:
        result_class = "review"
        overall_status = "Manual review required"

    return {
        "comparison_rows": rows,
        "comparison_summary": {
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "unavailable_count": unavailable_count,
            "result_class": result_class,
            "overall_status": overall_status,
        },
    }


def build_official_details(verification_url):
    empty_details = {
        "source_url": verification_url or "",
        "detected_fields": {},
        "page_title": "",
        "raw_official_text": "",
        "error": None,
    }

    if not verification_url:
        return empty_details

    try:
        official_response = verify_qr_content(
            verification_url
        )

        if not isinstance(
            official_response,
            dict,
        ):
            return empty_details

        if "detected_fields" not in official_response:
            official_response = {
                "source_url": verification_url,
                "detected_fields": official_response,
                "page_title": "",
                "raw_official_text": "",
                "error": None,
            }

        return official_response

    except Exception as error:
        empty_details["error"] = str(error)
        return empty_details


def add_marksheet_fallbacks(
    raw_ocr_text,
    qr_content,
    marksheet_details,
):
    if not marksheet_details:
        return marksheet_details

    is_tndge_qr = (
        qr_content
        and "certverify.tndge.org/ceti-verify"
        in qr_content.lower()
    )

    if (
        is_tndge_qr
        and not marksheet_details.get("total_marks")
    ):
        possible_marks = re.findall(
            r"\b([1-5]\d{2})\b",
            raw_ocr_text,
        )

        possible_marks = [
            mark
            for mark in possible_marks
            if 100 <= int(mark) <= 500
        ]

        unique_marks = list(
            dict.fromkeys(possible_marks)
        )

        if len(unique_marks) == 1:
            marksheet_details["total_marks"] = (
                unique_marks[0]
            )

            marksheet_details[
                "total_marks_source"
            ] = "OCR numeric fallback"

    return marksheet_details


def get_marksheet_field_count(marksheet_details):
    if not marksheet_details:
        return 0

    fields = [
        marksheet_details.get("student_name"),
        marksheet_details.get("roll_number"),
        marksheet_details.get("register_number"),
        marksheet_details.get("total_marks"),
        marksheet_details.get("result"),
    ]

    return sum(
        1
        for field in fields
        if field
    )


def update_failed_request(request_id):
    connection = get_db_connection()

    connection.execute(
        """
        UPDATE verification_requests
        SET processing_status = ?
        WHERE id = ?
        """,
        (
            "OCR or QR Scan Failed",
            request_id,
        ),
    )

    connection.commit()
    connection.close()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["GET", "POST"])
def upload_certificate():
    if request.method == "GET":
        return render_template(
            "upload.html",
            error=None,
        )

    if "certificate_file" not in request.files:
        return render_template(
            "upload.html",
            error=(
                "No file was received. "
                "Please select a certificate file."
            ),
        )

    uploaded_file = request.files[
        "certificate_file"
    ]

    if uploaded_file.filename == "":
        return render_template(
            "upload.html",
            error=(
                "Please select a PDF, JPG, JPEG, "
                "or PNG file."
            ),
        )

    if not allowed_file(uploaded_file.filename):
        return render_template(
            "upload.html",
            error=(
                "Only PDF, JPG, JPEG, and PNG "
                "files are allowed."
            ),
        )

    original_filename = secure_filename(
        uploaded_file.filename
    )

    file_extension = original_filename.rsplit(
        ".",
        1,
    )[1].lower()

    stored_filename = (
        f"{uuid.uuid4().hex}.{file_extension}"
    )

    save_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        stored_filename,
    )

    uploaded_file.save(save_path)
    file_size = os.path.getsize(save_path)

    connection = get_db_connection()

    cursor = connection.execute(
        """
        INSERT INTO verification_requests (
            original_filename,
            stored_filename,
            file_extension,
            file_size,
            processing_status,
            uploaded_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            original_filename,
            stored_filename,
            file_extension,
            file_size,
            "Processing OCR and QR Scan",
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        ),
    )

    request_id = cursor.lastrowid

    connection.commit()
    connection.close()

    try:
        if file_extension == "pdf":
            raw_ocr_text = extract_text_from_pdf(
                save_path
            )

            qr_content = get_qr_content_from_pdf(
                save_path
            )

        else:
            raw_ocr_text = extract_text_from_image(
                save_path
            )

            qr_content = get_qr_content_from_image(
                save_path
            )

        qr_content = clean_qr_content(
            qr_content
        )

        details = extract_certificate_details(
            raw_ocr_text
        )

        document_analysis = detect_document_type(
            raw_ocr_text
        )

        marksheet_details = (
            extract_marksheet_details(
                raw_ocr_text
            )
        )

        marksheet_details = add_marksheet_fallbacks(
            raw_ocr_text,
            qr_content,
            marksheet_details,
        )

        marksheet_field_count = (
            get_marksheet_field_count(
                marksheet_details
            )
        )

        if (
            document_analysis.get("document_type")
            == "Unknown"
            and marksheet_field_count >= 2
        ):
            document_analysis = {
                "document_type": "Marksheet",
                "confidence": "Medium",
            }

        qr_detected = 1 if qr_content else 0
        qr_type = get_qr_type(qr_content)

        verification_url = clean_qr_content(
            qr_content
        )

        official_details = build_official_details(
            verification_url
        )

        comparison_result = (
            compare_certificate_details(
                marksheet_details,
                official_details,
            )
        )

        verification_result = {
            "verification_url": verification_url,
            "official_details": official_details,
            "comparison_rows": comparison_result[
                "comparison_rows"
            ],
            "comparison_summary": comparison_result[
                "comparison_summary"
            ],
        }

        print(
            "\n========== VERIFICATION DEBUG =========="
        )
        print("QR Content:", qr_content)
        print(
            "Verification URL:",
            verification_url,
        )
        print(
            "Marksheet Details:",
            marksheet_details,
        )
        print(
            "Official Details:",
            official_details,
        )
        print(
            "Comparison Result:",
            comparison_result,
        )
        print(
            "========================================\n"
        )

        connection = get_db_connection()

        connection.execute(
            """
            INSERT INTO certificate_ocr_details (
                verification_request_id,
                raw_ocr_text,
                extracted_name,
                extracted_certificate_id,
                extracted_issue_date,
                extracted_marks,
                extracted_course,
                extracted_issuer,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                raw_ocr_text,
                details.get("name"),
                details.get("certificate_id"),
                details.get("issue_date"),
                details.get("marks"),
                details.get("course"),
                details.get("issuer"),
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            ),
        )

        connection.execute(
            """
            INSERT INTO qr_scan_details (
                verification_request_id,
                qr_detected,
                qr_content,
                qr_type,
                scanned_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request_id,
                qr_detected,
                qr_content,
                qr_type,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            ),
        )

        summary = comparison_result[
            "comparison_summary"
        ]

        connection.execute(
            """
            UPDATE verification_requests
            SET processing_status = ?,
                final_status = ?,
                confidence_score = ?
            WHERE id = ?
            """,
            (
                "OCR, QR, and comparison completed",
                summary["overall_status"],
                float(summary["match_count"]),
                request_id,
            ),
        )

        connection.commit()
        connection.close()

        return render_template(
            "ocr_result.html",
            request_id=request_id,
            details=details,
            raw_ocr_text=raw_ocr_text,
            qr_detected=qr_detected,
            qr_content=qr_content,
            qr_type=qr_type,
            document_analysis=document_analysis,
            marksheet_details=marksheet_details,
            verification_result=verification_result,
        )

    except Exception as processing_error:
        update_failed_request(request_id)

        print(
            "Certificate processing error:",
            processing_error,
        )

        return render_template(
            "upload.html",
            error=(
                "Certificate processing failed: "
                f"{processing_error}"
            ),
        )


@app.errorhandler(413)
def file_too_large(error):
    return (
        render_template(
            "upload.html",
            error=(
                "File size is too large. "
                "Maximum allowed file size is 10 MB."
            ),
        ),
        413,
    )


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/register")
def register():
    return render_template("register.html")


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)