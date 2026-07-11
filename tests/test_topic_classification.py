from app.document_processor import Article
from app.knowledge_pack import infer_topics


def test_scope_article_does_not_get_indirect_topics_from_listed_scope():
    article = Article(
        number="1",
        title="Phạm vi điều chỉnh",
        raw_content=(
            "Điều 1. Phạm vi điều chỉnh\n"
            "Nghị định này quy định chi tiết Luật Chuyển đổi số, bao gồm: "
            "dịch vụ công trực tuyến; kiến trúc hệ thống số; dữ liệu và chia sẻ dữ liệu; "
            "an ninh mạng, bảo vệ dữ liệu cá nhân."
        ),
    )

    assert infer_topics(article) == ["Quy định chung"]


def test_topics_use_direct_article_content_not_related_law_mentions():
    article = Article(
        number="23",
        title="Quy định chi tiết về nguyên tắc kiến trúc và thiết kế hệ thống số",
        raw_content=(
            "Điều 23. Quy định chi tiết về nguyên tắc kiến trúc và thiết kế hệ thống số\n"
            "Các nguyên tắc kiến trúc và thiết kế tại Điều 7 của Luật Chuyển đổi số được quy định chi tiết như sau:\n"
            "1. Phải thiết kế hệ thống số theo hướng sử dụng nền tảng số dùng chung.\n"
            "2. Ưu tiên sử dụng hạ tầng điện toán đám mây khi thiết kế hệ thống số.\n"
            "3. Thiết kế hệ thống số phải hỗ trợ giao diện lập trình ứng dụng để chia sẻ dữ liệu.\n"
            "4. Bảo đảm an ninh mạng và bảo vệ dữ liệu cá nhân ngay từ giai đoạn thiết kế."
        ),
    )

    topics = infer_topics(article)

    assert "Kiến trúc hệ thống số" in topics
    assert "Thiết kế hệ thống số" in topics
    assert "Dữ liệu và chia sẻ dữ liệu" in topics
    assert "An ninh mạng, bảo vệ dữ liệu cá nhân" in topics
