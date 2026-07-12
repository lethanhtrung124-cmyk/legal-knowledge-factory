import zipfile

from app.document_processor import Article, ParsedDocument
from app.knowledge_pack import build_knowledge_pack, gpt_knowledge_file_name


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
        content = archive.read(expected_name).decode("utf-8")

    assert expected_name in names
    assert "00_metadata.yaml" in names
    assert "validation_report.md" in names
    assert "06_prompt_system.md" in names
    assert "Validation Report" not in content
    assert "System Prompt" not in content
    assert "Điều 1. Phạm vi điều chỉnh" in content
    assert content.index("Điều 1. Phạm vi điều chỉnh") < content.index("## Từ khóa")
    assert content.index("Điều 1. Phạm vi điều chỉnh") < content.index("## FAQ")
