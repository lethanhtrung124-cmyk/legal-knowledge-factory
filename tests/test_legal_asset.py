from app.document_processor import Appendix, Article, ParsedDocument
from app.legal_asset import (
    build_legal_knowledge_asset,
    build_structure,
    checksum,
    detect_issued_content_start,
    render_asset_markdown,
    render_gpt_knowledge_from_asset,
    validate_asset,
    validate_structure_for_export,
)


def make_parsed(raw_text: str, articles: list[Article] | None = None, appendices: list[Appendix] | None = None) -> ParsedDocument:
    return ParsedDocument(
        file_name="sample.docx",
        document_type="Quyết định",
        document_number="671/QĐ-BTTTT",
        issued_date="01/01/2026",
        effective_date="01/01/2026",
        issuing_authority="Bộ Thông tin và Truyền thông",
        title="Ban hành hướng dẫn kiểm thử",
        raw_text=raw_text,
        preamble="",
        legal_basis=[],
        scope="Quyết định này ban hành hướng dẫn kiểm thử.",
        applicable_subjects="- cơ quan, tổ chức, cá nhân có liên quan",
        main_text=raw_text,
        appendix_text="",
        closing_text="",
        chapters=[],
        sections=[],
        subsections=[],
        articles=articles or [],
        appendices=appendices or [],
        definitions=[],
    )


def test_detect_issued_content_from_heading_and_attached_confirmation():
    lines = [
        "Điều 1. Ban hành kèm theo Quyết định này Hướng dẫn kiểm thử.",
        "Điều 2. Quyết định này có hiệu lực.",
        "KT. BỘ TRƯỞNG",
        "THỨ TRƯỞNG",
        "HƯỚNG DẪN KIỂM THỬ",
        "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
        "Điều 1. Phạm vi áp dụng",
    ]

    assert detect_issued_content_start(lines) == 4


def test_asset_separates_main_and_issued_content_with_same_article_number():
    raw_text = "\n".join(
        [
            "Điều 1. Ban hành kèm theo Quyết định này Hướng dẫn kiểm thử.",
            "Điều 2. Tổ chức thực hiện",
            "KT. BỘ TRƯỞNG",
            "THỨ TRƯỞNG",
            "HƯỚNG DẪN KIỂM THỬ",
            "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
            "Điều 1. Phạm vi áp dụng",
            "1. Hướng dẫn này áp dụng đối với cơ quan, tổ chức.",
            "Điều 2. Nội dung hướng dẫn",
            "1. Thực hiện theo Phụ lục IV.",
        ]
    )
    parsed = make_parsed(raw_text)

    asset = build_legal_knowledge_asset(parsed)
    main_articles = [node for node in asset.nodes if node.node_type == "PROVISION" and node.scope_type == "MAIN_DOCUMENT"]
    issued_articles = [node for node in asset.nodes if node.node_type == "PROVISION" and node.scope_type == "ISSUED_CONTENT"]

    assert asset.stats["issued_content_count"] == 1
    assert [node.number for node in main_articles] == ["1", "2"]
    assert [node.number for node in issued_articles] == ["1", "2"]
    assert validate_asset(asset.nodes).status in {"PASS", "WARNING"}


def test_reference_to_appendix_in_sentence_does_not_create_appendix():
    raw_text = "\n".join(
        [
            "Điều 1. Ban hành kèm theo Quyết định này Hướng dẫn kiểm thử.",
            "KT. BỘ TRƯỞNG",
            "HƯỚNG DẪN KIỂM THỬ",
            "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
            "Điều 1. Nội dung",
            "1. Thực hiện theo Phụ lục IV và Phụ lục V của Hướng dẫn này.",
        ]
    )
    parsed = make_parsed(raw_text)

    asset = build_legal_knowledge_asset(parsed)

    assert asset.stats["appendix_count"] == 0
    assert asset.stats["reference_count"] == 2


