from app.document_processor import (
    Article,
    detect_document_number,
    detect_effective_date,
    detect_applicable_subjects,
    detect_issuing_authority,
    detect_title,
    detect_document_type,
    extract_closing_metadata,
    parse_appendices,
    parse_structure,
    split_main_and_appendix,
    split_main_appendix_closing,
    split_preamble_and_basis,
)
from app.knowledge_pack import article_contains_appendix_marker, build_article_knowledge, validate_pack


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


def test_decision_title_stops_before_signer_title():
    lines = [
        "BỘ KHOA HỌC VÀ CÔNG NGHỆ",
        "Số: 292/QĐ-BKHCN",
        "QUYẾT ĐỊNH",
        "BAN HÀNH KHUNG KIẾN TRÚC CHÍNH PHỦ SỐ VIỆT NAM, PHIÊN BẢN 4.0",
        "BỘ TRƯỞNG BỘ KHOA HỌC VÀ CÔNG NGHỆ",
        "Căn cứ Nghị định số 55/2025/NĐ-CP;",
    ]

    assert detect_title(lines, "Quyết định") == "Ban hành khung kiến trúc chính phủ số việt nam, phiên bản 4.0"


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


def test_decision_article_with_attached_phrase_is_not_appendix_start():
    lines = [
        "QUYẾT ĐỊNH:",
        "Điều 1. Ban hành kèm theo Quyết định này Khung kiến trúc Chính phủ số Việt Nam, phiên bản 4.0.",
        "Điều 2. Quyết định này có hiệu lực thi hành kể từ ngày ký.",
        "Điều 3. Chánh Văn phòng chịu trách nhiệm thi hành Quyết định này.",
        "Nơi nhận:",
        "- Như Điều 3;",
        "KT. BỘ TRƯỞNG",
        "THỨ TRƯỞNG",
        "Nguyễn Văn A",
        "KHUNG KIẾN TRÚC CHÍNH PHỦ SỐ VIỆT NAM",
        "(Ban hành kèm theo Quyết định số 292/QĐ-BKHCN ngày 25/03/2025)",
        "CHƯƠNG 1. KHÁI QUÁT CHUNG",
    ]

    main_lines, appendix_lines, closing_lines = split_main_appendix_closing(lines)
    _, _, _, articles = parse_structure(main_lines)

    assert [article.number for article in articles] == ["1", "2", "3"]
    assert appendix_lines[0] == "KHUNG KIẾN TRÚC CHÍNH PHỦ SỐ VIỆT NAM"
    assert closing_lines[0] == "Nơi nhận:"


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


def test_decision_effective_date_from_article_body_without_effective_title():
    _, _, _, articles = parse_structure(
        [
            "Điều 1. Ban hành văn bản kèm theo",
            "Nội dung ban hành.",
            "Điều 2. Hiệu lực",
            "Quyết định này có hiệu lực thi hành kể từ ngày ký.",
        ]
    )

    assert detect_effective_date(articles, "25/03/2025") == "Kể từ ngày ký ban hành (25/03/2025)"


def test_decision_effective_date_does_not_use_replaced_document_dates():
    _, _, _, articles = parse_structure(
        [
            "Điều 2. Hiệu lực",
            "Quyết định này có hiệu lực thi hành kể từ ngày ký và thay thế Quyết định số 2568/QĐ-BTTTT ngày 29 tháng 12 năm 2023.",
        ]
    )

    assert detect_effective_date(articles, "25/03/2025") == "Kể từ ngày ký ban hành (25/03/2025)"


def test_decision_article_attached_phrase_is_not_appendix_leak():
    article = Article(
        number="1",
        title="Ban hành văn bản kèm theo",
        raw_content="Điều 1. Ban hành kèm theo Quyết định này Khung kiến trúc Chính phủ số Việt Nam, phiên bản 4.0.",
    )

    assert article_contains_appendix_marker(article) is False


def test_issuing_authority_prefers_signature_authority_without_normalizing():
    lines = [
        "CHÍNH PHỦ",
        "Số: 224/2026/NĐ-CP",
        "NGHỊ ĐỊNH",
        "Quy định chi tiết một số điều",
        "Căn cứ Luật Chuyển đổi số số 148/2025/QH15;",
    ]
    closing_lines = ["Nơi nhận:", "- Như trên;", "TM. CHÍNH PHỦ", "KT. THỦ TƯỚNG", "PHÓ THỦ TƯỚNG"]

    assert detect_issuing_authority(lines, "Nghị định", closing_lines) == "Chính phủ"


def test_issuing_authority_keeps_multiline_heading():
    lines = [
        "BỘ KHOA HỌC VÀ",
        "CÔNG NGHỆ",
        "Số: 01/2026/TT-BKHCN",
        "THÔNG TƯ",
        "Quy định về hồ sơ điện tử",
        "Căn cứ Luật Giao dịch điện tử;",
    ]

    assert detect_issuing_authority(lines, "Thông tư") == "Bộ Khoa học và Công nghệ"


