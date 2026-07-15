import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import OUTPUT_DIR
from .document_processor import Appendix, Article, ParsedDocument, is_signer_title

logger = logging.getLogger(__name__)


COMMON_KEYWORDS = {
    "điều",
    "khoản",
    "điểm",
    "văn bản",
    "quy định",
    "cơ quan",
    "thông tin",
    "dữ liệu",
    "tổ chức",
    "cá nhân",
    "nội dung",
    "thực hiện",
    "yêu cầu",
    "phương pháp",
    "bảng",
}


LEGAL_TERM_CATALOG: list[tuple[str, str, tuple[str, ...]]] = [
    ("legal", "phạm vi điều chỉnh", ("phạm vi điều chỉnh", "phạm vi áp dụng")),
    ("legal", "đối tượng áp dụng", ("đối tượng áp dụng", "áp dụng đối với")),
    ("legal", "giải thích từ ngữ", ("giải thích từ ngữ", "được hiểu là")),
    ("legal", "căn cứ pháp lý", ("căn cứ luật", "căn cứ nghị định", "căn cứ thông tư", "theo đề nghị")),
    ("legal", "nguyên tắc kiến trúc", ("nguyên tắc kiến trúc", "nguyên tắc thiết kế")),
    ("legal", "thẩm quyền quyết định", ("thẩm quyền quyết định", "thẩm quyền phê duyệt", "quyết định đầu tư", "quyết định phê duyệt")),
    ("legal", "trách nhiệm tổ chức thực hiện", ("trách nhiệm tổ chức thực hiện", "tổ chức thực hiện", "chủ trì", "phối hợp")),
    ("legal", "quyền và nghĩa vụ", ("quyền", "nghĩa vụ")),
    ("legal", "điều kiện thực hiện", ("điều kiện thực hiện", "điều kiện bảo đảm", "đáp ứng điều kiện")),
    ("legal", "xử lý vi phạm", ("vi phạm", "xử lý vi phạm", "xử phạt")),
    ("legal", "hiệu lực thi hành", ("hiệu lực thi hành", "kể từ ngày")),
    ("legal", "quy định chuyển tiếp", ("chuyển tiếp", "tiếp tục thực hiện")),
    ("legal", "nguyên tắc tính đúng, tính đủ", ("tính đúng, tính đủ", "không trùng lặp")),
    ("legal", "pháp luật chuyên ngành", ("pháp luật chuyên ngành", "quy định của pháp luật chuyên ngành")),
    ("legal", "quản lý chi phí đầu tư ứng dụng công nghệ thông tin", ("quản lý chi phí đầu tư ứng dụng công nghệ thông tin", "lập và quản lý chi phí đầu tư")),
    ("business", "hồ sơ", ("hồ sơ", "thành phần hồ sơ", "tài liệu")),
    ("business", "trình tự thủ tục", ("trình tự", "thủ tục", "thời hạn", "tiếp nhận", "giải quyết")),
    ("business", "chi phí phần mềm nội bộ", ("chi phí phần mềm nội bộ", "chi phí trực tiếp xây dựng, phát triển, nâng cấp, mở rộng phần mềm nội bộ")),
    ("business", "xác định chi phí phần mềm nội bộ", ("xác định chi phí phần mềm nội bộ", "xác định chi phí trực tiếp xây dựng")),
    ("business", "hồ sơ xác định chi phí phần mềm nội bộ", ("hồ sơ phục vụ xác định chi phí phần mềm nội bộ", "hồ sơ xác định chi phí phần mềm nội bộ")),
    ("business", "trình tự xác định chi phí phần mềm nội bộ", ("trình tự xác định chi phí phần mềm nội bộ", "theo các bước, công việc chính")),
    ("business", "phương pháp tính chi phí phần mềm nội bộ", ("phương pháp tính chi phí phần mềm nội bộ", "nội suy", "mức lương lao động bình quân")),
    ("business", "bảng chi phí trực tiếp", ("bảng chi phí trực tiếp", "chi phí chung", "thu nhập chịu thuế tính trước")),
    ("business", "tác nhân", ("tác nhân", "actor", "actors")),
    ("business", "trường hợp sử dụng", ("trường hợp sử dụng", "use case")),
    ("business", "giao dịch", ("giao dịch", "transaction")),
    ("business", "yêu cầu chức năng", ("yêu cầu chức năng", "danh sách các yêu cầu chức năng")),
    ("business", "yêu cầu phi chức năng", ("yêu cầu phi chức năng", "độ phức tạp kỹ thuật - công nghệ")),
    ("business", "hệ số phức tạp kỹ thuật - công nghệ", ("hệ số phức tạp kỹ thuật - công nghệ", "tcf")),
    ("business", "hệ số tác động môi trường", ("hệ số tác động môi trường", "nhóm làm việc", "ef")),
    ("business", "kiểm thử phần mềm nội bộ", ("kiểm thử phần mềm nội bộ", "chi phí kiểm thử")),
    ("business", "dịch vụ công trực tuyến", ("dịch vụ công trực tuyến", "dịch vụ công")),
    ("business", "dịch vụ công trực tuyến chủ động", ("dịch vụ công trực tuyến chủ động",)),
    ("business", "cung cấp thông tin trên môi trường số", ("cung cấp thông tin", "môi trường số")),
    ("business", "mua sắm, thuê dịch vụ công nghệ số", ("mua sắm", "thuê dịch vụ công nghệ số", "dịch vụ công nghệ số")),
    ("business", "nhiệm vụ chi ngân sách nhà nước", ("ngân sách nhà nước", "nhiệm vụ chi", "chi thường xuyên", "chi đầu tư")),
    ("business", "phân cấp nhiệm vụ chi", ("phân cấp nhiệm vụ chi", "phân cấp ngân sách")),
    ("business", "kinh tế số", ("kinh tế số",)),
    ("business", "xã hội số", ("xã hội số",)),
    ("technology", "hệ thống số", ("hệ thống số",)),
    ("technology", "phần mềm nội bộ", ("phần mềm nội bộ",)),
    ("technology", "cơ sở dữ liệu", ("cơ sở dữ liệu", "tạo lập cơ sở dữ liệu")),
    ("technology", "thiết kế hệ thống số", ("thiết kế hệ thống số",)),
    ("technology", "kiến trúc hệ thống số", ("kiến trúc hệ thống số",)),
    ("technology", "kiến trúc nền tảng số", ("kiến trúc nền tảng số", "nền tảng số")),
    ("technology", "nền tảng số dùng chung", ("nền tảng số dùng chung",)),
    ("technology", "điện toán đám mây", ("điện toán đám mây", "cloud")),
    ("technology", "API", ("api", "giao diện lập trình ứng dụng")),
    ("technology", "chuẩn mở", ("chuẩn mở",)),
    ("technology", "kiến trúc mở", ("kiến trúc mở",)),
    ("technology", "dữ liệu chủ", ("dữ liệu chủ", "master data")),
    ("technology", "tích hợp, chia sẻ dữ liệu", ("tích hợp", "chia sẻ dữ liệu", "kết nối, chia sẻ")),
    ("technology", "an ninh mạng", ("an ninh mạng", "an toàn thông tin mạng")),
    ("technology", "bảo vệ dữ liệu cá nhân", ("bảo vệ dữ liệu cá nhân", "dữ liệu cá nhân")),
    ("state", "quản lý nhà nước", ("quản lý nhà nước",)),
    ("state", "phân cấp, phân quyền", ("phân cấp", "phân quyền", "ủy quyền")),
    ("state", "kiểm tra, thanh tra, giám sát", ("kiểm tra", "thanh tra", "giám sát", "theo dõi")),
    ("related", "Luật Chuyển đổi số", ("luật chuyển đổi số",)),
]


TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Quy định chung", ("phạm vi điều chỉnh", "đối tượng áp dụng", "giải thích từ ngữ")),
    ("Chiến lược, chương trình, kế hoạch chuyển đổi số", ("chiến lược", "chương trình", "kế hoạch chuyển đổi số")),
    ("Dịch vụ công trực tuyến", ("dịch vụ công trực tuyến",)),
    ("Dịch vụ công trực tuyến chủ động", ("dịch vụ công trực tuyến chủ động",)),
    ("Cung cấp thông tin trên môi trường số", ("cung cấp thông tin", "môi trường số")),
    ("Kiến trúc hệ thống số", ("kiến trúc hệ thống số", "nguyên tắc kiến trúc")),
    ("Kiến trúc nền tảng số", ("kiến trúc nền tảng số", "nền tảng số dùng chung")),
    ("Thiết kế hệ thống số", ("thiết kế hệ thống số",)),
    ("Dữ liệu và chia sẻ dữ liệu", ("chia sẻ dữ liệu", "dữ liệu chủ", "cơ sở dữ liệu", "tích hợp")),
    ("An ninh mạng, bảo vệ dữ liệu cá nhân", ("an ninh mạng", "an toàn thông tin", "bảo vệ dữ liệu cá nhân")),
    ("Đầu tư chuyển đổi số", ("đầu tư chuyển đổi số", "dự án đầu tư")),
    ("Mua sắm, thuê dịch vụ công nghệ số", ("mua sắm", "thuê dịch vụ công nghệ số", "dịch vụ công nghệ số")),
    ("Nhiệm vụ chi ngân sách nhà nước", ("ngân sách nhà nước", "nhiệm vụ chi", "chi thường xuyên", "chi đầu tư")),
    ("Phân cấp nhiệm vụ chi", ("phân cấp nhiệm vụ chi", "phân cấp ngân sách")),
    ("Kinh tế số", ("kinh tế số",)),
    ("Xã hội số", ("xã hội số",)),
    ("Trách nhiệm tổ chức thực hiện", ("trách nhiệm", "tổ chức thực hiện", "chủ trì", "phối hợp")),
    ("Hiệu lực thi hành", ("hiệu lực thi hành", "kể từ ngày")),
    ("Quy định chuyển tiếp", ("chuyển tiếp",)),
    ("Xác định chi phí phần mềm nội bộ", ("xác định chi phí phần mềm nội bộ", "chi phí phần mềm nội bộ")),
    ("Hồ sơ xác định chi phí phần mềm nội bộ", ("hồ sơ phục vụ xác định chi phí phần mềm nội bộ", "hồ sơ xác định chi phí")),
    ("Trình tự xác định chi phí phần mềm nội bộ", ("trình tự xác định chi phí phần mềm nội bộ", "theo các bước, công việc chính")),
    ("Phương pháp tính chi phí phần mềm nội bộ", ("phương pháp tính chi phí phần mềm nội bộ", "nội suy", "mức lương lao động bình quân")),
    ("Tác nhân, trường hợp sử dụng và giao dịch", ("tác nhân", "trường hợp sử dụng", "giao dịch", "actor", "use case", "transaction")),
    ("Hệ số kỹ thuật và môi trường", ("hệ số phức tạp kỹ thuật", "hệ số tác động môi trường", "nhóm làm việc")),
    ("Bảng tính chi phí phần mềm", ("bảng chi phí trực tiếp", "chi phí chung", "thu nhập chịu thuế tính trước")),
]

GENERIC_TOPIC_FALLBACKS = {"Nội dung chuyên ngành", "Quy định chung"}

GENERAL_PROVISION_TITLE_MARKERS = (
    "phạm vi điều chỉnh",
    "đối tượng áp dụng",
    "giải thích từ ngữ",
)

DIRECT_TOPIC_CONTEXT_MARKERS = (
    "quy định",
    "phải",
    "không được",
    "được",
    "bảo đảm",
    "ưu tiên",
    "xây dựng",
    "thiết kế",
    "cung cấp",
    "thực hiện",
    "sử dụng",
    "áp dụng",
    "xác định",
    "quản lý",
    "phê duyệt",
    "ban hành",
    "bố trí",
    "chi",
    "thuê",
    "mua sắm",
    "thu hồi",
    "đình chỉ",
)

INDIRECT_TOPIC_CONTEXT_MARKERS = (
    "bao gồm:",
    "bao gồm các",
    "theo quy định tại điều",
    "quy định chi tiết điều",
    "căn cứ",
    "luật chuyển đổi số",
    "luật ",
)


@dataclass
class ArticleKnowledge:
    article: Article
    topics: list[str]
    legal_keywords: list[str]
    business_keywords: list[str]
    technology_keywords: list[str]
    state_keywords: list[str]
    related_keywords: list[str]
    related_articles: list[Article] = field(default_factory=list)
    faqs: list[dict[str, str]] = field(default_factory=list)

    @property
    def all_keywords(self) -> list[str]:
        return prune_keywords(
            self.legal_keywords
            + self.business_keywords
            + self.technology_keywords
            + self.state_keywords
            + self.related_keywords
        )


@dataclass
class ValidationResult:
    status: str
    warnings: list[str]
    errors: list[str]
    faq_count: int
    keyword_count: int


@dataclass
class MergedMarkdownValidationResult:
    status: str
    warnings: list[str]
    errors: list[str]


def build_knowledge_pack(parsed: ParsedDocument, output_root: Path | None = None, emit_gpt_markdown: bool = True) -> Path:
    output_root = output_root or OUTPUT_DIR / "knowledge_packs"
    safe_number = document_folder_name(parsed)
    pack_dir = output_root / safe_number
    if pack_dir.exists():
        shutil.rmtree(pack_dir)

    articles_dir = pack_dir / "articles"
    appendices_dir = pack_dir / "appendices"
    indexes_dir = pack_dir / "indexes"
    for directory in (articles_dir, appendices_dir, indexes_dir):
        directory.mkdir(parents=True, exist_ok=True)

    logger.info("Building Knowledge Pack 1.0 at %s", pack_dir)
    article_knowledge = build_article_knowledge(parsed)
    validation = validate_pack(parsed, article_knowledge)

    write_text(pack_dir / "00_metadata.yaml", render_metadata(parsed, validation))
    write_text(pack_dir / "01_muc_luc.md", render_toc(parsed))
    write_text(pack_dir / "02_giai_thich_tu_ngu.md", render_definitions(parsed))
    write_text(pack_dir / "03_bang_tra_cuu.md", render_lookup(article_knowledge))
    write_text(pack_dir / "04_chu_de.md", render_topics(article_knowledge))
    write_text(pack_dir / "05_faq.md", render_faq(parsed, article_knowledge))
    write_text(pack_dir / "06_prompt_system.md", render_system_prompt(parsed))
    write_text(pack_dir / "07_noi_dung_goc.md", render_raw_text(parsed))
    write_text(pack_dir / "validation_report.md", render_validation_report(parsed, validation, article_knowledge))

    for index, knowledge in enumerate(article_knowledge, start=1):
        write_text(articles_dir / f"dieu_{index:03d}.md", render_article(knowledge, parsed))

    for index, appendix in enumerate(parsed.appendices, start=1):
        prefix = "mau_so" if appendix.kind == "mau_so" else "phu_luc"
        write_text(appendices_dir / f"{prefix}_{index:02d}.md", render_appendix(appendix))

    write_text(indexes_dir / "keyword_index.md", render_keyword_index(article_knowledge))
    write_text(indexes_dir / "topic_index.md", render_topic_index(article_knowledge))
    write_json(indexes_dir / "article_index.json", build_article_index(article_knowledge))
    write_json(indexes_dir / "citation_index.json", build_citation_index(article_knowledge))

    zip_path = shutil.make_archive(str(pack_dir), "zip", root_dir=pack_dir)
    if emit_gpt_markdown:
        merged_markdown = render_gpt_knowledge_markdown(parsed, article_knowledge)
        merged_validation = validate_merged_markdown(parsed, article_knowledge, merged_markdown)
        if merged_validation.status == "FAIL":
            logger.error("Merged Markdown validation failed: %s", "; ".join(merged_validation.errors))
            raise ValueError("Merged Markdown validation FAIL: " + "; ".join(merged_validation.errors))
        if merged_validation.warnings:
            logger.warning("Merged Markdown validation warnings: %s", "; ".join(merged_validation.warnings))
        write_text(output_root / gpt_knowledge_file_name(parsed), merged_markdown)
    logger.info("Knowledge Pack created: %s", zip_path)
    return Path(zip_path)


