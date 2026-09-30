def detect_document_type(raw_text):
    text = raw_text.lower()

    marksheet_keywords = [
        "marksheet",
        "mark sheet",
        "subject",
        "subject code",
        "semester",
        "cgpa",
        "gpa",
        "total marks",
        "maximum marks",
        "percentage",
        "register number",
        "register no",
        "roll number",
        "roll no",
        "hall ticket",
        "grade",
        "result"
    ]

    certificate_keywords = [
        "certificate",
        "certificate id",
        "credential id",
        "credential",
        "awarded to",
        "issued to",
        "this is to certify",
        "course completion",
        "completion certificate",
        "certify that"
    ]

    marksheet_score = sum(
        1 for keyword in marksheet_keywords
        if keyword in text
    )

    certificate_score = sum(
        1 for keyword in certificate_keywords
        if keyword in text
    )

    if marksheet_score >= 2 and marksheet_score > certificate_score:
        return {
            "document_type": "Marksheet",
            "confidence": "High",
            "marksheet_score": marksheet_score,
            "certificate_score": certificate_score
        }

    if certificate_score >= 1 and certificate_score >= marksheet_score:
        return {
            "document_type": "Certificate",
            "confidence": "High",
            "marksheet_score": marksheet_score,
            "certificate_score": certificate_score
        }

    return {
        "document_type": "Unknown",
        "confidence": "Low",
        "marksheet_score": marksheet_score,
        "certificate_score": certificate_score
    }