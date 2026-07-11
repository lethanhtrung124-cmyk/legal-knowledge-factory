from app.document_processor import (
    detect_document_number,
    detect_effective_date,
    detect_title,
    detect_document_type,
    extract_closing_metadata,
    parse_appendices,
    parse_structure,
    split_main_and_appendix,
    split_main_appendix_closing,
    split_preamble_and_basis,
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


def test_legal_basis_excludes_proposal_and_enactment_line():
    lines = [
        "CHÍNH PHỦ",
        "Số: 224/2026/NĐ-CP",
        "NGHỊ ĐỊNH",
        "Quy định chi tiết một số điều",
        "Căn cứ Luật Tổ chức Chính phủ;",
        "Căn cứ Luật Chuyển đổi số;",
        "Theo đề nghị của Bộ trưởng Bộ Khoa học và Công nghệ;",
        "Chính phủ ban hành Nghị định quy định chi tiết một số điều.",
        "Chương I",
        "Điều 1. Phạm vi điều chỉnh",
    ]

    _, legal_basis = split_preamble_and_basis(lines)

    assert legal_basis == ["Căn cứ Luật Tổ chức Chính phủ;", "Căn cứ Luật Chuyển đổi số;"]


def test_main_parser_stops_before_closing_section():
    lines = [
        "Chương I",
        "Điều 1. Phạm vi điều chỉnh",
        "1. Nội dung chính.",
        "Nơi nhận:",
        "- Văn phòng Chính phủ;",
        "TM. CHÍNH PHỦ",
        "THỦ TƯỚNG",
        "Nguyễn Văn A",
    ]

    main_lines, appendix_lines, closing_lines = split_main_appendix_closing(lines)
    _, _, _, articles = parse_structure(main_lines)
    recipients, signer = extract_closing_metadata(closing_lines)

    assert appendix_lines == []
    assert [article.number for article in articles] == ["1"]
    assert "Nơi nhận" not in articles[0].raw_content
    assert recipients[0] == "Nơi nhận:"
    assert "THỦ TƯỚNG" in signer
    assert "Nguyễn Văn A" in signer


def test_chairperson_inside_article_is_not_closing_section():
    _, _, _, articles = parse_structure(
        [
            "Điều 50. Thẩm quyền quyết định",
            "1. Chủ tịch Ủy ban nhân dân cấp tỉnh quyết định dự án theo thẩm quyền.",
            "2. Bộ trưởng, Thủ trưởng cơ quan ngang bộ tổ chức thực hiện.",
            "Điều 51. Nội dung tiếp theo",
            "1. Nội dung chính.",
        ]
    )

    assert [article.number for article in articles] == ["50", "51"]


def test_appendix_after_signature_is_kept_outside_closing_text():
    lines = [
        "Điều 1. Nội dung chính",
        "1. Quy định chính.",
        "Nơi nhận:",
        "- Như trên;",
        "TM. CHÍNH PHỦ",
        "KT. THỦ TƯỚNG",
        "PHÓ THỦ TƯỚNG",
        "Nguyễn Văn A",
        "Phụ lục",
        "Mẫu số 01",
        "Nội dung biểu mẫu.",
    ]

    main_lines, appendix_lines, closing_lines = split_main_appendix_closing(lines)

    assert main_lines == ["Điều 1. Nội dung chính", "1. Quy định chính."]
    assert appendix_lines[0] == "Phụ lục"
    assert "Nơi nhận:" in closing_lines
    assert "Mẫu số 01" not in closing_lines


def test_recipient_marker_inside_appendix_is_not_document_closing():
    lines = [
        "Điều 1. Nội dung chính",
        "1. Quy định chính.",
        "Phụ lục",
        "Mẫu số 01",
        "Nơi nhận:",
        "- Như trên;",
        "ĐẠI DIỆN CƠ QUAN",
    ]

    main_lines, appendix_lines, closing_lines = split_main_appendix_closing(lines)

    assert main_lines == ["Điều 1. Nội dung chính", "1. Quy định chính."]
    assert "Nơi nhận:" in appendix_lines
    assert closing_lines == []


def test_detect_effective_date_from_signing_date_phrase():
    _, _, _, articles = parse_structure(
        [
            "Điều 92. Hiệu lực thi hành",
            "Nghị định này có hiệu lực thi hành kể từ ngày ký ban hành.",
        ]
    )

    assert detect_effective_date(articles, "11/07/2026") == "Kể từ ngày ký ban hành (11/07/2026)"
