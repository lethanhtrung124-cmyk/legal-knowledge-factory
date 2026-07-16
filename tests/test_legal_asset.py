import json

import pytest

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
    write_legal_asset_outputs,
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


def test_gpt_export_requires_asset_validation_pass():
    raw_text = "Điều 1. Nội dung\n1. Nội dung kiểm thử."
    parsed = make_parsed(raw_text, articles=[Article(number="1", title="Nội dung", raw_content=raw_text)])
    asset = build_legal_knowledge_asset(parsed)
    asset.validation = {"status": "WARNING", "errors": [], "warnings": [{"code": "TEST", "message": "review"}]}

    validation = validate_structure_for_export(asset)

    assert validation["status"] == "FAIL"
    with pytest.raises(ValueError, match="Structure validation FAIL"):
        render_gpt_knowledge_from_asset(asset)


def test_semantic_layer_exports_json_and_markdown_sections(tmp_path):
    raw_text = "\n".join(
        [
            "Điều 1. Ban hành kèm theo Quyết định này Hướng dẫn xác định chi phí phần mềm nội bộ.",
            "Điều 2. Hiệu lực thi hành",
            "Điều 3. Tổ chức thực hiện",
            "KT. BỘ TRƯỞNG",
            "HƯỚNG DẪN XÁC ĐỊNH CHI PHÍ PHẦN MỀM NỘI BỘ",
            "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
            "Điều 1. Giải thích từ ngữ",
            "1. Tác nhân (Actor) là vai trò tương tác với phần mềm nội bộ.",
            "Điều 2. Trình tự xác định chi phí",
            "1. Xác định hồ sơ phục vụ xác định chi phí phần mềm nội bộ.",
            "2. Tính chi phí theo Phụ lục I.",
            "PHỤ LỤC I",
            "CÔNG THỨC XÁC ĐỊNH CHI PHÍ",
            "G = 1,4 x E x P x H",
        ]
    )
    parsed = make_parsed(raw_text)

    asset = build_legal_knowledge_asset(parsed)
    outputs = write_legal_asset_outputs(asset, tmp_path)

    assert asset.validation["status"] == "PASS"
    assert (outputs["semantic_dir"] / "topics.json").exists()
    assert (outputs["semantic_dir"] / "keywords.json").exists()
    assert (outputs["semantic_dir"] / "concepts.json").exists()
    assert (outputs["semantic_dir"] / "formulas.json").exists()
    assert (outputs["semantic_dir"] / "procedures.json").exists()
    assert (outputs["semantic_dir"] / "cross_references.json").exists()
    assert (outputs["semantic_dir"] / "legal_references.json").exists()
    assert (outputs["semantic_dir"] / "appendix_metadata.json").exists()
    assert (outputs["semantic_dir"] / "semantic_validation_report.json").exists()
    formulas = json.loads((outputs["semantic_dir"] / "formulas.json").read_text(encoding="utf-8"))
    entities = json.loads((outputs["semantic_dir"] / "entities.json").read_text(encoding="utf-8"))
    procedures = json.loads((outputs["semantic_dir"] / "procedures.json").read_text(encoding="utf-8"))
    semantic_report = json.loads((outputs["semantic_dir"] / "semantic_validation_report.json").read_text(encoding="utf-8"))
    markdown = outputs["gpt_markdown"].read_text(encoding="utf-8")

    assert any(item["display_expression"] == "G = 1,4 x E x P x H" for item in formulas)
    assert all(item["supporting_node_ids"] for item in formulas)
    assert {"FORMULA_VARIABLE", "LEGAL_AUTHORITY", "APPLICABLE_SUBJECT"} <= {item["entity_type"] for item in entities}
    assert procedures and len(procedures[0]["steps"]) == 2
    assert semantic_report["status"] == "PASS"
    assert all(check["status"] == "PASS" for check in semantic_report["checks"])
    assert "## Chỉ mục khái niệm" in markdown
    assert "## Công thức" in markdown
    assert "## Trình tự thực hiện" in markdown
    assert "| node_id | scope_type | title | topics | canonical_keywords | formulas | references |" in markdown


def test_semantic_engine_canonicalizes_and_deduplicates_core_indexes():
    raw_text = "\n".join(
        [
            "Điều 1. Ban hành kèm theo Quyết định này Hướng dẫn xác định chi phí phần mềm nội bộ.",
            "Điều 2. Hiệu lực thi hành",
            "Điều 3. Tổ chức thực hiện",
            "KT. BỘ TRƯỞNG",
            "HƯỚNG DẪN XÁC ĐỊNH CHI PHÍ PHẦN MỀM NỘI BỘ",
            "(Ban hành kèm theo Quyết định số 671/QĐ-BTTTT)",
            "Điều 1. Nội dung viện dẫn",
            "1. Thực hiện theo Phụ lục I, Phụ lục I và Nghị định số 73/2019/NĐ-CP.",
            "2. Căn cứ Nghị định 73/2019/NĐ-CP để áp dụng phương pháp.",
            "PHỤ LỤC I",
            "CÔNG THỨC XÁC ĐỊNH CHI PHÍ",
            "G = 1,4 x E x P x H",
            "G=1,4×E×P×H",
        ]
    )
    parsed = make_parsed(raw_text)

    asset = build_legal_knowledge_asset(parsed)
    formulas = asset.semantic["formulas"]
    xrefs = asset.semantic["cross_references"]
    legal_refs = asset.semantic["legal_references"]

    assert asset.validation["status"] == "PASS"
    assert [formula["expression"] for formula in formulas] == ["G = 1,4 x E x P x H"]
    assert formulas[0]["supporting_node_ids"]
    assert len(xrefs) == 1
    assert len(legal_refs) == 1
    assert legal_refs[0]["target_document_type"] == "Nghị định"
    assert legal_refs[0]["target_document_number"] == "73/2019/NĐ-CP"


def test_long_appendix_with_reference_phrases_does_not_block_export():
    raw_text = "\n".join(
        [
            "PHỤ LỤC 01",
            "KẾ HOẠCH DỊCH CHUYỂN, TÍCH HỢP CÁC HỆ THỐNG CNTT",
            "STT",
            "Tên hệ thống",
            "Đơn vị chủ trì",
            "Ghi chú",
            "1",
            "CSDL quốc gia",
            "Cục CNTT",
            "Hệ thống chuyển lên TTDLQG theo Phụ lục kế hoạch và theo Công văn hướng dẫn.",
            "2",
            "CSDL chuyên ngành",
            "Đơn vị nghiệp vụ",
            "Nội dung bảng dữ liệu là phụ lục thật, không phải dòng dẫn chiếu.",
        ]
    )
    parsed = make_parsed(
        raw_text,
        articles=[],
        appendices=[Appendix(number="01", title="Kế hoạch dịch chuyển", raw_content=raw_text)],
    )

    asset = build_legal_knowledge_asset(parsed)
    markdown = render_gpt_knowledge_from_asset(asset)

    assert asset.validation["status"] == "PASS"
    assert asset.stats["appendix_count"] == 1
    assert "PHỤ LỤC 01" in markdown
