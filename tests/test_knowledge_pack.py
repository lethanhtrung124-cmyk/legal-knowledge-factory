import zipfile

from app.document_processor import Article, ParsedDocument
from app.knowledge_pack import build_article_knowledge, build_knowledge_pack, gpt_knowledge_file_name, render_gpt_knowledge_markdown, validate_merged_markdown


def make_parsed_document() -> ParsedDocument:
    article = Article(
        number="1",
        title="Phạm vi điều chỉnh",
        raw_content=(
            "Điều 1. Phạm vi điều chỉnh\n"
            "1. Văn bản này quy định về hồ sơ điện tử.\n"
            "a) Nội dung gốc phải được giữ nguyên."
        ),
        clauses=["1. Văn bản này quy định về hồ sơ điện tử."],
        points=["a) Nội dung gốc phải được giữ nguyên."],
    )
    return ParsedDocument(
        file_name="sample.docx",
        document_type="Thông tư",
        document_number="01/2026/TT-BTC",
        issued_date="01/01/2026",
        effective_date="01/02/2026",
        issuing_authority="Bộ Tài chính",
        title="Quy định về hồ sơ điện tử",
        raw_text=article.raw_content,
        preamble="",
        legal_basis=["Căn cứ Luật Giao dịch điện tử;"],
        scope="Văn bản này quy định về hồ sơ điện tử.",
        applicable_subjects="- cơ quan nhà nước\n- tổ chức, cá nhân có liên quan",
        main_text=article.raw_content,
        appendix_text="Phụ lục\nMẫu biểu",
        closing_text="",
        chapters=[],
        sections=[],
        subsections=[],
        articles=[article],
        appendices=[],
        definitions=[],
    )


def test_build_pack_includes_unified_gpt_knowledge_markdown(tmp_path):
    parsed = make_parsed_document()
    zip_path = build_knowledge_pack(parsed, tmp_path)
    expected_name = gpt_knowledge_file_name(parsed)

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()

    content = (tmp_path / expected_name).read_text(encoding="utf-8")

    assert expected_name not in names
    assert (tmp_path / expected_name).exists()
    assert "00_metadata.yaml" in names
    assert "validation_report.md" in names
    assert "06_prompt_system.md" in names
    assert "Validation Report" not in content
    assert "System Prompt" not in content
    assert "Điều/Mục" not in content
    assert content.startswith("# Quy định về hồ sơ điện tử")
    assert "Điều 1. Phạm vi điều chỉnh" in content
    assert content.index("Điều 1. Phạm vi điều chỉnh") < content.index("## Từ khóa")
    assert content.index("Điều 1. Phạm vi điều chỉnh") < content.index("## FAQ")


def test_merged_markdown_validator_catches_forbidden_label_and_duplicate_article_heading():
    parsed = make_parsed_document()
    article_knowledge = build_article_knowledge(parsed)
    markdown = render_gpt_knowledge_markdown(parsed, article_knowledge).replace(
        "#### Điều 1",
        "#### Điều/Mục 1. Phạm vi điều chỉnh\n#### Điều 1. Phạm vi điều chỉnh",
    )

    validation = validate_merged_markdown(parsed, article_knowledge, markdown)

    assert validation.status == "FAIL"
    assert any("Điều/Mục" in error for error in validation.errors)


def test_merged_markdown_uses_muc_for_thematic_resolution_without_duplicate_chapter():
    article = Article(
        number="I",
        title="QUAN ĐIỂM CHỈ ĐẠO",
        raw_content="I- QUAN ĐIỂM CHỈ ĐẠO\n1. Nội dung quan điểm.",
        chapter="I- QUAN ĐIỂM CHỈ ĐẠO",
        clauses=["1. Nội dung quan điểm."],
    )
    parsed = make_parsed_document()
    parsed.document_type = "Nghị quyết"
    parsed.document_number = "57-NQ/TW"
    parsed.articles = [article]
    parsed.chapters = ["I- QUAN ĐIỂM CHỈ ĐẠO"]
    parsed.raw_text = article.raw_content
    parsed.main_text = article.raw_content

    content = render_gpt_knowledge_markdown(parsed, build_article_knowledge(parsed))

    assert "Điều/Mục" not in content
    assert "### Mục I" in content
    assert content.count("### I- QUAN ĐIỂM CHỈ ĐẠO") == 0
