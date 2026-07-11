from app.document_processor import (
    detect_document_number,
    detect_title,
    detect_document_type,
    parse_appendices,
    parse_structure,
    split_main_and_appendix,
)


def test_metadata_parser_prefers_number_line_before_legal_basis():
    lines = [
        "CHÍNH PHỦ",
        "Số: 224/2026/NĐ-CP",
        "NGHỊ ĐỊNH",
        "Quy định chi tiết một số điều và biện pháp thi hành Luật Chuyển đổi số",
        "Căn cứ Luật số 11/2024/QH15;",
    ]

    assert detect_document_type(lines) == "Nghị định"
    assert detect_document_number(lines) == "224/2026/NĐ-CP"


def test_metadata_parser_handles_law_number_line_without_cutting_suffix():
    lines = [
        "Luật số: 148/2025/QH15",
        "LUẬT",
        "CHUYỂN ĐỔI SỐ",
        "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;",
        "Chương I",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về chuyển đổi số.",
    ]

    assert detect_document_type(lines) == "Luật"
    assert detect_document_number(lines) == "148/2025/QH15"
    assert detect_title(lines, "Luật") == "Chuyển đổi số"


def test_title_stops_before_legal_basis_and_articles():
    lines = [
        "THÔNG TƯ",
        "Quy định về hồ sơ điện tử",
        "Căn cứ Luật Giao dịch điện tử;",
        "Điều 1. Phạm vi điều chỉnh",
    ]

    assert detect_title(lines, "Thông tư") == "Quy định về hồ sơ điện tử"


def test_article_parser_stops_before_appendix():
    lines = [
        "Chương I Quy định chung",
        "Điều 1. Phạm vi điều chỉnh",
        "1. Nội dung chính.",
        "PHỤ LỤC I",
        "Điều 2. Nội dung trong phụ lục",
    ]

    main_lines, appendix_lines = split_main_and_appendix(lines)
    _, _, _, articles = parse_structure(main_lines)

    assert [article.number for article in articles] == ["1"]
    assert appendix_lines[0] == "PHỤ LỤC I"


def test_appendix_detector_detects_forms():
    appendices = parse_appendices(
        [
            "Mẫu số 01",
            "Mẫu báo cáo",
            "Điều 1. Nội dung trong mẫu không phải điều chính.",
        ]
    )

    assert len(appendices) == 1
    assert appendices[0].kind == "mau_so"
    assert "Điều 1" in appendices[0].raw_content
