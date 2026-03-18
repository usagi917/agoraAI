"""文書パーサー: txt/md/pdf からテキスト抽出"""

def parse_pdf(content: bytes) -> str:
    import pymupdf

    doc = pymupdf.open(stream=content, filetype="pdf")
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)
