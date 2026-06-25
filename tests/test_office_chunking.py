from koreanops_rag.office.chunking import _pack_sections, split_fixed


def test_fixed_chunks_overlap_and_preserve_text():
    text = " ".join(f"word{index}" for index in range(20))

    chunks = split_fixed(text, size=8, overlap=2)

    assert len(chunks) == 3
    assert "word0" in chunks[0]
    assert "word6" in chunks[0] and "word6" in chunks[1]


def test_structure_chunks_keep_heading_with_body():
    blocks = [
        {"page_num": 1, "reading_order": 0, "text": "Heading One", "is_heading": True},
        {"page_num": 1, "reading_order": 1, "text": "First body.", "is_heading": False},
        {"page_num": 2, "reading_order": 0, "text": "Heading Two", "is_heading": True},
        {"page_num": 2, "reading_order": 1, "text": "Second body.", "is_heading": False},
    ]

    sections = _pack_sections(blocks, min_tokens=4, max_tokens=100)

    assert len(sections) == 2
    assert sections[0]["heading"] == "Heading One"
    assert "First body" in sections[0]["text"]