def test_real_appendices_are_children_of_issued_content():
    raw_text = "\n".join(
        [
            "Điều 1. Ban hành kèm theo Quyết định này Hướng dẫn kiểm thử.",
            "KT. BỘ TRƯỞNG",
            "HƯỚNG DẪN KIỂM THỬ",
            "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
            "Điều 1. Nội dung",
            "1. Nội dung hướng dẫn.",
            "PHỤ LỤC I",
            "BẢNG THAM SỐ",
            "Cột A | Cột B",
            "PHỤ LỤC II",
            "CÔNG THỨC",
            "C = A + B",
        ]
    )
    parsed = make_parsed(raw_text)

    asset = build_legal_knowledge_asset(parsed)
    issued = next(node for node in asset.nodes if node.node_type == "ISSUED_CONTENT")
    appendices = [node for node in asset.nodes if node.node_type == "APPENDIX"]

    assert asset.stats["appendix_count"] == 2
    assert {node.parent_id for node in appendices} == {issued.id}
    assert any("C = A + B" in node.original_text for node in appendices)


def test_asset_export_has_required_headings_and_no_false_appendix_label():
    raw_text = "\n".join(
        [
            "Điều 1. Ban hành kèm theo Quyết định này Khung kiểm thử.",
            "KT. BỘ TRƯỞNG",
            "KHUNG KIỂM THỬ",
            "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
            "Mục I. Quy định chung",
            "Điều 1. Phạm vi",
            "1. Nội dung.",
        ]
    )
    parsed = make_parsed(raw_text)
    asset = build_legal_knowledge_asset(parsed)

    markdown = render_asset_markdown(asset)

    assert "## SOURCE OF TRUTH" in markdown
    assert "## Văn bản chính" in markdown
    assert "## Nội dung ban hành kèm theo" in markdown
    assert "Phụ lục 01. Phụ lục" not in markdown


def test_migration_report_preserves_legacy_checksum():
    raw_text = "Điều 1. Nội dung\n1. Không có nội dung ban hành kèm theo."
    parsed = make_parsed(raw_text, articles=[Article(number="1", title="Nội dung", raw_content=raw_text)])

    asset = build_legal_knowledge_asset(parsed)

    assert asset.migration_report["legacy_checksum"] == checksum(raw_text)
    assert asset.validation["status"] in {"PASS", "WARNING"}


def test_structure_json_gates_asset_gpt_export_for_issued_content():
    raw_text = "\n".join(
        [
            "Điều 1. Ban hành kèm theo Quyết định này Hướng dẫn kiểm thử.",
            "Điều 2. Hiệu lực thi hành",
            "Điều 3. Tổ chức thực hiện",
            "KT. BỘ TRƯỞNG",
            "HƯỚNG DẪN KIỂM THỬ",
            "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
            "Điều 1. Nội dung 1",
            "Điều 2. Nội dung 2",
            "Điều 3. Nội dung 3",
            "Điều 4. Nội dung 4",
            "Điều 5. Nội dung 5",
            "Điều 6. Nội dung 6",
            "Điều 7. Nội dung 7",
            "PHỤ LỤC I",
            "Nội dung phụ lục I",
            "PHỤ LỤC II",
            "Nội dung phụ lục II",
            "PHỤ LỤC III",
            "Nội dung phụ lục III",
            "PHỤ LỤC IV",
            "Nội dung phụ lục IV",
            "PHỤ LỤC V",
            "Nội dung phụ lục V",
            "PHỤ LỤC VI",
            "Nội dung phụ lục VI",
            "PHỤ LỤC VII",
            "Nội dung phụ lục VII",
            "PHỤ LỤC VIII",
            "Nội dung phụ lục VIII",
        ]
    )
    parsed = make_parsed(raw_text)
    asset = build_legal_knowledge_asset(parsed)
    structure = build_structure(asset)
    validation = validate_structure_for_export(asset)
    markdown = render_gpt_knowledge_from_asset(asset)

    issued = structure["tree"]["issued_content"][0]
    assert validation["status"] in {"PASS", "WARNING"}
    assert asset.stats["main_document_article_count"] == 3
    assert asset.stats["issued_content_count"] == 1
    assert asset.stats["issued_content_provision_count"] == 7
    assert asset.stats["appendix_count"] == 8
    assert [item["number"] for item in issued["provisions"]] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [item["canonical_number"] for item in issued["appendices"]] == ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
    assert "## Nội dung ban hành kèm theo" in markdown
    assert "Phụ lục 01. Phụ lục" not in markdown