def test_effective_date_uses_only_effective_article_not_legal_basis_dates():
    _, _, _, articles = parse_structure(
        [
            "Điều 1. Phạm vi điều chỉnh",
            "Căn cứ Luật số 148/2025/QH15 ngày 14 tháng 6 năm 2025.",
            "Điều 2. Trách nhiệm thi hành",
            "Bộ trưởng tổ chức thi hành văn bản này.",
            "Điều 3. Hiệu lực thi hành",
            "Thông tư này có hiệu lực thi hành từ ngày 15 tháng 8 năm 2026.",
        ]
    )

    assert detect_effective_date(articles) == "15/08/2026"


def test_issuing_authority_does_not_use_signer_title_for_circular():
    lines = [
        "BỘ KHOA HỌC VÀ CÔNG NGHỆ",
        "Số: 01/2026/TT-BKHCN",
        "THÔNG TƯ",
        "Quy định về hồ sơ điện tử",
        "Căn cứ Luật Giao dịch điện tử;",
    ]
    closing_lines = ["Nơi nhận:", "- Như trên;", "BỘ TRƯỞNG", "Nguyễn Văn A"]

    assert detect_issuing_authority(lines, "Thông tư", closing_lines) == "Bộ Khoa học và Công nghệ"


def test_applicable_subjects_are_normalized_list_not_raw_article():
    article = Article(
        number="2",
        title="Đối tượng áp dụng",
        raw_content=(
            "Điều 2. Đối tượng áp dụng\n"
            "Thông tư này áp dụng đối với cơ quan nhà nước; tổ chức cung cấp dịch vụ; cá nhân có liên quan."
        ),
    )

    result = detect_applicable_subjects([article])

    assert result == "- cơ quan nhà nước\n- tổ chức cung cấp dịch vụ\n- cá nhân có liên quan"
    assert "Điều 2" not in result


def test_metadata_scope_and_subjects_have_fallbacks():
    from app.document_processor import detect_scope

    articles = [
        Article(
            number="1",
            title="Quy định chung",
            raw_content="Điều 1. Quy định chung\nThông tư này quy định về hồ sơ điện tử của cơ quan, tổ chức, cá nhân.",
        )
    ]

    assert detect_scope(articles) == "Thông tư này quy định về hồ sơ điện tử của cơ quan, tổ chức, cá nhân."
    assert detect_applicable_subjects(articles) == "- Thông tư này quy định về hồ sơ điện tử của cơ quan, tổ chức, cá nhân"


def test_authority_name_is_normalized_to_official_casing():
    lines = [
        "bộ tài chính",
        "Số: 01/2026/TT-BTC",
        "THÔNG TƯ",
        "Quy định về quản lý tài chính",
        "Căn cứ Luật Ngân sách nhà nước;",
    ]

    assert detect_issuing_authority(lines, "Thông tư") == "Bộ Tài chính"


def test_validation_fails_when_issuing_authority_is_signer_title():
    from app.document_processor import ParsedDocument

    article = Article(number="1", title="Phạm vi điều chỉnh", raw_content="Điều 1. Phạm vi điều chỉnh\nNội dung.")
    parsed = ParsedDocument(
        file_name="test.docx",
        document_type="Thông tư",
        document_number="01/2026/TT-BKHCN",
        issued_date="01/01/2026",
        effective_date="",
        issuing_authority="BỘ TRƯỞNG",
        title="Quy định thử nghiệm",
        raw_text="",
        preamble="",
        legal_basis=[],
        scope="",
        applicable_subjects="",
        main_text="",
        appendix_text="",
        closing_text="",
        chapters=[],
        sections=[],
        subsections=[],
        articles=[article],
        appendices=[],
        definitions=[],
    )

    validation = validate_pack(parsed, build_article_knowledge(parsed))

    assert validation.status == "FAIL"
    assert any("chức danh người ký" in error for error in validation.errors)


def test_validation_fails_when_required_metadata_is_empty():
    from app.document_processor import ParsedDocument

    article = Article(number="1", title="Quy định chung", raw_content="Điều 1. Quy định chung\nNội dung.")
    parsed = ParsedDocument(
        file_name="test.docx",
        document_type="Thông tư",
        document_number="01/2026/TT-BTC",
        issued_date="01/01/2026",
        effective_date="",
        issuing_authority="Bộ Tài chính",
        title="Quy định thử nghiệm",
        raw_text="",
        preamble="",
        legal_basis=[],
        scope="",
        applicable_subjects="",
        main_text="",
        appendix_text="",
        closing_text="",
        chapters=[],
        sections=[],
        subsections=[],
        articles=[article],
        appendices=[],
        definitions=[],
    )

    validation = validate_pack(parsed, build_article_knowledge(parsed))

    assert validation.status == "FAIL"
    assert "Thiếu phạm vi điều chỉnh." in validation.errors
    assert "Thiếu đối tượng áp dụng." in validation.errors