def write_text(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_metadata(parsed: ParsedDocument, validation: ValidationResult) -> str:
    legal_basis = "\n".join(f"  - \"{escape_yaml(item)}\"" for item in parsed.legal_basis)
    return f"""schema_version: "1.0"
source_file: "{escape_yaml(parsed.file_name)}"
document_type: "{parsed.document_type}"
document_number: "{escape_yaml(parsed.document_number)}"
issuing_authority: "{escape_yaml(parsed.issuing_authority)}"
issued_date: "{escape_yaml(parsed.issued_date)}"
effective_date: "{escape_yaml(parsed.effective_date)}"
title: "{escape_yaml(parsed.title)}"
legal_basis:
{legal_basis or "  []"}
scope: |
{yaml_block(parsed.scope)}
applicable_subjects: |
{yaml_block(parsed.applicable_subjects)}
recipients:
{yaml_list_block(parsed.recipients)}
signer: |
{yaml_block(parsed.signer)}
chapter_count: {len(parsed.chapters)}
section_count: {len(parsed.sections)}
subsection_count: {len(parsed.subsections)}
article_count: {len(parsed.articles)}
appendix_count: {len(parsed.appendices)}
appendix_status: "{'Có phụ lục/biểu mẫu' if parsed.appendices else 'Không phát hiện phụ lục'}"
validation_status: "{validation.status}"
generated_at: "{datetime.now().isoformat(timespec='seconds')}"
source_priority: "original_text"
privacy: "MVP xử lý cục bộ, không gửi dữ liệu ra ngoài."
"""


def render_gpt_knowledge_markdown(parsed: ParsedDocument, article_knowledge: list[ArticleKnowledge]) -> str:
    lines = [
        f"# {parsed.title}",
        "",
        "Tài liệu hợp nhất dùng để nạp vào Custom GPT. Nội dung gốc được đặt trước các phần tóm tắt, từ khóa và FAQ.",
        "",
        "## Metadata",
        "",
        f"- Loại văn bản: {parsed.document_type}",
        f"- Số/ký hiệu: {parsed.document_number}",
        f"- Cơ quan ban hành: {parsed.issuing_authority}",
        f"- Ngày ban hành: {parsed.issued_date}",
        f"- Hiệu lực: {parsed.effective_date or 'Không phát hiện trong văn bản'}",
        f"- Tên văn bản: {parsed.title}",
        f"- Số chương/mục lớn: {len(parsed.chapters)}",
        f"- Số điều/mục nội dung chính: {len(parsed.articles)}",
        f"- Số phụ lục/biểu mẫu: {len(parsed.appendices)}",
        "",
        "## Phạm vi điều chỉnh",
        "",
        parsed.scope or "Không phát hiện.",
        "",
        "## Đối tượng áp dụng",
        "",
        parsed.applicable_subjects or "Không phát hiện.",
        "",
        "## Căn cứ pháp lý",
        "",
    ]
    if parsed.legal_basis:
        lines.extend(f"- {item}" for item in parsed.legal_basis)
    else:
        lines.append("Không phát hiện căn cứ pháp lý riêng.")

    lines.extend(["", "## Mục lục", ""])
    lines.extend(render_toc_items(parsed))

    lines.extend(["", "## Giải thích từ ngữ", ""])
    if parsed.definitions:
        lines.extend(render_merged_definitions(parsed.definitions))
    else:
        lines.append("Không phát hiện điều khoản giải thích từ ngữ riêng trong văn bản.")

    lines.extend(
        [
            "",
            "## Nội dung gốc điều khoản",
            "",
            "Các nội dung dưới đây là nguồn ưu tiên cao nhất khi trả lời. Không suy luận vượt quá nội dung gốc.",
            "",
        ]
    )
    lines.extend(render_original_article_sections(article_knowledge))

    lines.extend(["", "## Phụ lục", ""])
    if parsed.appendices:
        for appendix in parsed.appendices:
            lines.extend(
                [
                    f"### {appendix_title(appendix)}",
                    "",
                    appendix.raw_content,
                    "",
                ]
            )
    else:
        lines.append("Không phát hiện phụ lục/biểu mẫu.")

    lines.extend(["", "## Bảng tra cứu", "", embed_markdown_section(render_lookup(article_knowledge), "Không phát hiện dữ liệu tra cứu."), ""])
    lines.extend(["", "## Chủ đề", "", embed_markdown_section(render_topics(article_knowledge), "Không phát hiện chủ đề đạt tiêu chí."), ""])
    lines.extend(["", "## Từ khóa", "", embed_markdown_section(render_keyword_index(article_knowledge), "Không phát hiện từ khóa đạt tiêu chí."), ""])
    lines.extend(["", "## Tóm tắt theo điều khoản", ""])
    for item in article_knowledge:
        article = item.article
        lines.extend(
            [
                f"### Tóm tắt {structure_label(article)} {article.number}",
                "",
                summarize(article.raw_content),
                "",
            ]
        )

    lines.extend(["", "## FAQ", ""])
    faqs = quality_checked_faqs(article_knowledge)
    if faqs:
        for faq in faqs:
            lines.extend(
                [
                    f"### {faq['question']}",
                    f"- Câu trả lời ngắn: {faq['answer']}",
                    f"- Căn cứ: {faq['citation']}",
                    f"- Mức độ chắc chắn: {faq['confidence']}",
                    f"- Ghi chú: {faq['note']}",
                    "",
                ]
            )
    else:
        lines.append("Không có FAQ đạt kiểm tra chất lượng.")
    return "\n".join(lines)


def render_merged_definitions(definitions: list[str]) -> list[str]:
    lines: list[str] = []
    for definition in definitions:
        cleaned_lines = []
        previous = ""
        for line in definition.splitlines():
            stripped = line.strip()
            if re.match(r"^Điều\s+\d+[a-zA-Z]?\.\s*", stripped, flags=re.IGNORECASE):
                if previous.lower() == stripped.lower():
                    continue
                previous = stripped
                continue
            cleaned_lines.append(line)
        cleaned = "\n".join(cleaned_lines).strip()
        if cleaned:
            lines.extend([cleaned, ""])
    return lines or ["Không phát hiện nội dung giải thích từ ngữ riêng ngoài điều khoản gốc."]


def render_original_article_sections(article_knowledge: list[ArticleKnowledge]) -> list[str]:
    lines: list[str] = []
    last_chapter = ""
    last_section = ""
    last_subsection = ""
    has_article_group = False
    for item in article_knowledge:
        article = item.article
        first_line = article.raw_content.splitlines()[0].strip() if article.raw_content else ""
        if article.chapter and article.chapter != last_chapter and article.chapter.strip() != first_line:
            lines.extend([f"### {article.chapter}", ""])
            last_chapter = article.chapter
            last_section = ""
            last_subsection = ""
            has_article_group = True
        if article.section and article.section != last_section:
            lines.extend([nested_structure_heading(article.section, under_chapter=bool(last_chapter)), ""])
            last_section = article.section
            last_subsection = ""
            has_article_group = True
        if article.subsection and article.subsection != last_subsection:
            lines.extend([nested_structure_heading(article.subsection, under_chapter=bool(last_chapter or last_section)), ""])
            last_subsection = article.subsection
            has_article_group = True
        label = structure_label(article)
        if label == "Điều" and not has_article_group:
            lines.extend(["### Điều khoản chính", ""])
            has_article_group = True
        heading_level = "####" if label == "Điều" else "###"
        lines.extend(
            [
                f"{heading_level} {label} {article.number}",
                "",
                article.raw_content,
                "",
            ]
        )
    return lines


def nested_structure_heading(title: str, under_chapter: bool) -> str:
    if under_chapter:
        return f"**{title}**"
    return f"### {title}"


def embed_markdown_section(markdown: str, fallback: str) -> str:
    lines = markdown.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.match(r"^#{1,2}\s+", lines[0]):
        lines.pop(0)
    output: list[str] = []
    for line in lines:
        heading_match = re.match(r"^(#{1,5})\s+(.+)$", line)
        if heading_match:
            level = min(len(heading_match.group(1)) + 1, 6)
            output.append(f"{'#' * level} {heading_match.group(2)}")
        else:
            output.append(line)
    return "\n".join(output).strip() or fallback


def structure_label(article: Article) -> str:
    first_line = article.raw_content.splitlines()[0].strip() if article.raw_content else ""
    if re.match(r"^Điều\s+", first_line, flags=re.IGNORECASE):
        return "Điều"
    if re.match(r"^Mục\s+", first_line, flags=re.IGNORECASE):
        return "Mục"
    if re.match(r"^Chương\s+", first_line, flags=re.IGNORECASE):
        return "Chương"
    if re.match(r"^Phần\s+", first_line, flags=re.IGNORECASE):
        return "Phần"
    if re.match(r"^[IVXLCDM]+\s*[-–]\s+", first_line, flags=re.IGNORECASE):
        return "Mục"
    return "Điều"


def render_toc_items(parsed: ParsedDocument) -> list[str]:
    lines: list[str] = []
    for chapter in parsed.chapters:
        lines.append(f"- {chapter}")
    for section in parsed.sections:
        lines.append(f"  - {section}")
    for subsection in parsed.subsections:
        lines.append(f"    - {subsection}")
    for article in parsed.articles:
        lines.append(f"- {structure_label(article)} {article.number}. {article.title}")
    if parsed.appendices:
        lines.append("- Phụ lục, biểu mẫu")
        lines.extend(f"  - {appendix_title(appendix)}" for appendix in parsed.appendices)
    return lines or ["Không phát hiện mục lục."]


def render_toc(parsed: ParsedDocument) -> str:
    lines = [f"# Mục lục - {parsed.title}", ""]
    for chapter in parsed.chapters:
        lines.append(f"- {chapter}")
    for section in parsed.sections:
        lines.append(f"  - {section}")
    for subsection in parsed.subsections:
        lines.append(f"    - {subsection}")
    lines.append("")
    for article in parsed.articles:
        lines.append(f"- Điều {article.number}. {article.title}")
    if parsed.appendices:
        lines.extend(["", "## Phụ lục, biểu mẫu"])
        for appendix in parsed.appendices:
            lines.append(f"- {appendix_title(appendix)}")
    return "\n".join(lines)


def render_definitions(parsed: ParsedDocument) -> str:
    lines = ["# Giải thích từ ngữ", ""]
    if not parsed.definitions:
        lines.append("Không phát hiện điều khoản giải thích từ ngữ riêng trong văn bản.")
    else:
        for item in parsed.definitions:
            lines.extend([item, ""])
    return "\n".join(lines)


def render_lookup(article_knowledge: list[ArticleKnowledge]) -> str:
    lines = [
        "# Bảng tra cứu",
        "",
        "| Điều | Tên điều | Chương | Mục | Chủ đề | Từ khóa |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in article_knowledge:
        article = item.article
        lines.append(
            f"| {article.number} | {article.title or 'Không có tiêu đề'} | "
            f"{article.chapter or ''} | {article.section or ''} | "
            f"{', '.join(item.topics)} | {', '.join(item.all_keywords)} |"
        )
    return "\n".join(lines)


def render_topics(article_knowledge: list[ArticleKnowledge]) -> str:
    topic_map: dict[str, list[Article]] = {}
    for item in article_knowledge:
        for topic in item.topics:
            topic_map.setdefault(topic, []).append(item.article)

    lines = ["# Chủ đề", ""]
    for topic, articles in sorted(topic_map.items()):
        lines.append(f"## {topic}")
        for article in articles:
            lines.append(f"- Điều {article.number}. {article.title}")
        lines.append("")
    return "\n".join(lines)


def render_faq(parsed: ParsedDocument, article_knowledge: list[ArticleKnowledge]) -> str:
    lines = ["# FAQ", "", "## FAQ theo tình huống nghiệp vụ", ""]
    for topic, items in group_knowledge_by_topic(article_knowledge).items():
        article_refs = ", ".join(f"Điều {item.article.number}" for item in items[:12])
        lines.extend(
            [
                f"### Khi xử lý nghiệp vụ về {topic.lower()}, cần tra cứu điều khoản nào?",
                f"- Câu trả lời ngắn: Cần tra cứu {article_refs}.",
                f"- Căn cứ: {article_refs}.",
                "- Mức độ chắc chắn: Trung bình đến cao, tùy mức độ trực tiếp của nội dung gốc.",
                "- Ghi chú: Không suy luận vượt quá nội dung văn bản; cần đối chiếu thêm văn bản liên quan nếu câu hỏi yêu cầu căn cứ ngoài Knowledge Pack.",
                "",
            ]
        )

    lines.extend(["## FAQ phục vụ tra cứu pháp lý", ""])
    for item in article_knowledge:
        for faq in item.faqs:
            lines.extend(
                [
                    f"### {faq['question']}",
                    f"- Câu trả lời ngắn: {faq['answer']}",
                    f"- Căn cứ: {faq['citation']}",
                    f"- Mức độ chắc chắn: {faq['confidence']}",
                    f"- Ghi chú: {faq['note']}",
                    "",
                ]
            )

    lines.extend(["## FAQ theo điều khoản", ""])
    for item in article_knowledge:
        article = item.article
        lines.extend(
            [
                f"### Điều {article.number}. {article.title or 'Không có tiêu đề'} quy định nội dung gì?",
                f"- Câu trả lời ngắn: {summarize(article.raw_content)}",
                f"- Căn cứ: Điều {article.number}.",
                "- Mức độ chắc chắn: Cao.",
                "- Ghi chú: Câu trả lời chỉ tóm tắt nội dung gốc của điều này.",
                "",
            ]
        )
    return "\n".join(lines)


def render_system_prompt(parsed: ParsedDocument) -> str:
    return f"""# System Prompt cho Custom GPT

Bạn là trợ lý pháp lý tra cứu nội dung từ Legal Knowledge Pack 1.0 của văn bản: {parsed.title}.

Quy tắc bắt buộc:
- Chỉ trả lời khi có căn cứ trực tiếp trong Knowledge Pack.
- Khi trả lời pháp lý phải nêu rõ Điều/Khoản/Điểm nếu có.
- Không suy luận, không đoán ý, không bổ sung điều kiện hoặc nghĩa vụ nếu nội dung gốc không nêu.
- Không được suy luận từ từ khóa, tiêu đề hoặc FAQ nếu nội dung gốc không có căn cứ.
- Thứ tự ưu tiên nguồn bắt buộc: Nội dung gốc trong `07_noi_dung_goc.md` và `articles/dieu_*.md` > điều khoản đã tách > metadata > tóm tắt > FAQ > từ khóa.
- Nếu FAQ hoặc tóm tắt mâu thuẫn với nội dung gốc thì phải ưu tiên nội dung gốc.
- Không được coi phụ lục, biểu mẫu, bảng, mẫu quyết định, mẫu tờ khai hoặc nội dung trong `appendices/` là điều khoản chính của văn bản.
- Khi người dùng hỏi về điều khoản chính, chỉ sử dụng các file trong `articles/`; chỉ dùng `appendices/` khi câu hỏi nêu rõ phụ lục, biểu mẫu hoặc mẫu tương ứng.
- Không được trích phụ lục để tạo nghĩa vụ pháp lý chính nếu điều khoản chính không nêu nghĩa vụ đó.
- Không được tự xác định văn bản hết hiệu lực, bị thay thế, bị sửa đổi nếu metadata hoặc nội dung gốc không nêu.
- Nếu không tìm thấy căn cứ thì trả lời đúng câu: “Chưa có căn cứ trực tiếp trong văn bản được nạp.”
- Không được tự thêm quy định từ văn bản khác nếu văn bản đó chưa được nạp.
- Khi cần viện dẫn văn bản khác, phải nói rõ: “Cần đối chiếu thêm văn bản liên quan.”
- Đây là công cụ hỗ trợ tra cứu, không thay thế tư vấn pháp lý chuyên nghiệp.
"""


def render_raw_text(parsed: ParsedDocument) -> str:
    return f"""# Nội dung gốc - {parsed.title}

```text
{parsed.raw_text}
```
"""


def render_appendix(appendix: Appendix) -> str:
    return f"""# {appendix_title(appendix)}

## Loại nội dung
Phụ lục/biểu mẫu kèm theo văn bản. Đây không phải là điều khoản chính.

## Nội dung gốc
{appendix.raw_content}
"""


def render_article(item: ArticleKnowledge, parsed: ParsedDocument) -> str:
    article = item.article
    related = item.related_articles
    front_matter = f"""---
document_number: "{escape_yaml(parsed.document_number)}"
document_type: "{parsed.document_type}"
article_number: "{article.number}"
article_title: "{escape_yaml(article.title)}"
chapter: "{escape_yaml(article.chapter)}"
section: "{escape_yaml(article.section)}"
topics: [{yaml_list(item.topics)}]
legal_keywords: [{yaml_list(item.legal_keywords)}]
business_keywords: [{yaml_list(item.business_keywords)}]
technology_keywords: [{yaml_list(item.technology_keywords)}]
related_articles: [{yaml_list([f"Điều {related_article.number}" for related_article in related])}]
source_priority: original_text
---
"""
    return f"""{front_matter}
# Điều {article.number}. {article.title or 'Không có tiêu đề'}

## Nội dung gốc
{article.raw_content}

## Cấu trúc điều khoản
{render_clause_structure(article)}

## Tóm tắt pháp lý
{summarize(article.raw_content)}

## Từ khóa
- Pháp lý: {', '.join(item.legal_keywords) or 'Chưa xác định'}
- Nghiệp vụ: {', '.join(item.business_keywords) or 'Chưa xác định'}
- Công nghệ: {', '.join(item.technology_keywords) or 'Không phát hiện'}
- Quản lý nhà nước: {', '.join(item.state_keywords) or 'Không phát hiện'}
- Liên kết văn bản khác: {', '.join(item.related_keywords) or 'Không phát hiện'}

## FAQ liên quan
{render_article_faq(item)}

## Ghi chú kiểm soát
{control_note(item)}
"""


def render_clause_structure(article: Article) -> str:
    lines: list[str] = []
    if not article.clauses and not article.points:
        return "Không phát hiện khoản/điểm riêng; xem toàn văn tại mục Nội dung gốc."
    if article.clauses:
        lines.append("### Khoản")
        lines.extend(f"- {clause}" for clause in article.clauses)
    if article.points:
        lines.append("### Điểm")
        lines.extend(f"- {point}" for point in article.points)
    return "\n".join(lines)


def render_article_faq(item: ArticleKnowledge) -> str:
    lines: list[str] = []
    for faq in item.faqs:
        lines.extend(
            [
                f"### {faq['question']}",
                f"- Câu trả lời ngắn: {faq['answer']}",
                f"- Căn cứ: {faq['citation']}",
                f"- Mức độ chắc chắn: {faq['confidence']}",
                f"- Ghi chú: {faq['note']}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def render_validation_report(
    parsed: ParsedDocument,
    validation: ValidationResult,
    article_knowledge: list[ArticleKnowledge],
) -> str:
    duplicate_numbers = find_duplicates([item.article.number for item in article_knowledge])
    expected_numbers = expected_article_numbers([item.article.number for item in article_knowledge])
    actual_numbers = {item.article.number for item in article_knowledge}
    missing_numbers = [number for number in expected_numbers if number not in actual_numbers]
    lines = [
        "# Validation Report",
        "",
        f"- Kết luận: {validation.status}",
        f"- Metadata đủ: {'Có' if metadata_complete(parsed) else 'Không'}",
        f"- Số điều chính thức: {len(parsed.articles)}",
        f"- Số file trong articles/: {len(article_knowledge)}",
        f"- Điều trùng: {', '.join(duplicate_numbers) if duplicate_numbers else 'Không'}",
        f"- Điều thiếu: {', '.join(missing_numbers) if missing_numbers else 'Không phát hiện'}",
        f"- Có điều phụ lục bị nhầm vào articles/: {'Có' if appendix_article_leak(parsed) else 'Không'}",
        f"- Số phụ lục: {len(parsed.appendices)}",
        f"- Số FAQ: {validation.faq_count}",
        f"- Số từ khóa: {validation.keyword_count}",
        "",
        "## Cảnh báo",
    ]
    lines.extend(f"- {warning}" for warning in validation.warnings)
    if not validation.warnings:
        lines.append("- Không có.")
    lines.extend(["", "## Lỗi"])
    lines.extend(f"- {error}" for error in validation.errors)
    if not validation.errors:
        lines.append("- Không có.")
    return "\n".join(lines)


def render_keyword_index(article_knowledge: list[ArticleKnowledge]) -> str:
    index: dict[str, list[str]] = {}
    for item in article_knowledge:
        for keyword in item.all_keywords:
            index.setdefault(keyword, []).append(f"Điều {item.article.number}")
    lines = ["# Keyword Index", ""]
    for keyword, articles in sorted(index.items()):
        lines.append(f"- **{keyword}**: {', '.join(unique(articles))}")
    return "\n".join(lines)


def render_topic_index(article_knowledge: list[ArticleKnowledge]) -> str:
    lines = ["# Topic Index", ""]
    for topic, items in group_knowledge_by_topic(article_knowledge).items():
        lines.append(f"## {topic}")
        lines.extend(f"- Điều {item.article.number}. {item.article.title}" for item in items)
        lines.append("")
    return "\n".join(lines)


def build_article_index(article_knowledge: list[ArticleKnowledge]) -> list[dict[str, object]]:
    return [
        {
            "article_number": item.article.number,
            "article_title": item.article.title,
            "chapter": item.article.chapter,
            "section": item.article.section,
            "topics": item.topics,
            "keywords": item.all_keywords,
        }
        for item in article_knowledge
    ]


def build_citation_index(article_knowledge: list[ArticleKnowledge]) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    for item in article_knowledge:
        citations.append(
            {
                "citation": f"Điều {item.article.number}",
                "article_title": item.article.title,
                "clauses": item.article.clauses,
                "points": item.article.points,
            }
        )
    return citations


def build_article_knowledge(parsed: ParsedDocument) -> list[ArticleKnowledge]:
    items: list[ArticleKnowledge] = []
    for article in parsed.articles:
        keyword_groups = extract_keyword_groups(article.raw_content)
        topics = infer_topics(article)
        item = ArticleKnowledge(
            article=article,
            topics=topics,
            legal_keywords=keyword_groups["legal"],
            business_keywords=keyword_groups["business"],
            technology_keywords=keyword_groups["technology"],
            state_keywords=keyword_groups["state"],
            related_keywords=keyword_groups["related"],
        )
        item.related_articles = find_related_articles(article, parsed.articles)
        item.faqs = build_article_faqs(item)
        items.append(item)
    return items


def extract_keyword_groups(text: str) -> dict[str, list[str]]:
    lowered = text.lower()
    groups = {"legal": [], "business": [], "technology": [], "state": [], "related": []}
    for group, term, markers in LEGAL_TERM_CATALOG:
        if any(marker.lower() in lowered for marker in markers):
            groups[group].append(term)
    for phrase in extract_domain_phrases(text):
        target = "business" if any(marker in phrase for marker in ("chi phí", "hồ sơ", "trình tự", "hệ số", "bảng")) else "technology"
        groups[target].append(phrase)
    for key in groups:
        groups[key] = prune_keywords([term for term in unique(groups[key]) if term not in COMMON_KEYWORDS])
    return groups


def extract_domain_phrases(text: str) -> list[str]:
    lowered = text.lower()
    patterns = (
        r"(chi phí phần mềm nội bộ)",
        r"(hồ sơ (?:phục vụ )?xác định chi phí phần mềm nội bộ)",
        r"(trình tự xác định chi phí phần mềm nội bộ)",
        r"(phương pháp tính chi phí phần mềm nội bộ)",
        r"(bảng [^.\n;:]{0,80}?(?:phần mềm nội bộ|tác nhân|trường hợp sử dụng|chi phí trực tiếp))",
        r"(hệ số [^.\n;:]{0,80}?(?:kỹ thuật|môi trường|nhóm làm việc))",
        r"(trường hợp sử dụng)",
        r"(yêu cầu (?:chức năng|phi chức năng))",
        r"(mức lương lao động bình quân)",
    )
    phrases: list[str] = []
    for pattern in patterns:
        phrases.extend(match.group(1).strip(" .;:") for match in re.finditer(pattern, lowered))
    return unique([phrase for phrase in phrases if 6 <= len(phrase) <= 120])


def prune_keywords(keywords: list[str]) -> list[str]:
    normalized_keywords = unique([normalize_keyword(keyword) for keyword in keywords if normalize_keyword(keyword)])
    ordered = sorted(normalized_keywords, key=lambda item: (-len(item), item))
    selected: list[str] = []
    for keyword in ordered:
        if any(keyword != other and keyword in other for other in selected):
            continue
        selected.append(keyword)
    return sorted(selected)


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword.replace("\xa0", " ")).strip(" .;:,").lower()


def infer_topics(article: Article) -> list[str]:
    title_text = article.title.lower()
    if any(marker in title_text for marker in GENERAL_PROVISION_TITLE_MARKERS):
        return ["Quy định chung"]

    scored: dict[str, int] = {}
    for topic, markers in TOPIC_RULES:
        title_score = sum(title_text.count(marker.lower()) for marker in markers)
        if title_score:
            scored[topic] = scored.get(topic, 0) + title_score * 3

    for context in direct_topic_contexts(article.raw_content):
        for topic, markers in TOPIC_RULES:
            score = sum(context.count(marker.lower()) for marker in markers)
            if score:
                scored[topic] = scored.get(topic, 0) + score

    if not scored:
        return ["Quy định chung"] if article.number in {"1", "2"} else ["Nội dung chuyên ngành"]
    ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    topics = [topic for topic, _ in ranked[:5]]
    specific_topics = [topic for topic in topics if topic not in GENERIC_TOPIC_FALLBACKS]
    if specific_topics:
        topics = specific_topics
    return topics[:4]


def direct_topic_contexts(text: str) -> list[str]:
    contexts: list[str] = []
    for raw_context in re.split(r"(?<=[.;:])\s+|\n+", text):
        context = raw_context.strip().lower()
        if not context:
            continue
        if is_indirect_topic_context(context):
            continue
        if any(marker in context for marker in DIRECT_TOPIC_CONTEXT_MARKERS):
            contexts.append(context)
    return contexts


def is_indirect_topic_context(context: str) -> bool:
    if context.startswith(("căn cứ ", "theo đề nghị", "xét đề nghị")):
        return True
    if "bao gồm:" in context:
        return True
    if "luật chuyển đổi số" in context and not any(
        direct in context
        for direct in (
            "phải",
            "không được",
            "bảo đảm",
            "ưu tiên",
            "xây dựng",
            "thiết kế",
            "cung cấp",
            "thực hiện",
            "sử dụng",
            "áp dụng",
        )
    ):
        return True
    return any(marker in context for marker in INDIRECT_TOPIC_CONTEXT_MARKERS[:4])


def build_article_faqs(item: ArticleKnowledge) -> list[dict[str, str]]:
    article = item.article
    topics = ", ".join(item.topics).lower()
    keywords = item.all_keywords
    primary_keyword = keywords[0] if keywords else (article.title or f"Điều {article.number}")
    citation = f"Điều {article.number}"
    if article.clauses:
        citation += ", khoản 1"
    faqs = [
        {
            "question": f"Điều này quy định nội dung gì về {article.title or primary_keyword}?",
            "answer": summarize(article.raw_content),
            "citation": citation,
            "confidence": "Cao",
            "note": "Tóm tắt trực tiếp từ nội dung gốc; không mở rộng nghĩa.",
        },
        {
            "question": f"Đối tượng hoặc cơ quan nào phải lưu ý khi áp dụng {primary_keyword}?",
            "answer": "Chỉ xác định theo chủ thể được nêu trong nội dung gốc của điều này.",
            "citation": f"Điều {article.number}",
            "confidence": "Trung bình",
            "note": "Nếu điều không nêu rõ chủ thể thì không được tự suy luận.",
        },
        {
            "question": f"Căn cứ nào quy định về {primary_keyword}?",
            "answer": f"Căn cứ trực tiếp nằm tại Điều {article.number}.",
            "citation": f"Điều {article.number}",
            "confidence": "Cao",
            "note": "Cần đối chiếu thêm văn bản liên quan nếu câu hỏi yêu cầu căn cứ ngoài văn bản được nạp.",
        },
    ]
    if "điện toán đám mây" in keywords:
        faqs.append(
            {
                "question": "Có bắt buộc ưu tiên điện toán đám mây khi thiết kế hệ thống số không?",
                "answer": "Chỉ trả lời theo nội dung gốc của điều có nhắc đến điện toán đám mây.",
                "citation": f"Điều {article.number}",
                "confidence": "Trung bình",
                "note": "Không suy luận thành nghĩa vụ bắt buộc nếu điều khoản không nêu rõ.",
            }
        )
    if "mua sắm, thuê dịch vụ công nghệ số" in keywords:
        faqs.append(
            {
                "question": "Khi nào được thuê dịch vụ công nghệ số?",
                "answer": "Tra cứu điều này và chỉ kết luận khi nội dung gốc nêu điều kiện hoặc trường hợp thuê.",
                "citation": f"Điều {article.number}",
                "confidence": "Trung bình",
                "note": "Không bổ sung điều kiện từ văn bản khác nếu chưa được nạp.",
            }
        )
    if "nhiệm vụ chi ngân sách nhà nước" in keywords:
        faqs.append(
            {
                "question": "Nhiệm vụ chi thường xuyên cho chuyển đổi số gồm những nội dung nào?",
                "answer": "Chỉ liệt kê các nội dung được nêu trực tiếp trong điều khoản.",
                "citation": f"Điều {article.number}",
                "confidence": "Trung bình",
                "note": "Cần đối chiếu thêm văn bản ngân sách nếu cần căn cứ ngoài Knowledge Pack.",
            }
        )
    if not topics:
        faqs.append(
            {
                "question": f"Khi tra cứu Điều {article.number}, cần kiểm tra gì?",
                "answer": "Kiểm tra nội dung gốc, khoản, điểm và điều liên quan nếu có.",
                "citation": f"Điều {article.number}",
                "confidence": "Cao",
                "note": "Không suy luận từ từ khóa.",
            }
        )
    return faqs


def quality_checked_faqs(article_knowledge: list[ArticleKnowledge]) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    seen: set[str] = set()
    article_by_number = {item.article.number: item.article for item in article_knowledge}
    for item in article_knowledge:
        for faq in item.faqs:
            question = faq.get("question", "").strip()
            normalized_question = normalize_for_compare(question)
            if not question or normalized_question in seen:
                continue
            if is_generic_faq_question(question):
                continue
            if not faq_has_direct_basis(faq, item.article, article_by_number):
                continue
            accepted.append(faq)
            seen.add(normalized_question)
    return accepted


def faq_has_direct_basis(faq: dict[str, str], article: Article, article_by_number: dict[str, Article]) -> bool:
    citation = faq.get("citation", "")
    refs = re.findall(r"Điều\s+(\d+[a-zA-Z]?|[IVXLCDM]+)", citation, flags=re.IGNORECASE)
    if not refs:
        return False
    if article.number not in refs:
        return False
    source_text = " ".join(article_by_number.get(ref, article).raw_content for ref in refs)
    combined = " ".join([faq.get("question", ""), faq.get("answer", ""), faq.get("note", "")]).lower()
    if "nội dung gốc" in combined or "không suy luận" in combined or "chỉ xác định" in combined:
        return True
    keywords = [keyword.lower() for keyword in extract_keyword_groups(source_text).get("legal", [])]
    keywords.extend(keyword.lower() for keyword in extract_keyword_groups(source_text).get("business", []))
    return any(keyword and keyword in source_text.lower() and keyword in combined for keyword in keywords)


def is_generic_faq_question(question: str) -> bool:
    normalized = normalize_for_compare(question)
    generic_patterns = (
        r"^dieu nay quy dinh gi$",
        r"^dieu \d+ quy dinh gi$",
        r"^dieu \d+ quy dinh noi dung gi$",
    )
    return any(re.match(pattern, normalized) for pattern in generic_patterns)


def validate_merged_markdown(
    parsed: ParsedDocument,
    article_knowledge: list[ArticleKnowledge],
    markdown: str,
) -> MergedMarkdownValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    headings = markdown_headings(markdown)

    if "Điều/Mục" in markdown:
        errors.append("File hợp nhất còn nhãn cấm 'Điều/Mục'.")
    if repeated_headings(headings):
        warnings.append("Có heading bị lặp trong file hợp nhất.")
    if heading_level_errors(headings):
        errors.append("Heading Markdown sai cấp hoặc có H1 bên trong nội dung.")
    if duplicate_article_headings(markdown):
        errors.append("Tiêu đề Điều bị lặp trong file hợp nhất.")
    if normalize_for_compare(parsed.scope) and normalize_for_compare(parsed.scope) == normalize_for_compare(parsed.applicable_subjects):
        errors.append("scope và applicable_subjects bị trùng nhau.")
    if empty_sections(markdown):
        errors.append("Có section rỗng trong file hợp nhất.")
    if article_content_missing(article_knowledge, markdown):
        errors.append("Mất nội dung gốc của điều khoản trong file hợp nhất.")
    if article_order_errors(parsed.articles, markdown):
        errors.append("Thứ tự Điều trong file hợp nhất bị sai.")
    if appendix_mixed_into_main(article_knowledge):
        errors.append("Phụ lục/biểu mẫu bị lẫn vào nội dung điều khoản chính.")

    faqs = quality_checked_faqs(article_knowledge)
    questions = [normalize_for_compare(faq["question"]) for faq in faqs]
    if find_duplicates(questions):
        errors.append("FAQ trùng trong file hợp nhất.")
    if any(is_generic_faq_question(faq["question"]) for faq in faqs):
        errors.append("FAQ generic trong file hợp nhất.")
    if not faqs and article_knowledge:
        warnings.append("Không có FAQ đạt kiểm tra chất lượng để đưa vào file hợp nhất.")

    status = "FAIL" if errors else "WARNING" if warnings else "PASS"
    return MergedMarkdownValidationResult(status=status, warnings=unique(warnings), errors=unique(errors))


def markdown_headings(markdown: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    for line in markdown.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            headings.append((len(match.group(1)), match.group(2).strip()))
    return headings


def repeated_headings(headings: list[tuple[int, str]]) -> list[str]:
    return find_duplicates([f"{level}:{title}" for level, title in headings])


def heading_level_errors(headings: list[tuple[int, str]]) -> list[str]:
    errors: list[str] = []
    if not headings or headings[0][0] != 1:
        errors.append("Heading đầu tiên không phải H1.")
    for index, (level, title) in enumerate(headings[1:], start=1):
        previous_level = headings[index - 1][0]
        if level == 1:
            errors.append(f"H1 lặp bên trong tài liệu: {title}")
        if level - previous_level > 1:
            errors.append(f"Heading nhảy cấp: {title}")
    return errors


def duplicate_article_headings(markdown: str) -> list[str]:
    article_headings = []
    for level, title in markdown_headings(markdown):
        if level <= 4 and re.match(r"^Điều\s+\d+[a-zA-Z]?\.", title, flags=re.IGNORECASE):
            article_headings.append(title.lower())
    return find_duplicates(article_headings)


def empty_sections(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    empty: list[str] = []
    for index, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not heading:
            continue
        current_level = len(heading.group(1))
        content_found = False
        for next_line in lines[index + 1 :]:
            next_heading = re.match(r"^(#{1,6})\s+", next_line)
            if next_heading and len(next_heading.group(1)) > current_level:
                content_found = True
                break
            if next_heading:
                break
            if next_line.strip():
                content_found = True
                break
        if not content_found:
            empty.append(heading.group(2))
    return empty


def article_content_missing(article_knowledge: list[ArticleKnowledge], markdown: str) -> list[str]:
    missing: list[str] = []
    for item in article_knowledge:
        if item.article.raw_content.strip() not in markdown:
            missing.append(item.article.number)
    return missing


def article_order_errors(articles: list[Article], markdown: str) -> bool:
    positions: list[int] = []
    for article in articles:
        marker = article.raw_content.splitlines()[0].strip()
        position = markdown.find(marker)
        if position == -1:
            return True
        positions.append(position)
    return positions != sorted(positions)


def appendix_mixed_into_main(article_knowledge: list[ArticleKnowledge]) -> bool:
    return any(article_contains_appendix_marker(item.article) for item in article_knowledge)


def normalize_for_compare(value: str) -> str:
    value = value.lower()
    replacements = str.maketrans(
        "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ",
        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd",
    )
    value = value.translate(replacements)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def validate_pack(parsed: ParsedDocument, article_knowledge: list[ArticleKnowledge]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(parsed.warnings)
    faq_count = sum(len(item.faqs) for item in article_knowledge) + len(group_knowledge_by_topic(article_knowledge))
    keyword_count = sum(len(item.all_keywords) for item in article_knowledge)

    if not parsed.document_type:
        errors.append("Thiếu loại văn bản.")
    if not parsed.document_number:
        errors.append("Thiếu số/ký hiệu văn bản.")
    if not parsed.issued_date:
        errors.append("Thiếu ngày ban hành.")
    if not parsed.effective_date:
        warnings.append("Chưa phát hiện ngày hoặc thời điểm hiệu lực.")
    if not parsed.issuing_authority:
        errors.append("Thiếu cơ quan ban hành.")
    elif is_signer_title(parsed.issuing_authority):
        errors.append("Cơ quan ban hành không hợp lệ: đang là chức danh người ký, không phải tên cơ quan.")
    if not parsed.title:
        errors.append("Thiếu tên văn bản.")
    if not parsed.scope:
        errors.append("Thiếu phạm vi điều chỉnh.")
    if not parsed.applicable_subjects:
        errors.append("Thiếu đối tượng áp dụng.")
    if len(parsed.articles) != len(article_knowledge):
        errors.append("Số articles khác số điều chính.")
    duplicate_numbers = find_duplicates([article.number for article in parsed.articles])
    if duplicate_numbers:
        errors.append(f"Điều bị trùng số: {', '.join(duplicate_numbers)}.")
    missing_numbers = missing_article_numbers(parsed.articles)
    if missing_numbers:
        errors.append(f"Thiếu điều trong chuỗi số: {', '.join(missing_numbers)}.")
    if appendix_article_leak(parsed):
        errors.append("Phát hiện điều phụ lục có nguy cơ bị nhầm vào articles/.")
    for article in parsed.articles:
        if article_has_orphan_point(article):
            errors.append(f"Điều {article.number} có Điểm không thuộc Khoản.")
        if article_contains_structure_heading(article):
            errors.append(f"Điều {article.number} chứa tiêu đề Chương/Mục bên trong nội dung điều.")
        if article_contains_appendix_marker(article):
            errors.append(f"Điều {article.number} có dấu hiệu lẫn nội dung phụ lục/biểu mẫu.")
        if article_contains_closing_marker(article):
            errors.append(f"Điều {article.number} có dấu hiệu lẫn phần nơi nhận/người ký.")
    if has_generic_faqs(article_knowledge):
        warnings.append("FAQ còn có câu hỏi chung, cần rà lại nếu dùng cho nghiệp vụ chuyên sâu.")
    if has_common_keywords(article_knowledge):
        warnings.append("Từ khóa chứa từ phổ thông, cần rà catalogue thuật ngữ.")

    status = "FAIL" if errors else "WARNING" if warnings else "PASS"
    return ValidationResult(status=status, warnings=unique(warnings), errors=unique(errors), faq_count=faq_count, keyword_count=keyword_count)


def metadata_complete(parsed: ParsedDocument) -> bool:
    return bool(
        parsed.document_type
        and parsed.document_number
        and parsed.issued_date
        and parsed.issuing_authority
        and parsed.title
        and parsed.scope
        and parsed.applicable_subjects
    )


def appendix_article_leak(parsed: ParsedDocument) -> bool:
    return any(article_contains_appendix_marker(article) for article in parsed.articles)


def missing_article_numbers(articles: list[Article]) -> list[str]:
    numbers = [article.number for article in articles]
    expected_numbers = expected_article_numbers(numbers)
    actual_numbers = set(numbers)
    return [number for number in expected_numbers if number not in actual_numbers]


def article_has_orphan_point(article: Article) -> bool:
    has_clause = False
    for line in article.raw_content.splitlines()[1:]:
        if re.match(r"^\d+\.\s+", line):
            has_clause = True
        if re.match(r"^[a-zđ]\)\s+", line, flags=re.IGNORECASE) and not has_clause:
            return True
    return False


def article_contains_structure_heading(article: Article) -> bool:
    lines = article.raw_content.splitlines()[1:]
    return any(re.match(r"^(Chương|Mục|Tiểu\s+mục)\s+", line, flags=re.IGNORECASE) for line in lines)


def article_contains_appendix_marker(article: Article) -> bool:
    lines = article.raw_content.splitlines()
    body_after_header = "\n".join(lines[1:])
    return bool(re.search(r"(^|\n)(PHỤ\s+LỤC|Phụ\s+lục|Mẫu\s+số|Biểu\s+mẫu)\b", body_after_header, flags=re.IGNORECASE))


def article_contains_closing_marker(article: Article) -> bool:
    return bool(
        re.search(
            r"(^|\n)(Nơi\s+nhận\b|TM\.(?:\s|$)|KT\.(?:\s|$)|TL\.(?:\s|$)|TUQ\.(?:\s|$))",
            article.raw_content,
            flags=re.IGNORECASE,
        )
    )


def has_generic_faqs(article_knowledge: list[ArticleKnowledge]) -> bool:
    questions = [faq["question"].lower() for item in article_knowledge for faq in item.faqs]
    generic = [question for question in questions if re.fullmatch(r"điều\s+\d+\s+quy định gì\??", question)]
    return bool(generic)


def has_common_keywords(article_knowledge: list[ArticleKnowledge]) -> bool:
    keywords = [keyword.lower() for item in article_knowledge for keyword in item.all_keywords]
    return any(keyword in COMMON_KEYWORDS for keyword in keywords)


def find_related_articles(article: Article, articles: list[Article], limit: int = 5) -> list[Article]:
    refs = set(re.findall(r"Điều\s+(\d+[a-zA-Z]?)", article.raw_content, flags=re.IGNORECASE))
    related = [item for item in articles if item.number in refs and item.number != article.number]
    if len(related) < limit:
        keywords = set(sum(extract_keyword_groups(article.raw_content).values(), []))
        scored: list[tuple[int, Article]] = []
        for item in articles:
            if item.number == article.number or item in related:
                continue
            other_keywords = set(sum(extract_keyword_groups(item.raw_content).values(), []))
            score = len(keywords.intersection(other_keywords))
            if score:
                scored.append((score, item))
        related.extend(item for _, item in sorted(scored, key=lambda row: -row[0]))
    return related[:limit]


def group_knowledge_by_topic(article_knowledge: list[ArticleKnowledge]) -> dict[str, list[ArticleKnowledge]]:
    grouped: dict[str, list[ArticleKnowledge]] = {}
    for item in article_knowledge:
        for topic in item.topics:
            grouped.setdefault(topic, []).append(item)
    return grouped


def expected_article_numbers(numbers: list[str]) -> list[str]:
    ints = sorted(int(number) for number in numbers if number.isdigit())
    if not ints:
        return []
    return [str(number) for number in range(ints[0], ints[-1] + 1)]


def find_duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def summarize(text: str, max_chars: int = 420) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rsplit(" ", 1)[0] + "..."


def control_note(item: ArticleKnowledge) -> str:
    if item.related_keywords:
        return "Điều này có nhắc hoặc liên kết đến văn bản khác; khi viện dẫn cần nói rõ: Cần đối chiếu thêm văn bản liên quan."
    return "Chỉ sử dụng nội dung gốc của điều này và các điều liên quan đã được tách trong Knowledge Pack."


def appendix_title(appendix: Appendix) -> str:
    label = "Mẫu số" if appendix.kind == "mau_so" else "Phụ lục"
    return f"{label} {appendix.number}. {appendix.title or 'Biểu mẫu, bảng hoặc nội dung kèm theo'}"


def document_folder_name(parsed: ParsedDocument) -> str:
    source = parsed.document_number or Path(parsed.file_name).stem or uuid4().hex[:8]
    return slugify(source)


def gpt_knowledge_file_name(parsed: ParsedDocument) -> str:
    return f"GPT_KNOWLEDGE_{document_folder_name(parsed)}.md"


def slugify(value: str) -> str:
    value = value.replace("/", "_")
    value = re.sub(r"[^A-Za-z0-9Đđ_-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "knowledge_pack"


def escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def yaml_list(values: list[str]) -> str:
    return ", ".join(f'"{escape_yaml(value)}"' for value in values)


def yaml_block(value: str) -> str:
    if not value.strip():
        return "  "
    return "\n".join(f"  {line}" for line in value.splitlines())


def yaml_list_block(values: list[str]) -> str:
    if not values:
        return "  []"
    return "\n".join(f"  - \"{escape_yaml(value)}\"" for value in values)


def unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
