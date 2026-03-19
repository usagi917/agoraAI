"""document_parser のテスト"""

from src.app.services.document_parser import parse_pdf


def test_parse_pdf_basic():
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello World")
    pdf_bytes = doc.tobytes()
    doc.close()

    text = parse_pdf(pdf_bytes)
    assert "Hello World" in text
