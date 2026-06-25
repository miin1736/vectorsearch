import fitz

from koreanops_rag.office.parse_pdfs import clean_pages, extract_pdf


def _sample_pdf() -> bytes:
    document = fitz.open()
    for page_number in range(2):
        page = document.new_page(width=600, height=800)
        page.insert_text((50, 40), "repeated header", fontsize=10)
        page.insert_text((50, 100), f"title {page_number + 1}", fontsize=18)
        page.insert_text((50, 160), "left column body", fontsize=11)
        page.insert_text((330, 160), "right column body", fontsize=11)
        page.insert_text((290, 770), str(page_number + 1), fontsize=9)
    payload = document.tobytes()
    document.close()
    return payload


def test_extract_and_clean_pdf_blocks():
    pages, title, text_layer_pages = extract_pdf(_sample_pdf())
    cleaned = clean_pages("doc", pages)

    assert len(pages) == 2
    assert text_layer_pages == 2
    assert title.startswith("title")
    assert "repeated header" not in cleaned[0]["clean_text"]
    assert "left column body" in cleaned[0]["clean_text"]
    assert "right column body" in cleaned[0]["clean_text"]
