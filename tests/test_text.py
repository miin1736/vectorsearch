from koreanops_rag.text import clean_text, split_tags


def test_clean_text_removes_html_and_normalizes_space():
    assert clean_text("<p>Hello&nbsp; world</p>\n\nagain") == "Hello world again"


def test_split_tags_handles_multiple_delimiters():
    assert split_tags("payment, api; timeout|db") == ["payment", "api", "timeout", "db"]
