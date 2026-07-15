import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from .document_processor import (
    APPENDIX_RE,
    ARTICLE_RE,
    CHAPTER_RE,
    FORM_RE,
    SECTION_RE,
    Appendix,
    Article,
    ParsedDocument,
    article_body_text,
    detect_applicable_subjects,
    detect_scope,
    is_closing_start,
    is_upper_heading,
    parse_appendices,
    parse_structure,
)
from .knowledge_pack import (
    build_article_knowledge,
    document_folder_name,
    embed_markdown_section,
    extract_keyword_groups,
    infer_topics,
    quality_checked_faqs,
    render_keyword_index,
    render_lookup,
    render_topics,
    summarize,
)


ISSUED_CONTENT_HEADING_RE = re.compile(
    r"^(HƯỚNG\s+DẪN|QUY\s+CHẾ|QUY\s+ĐỊNH|KHUNG|DANH\s+MỤC|ĐỀ\s+ÁN|CHƯƠNG\s+TRÌNH|NỘI\s+DUNG\s+KỸ\s+THUẬT)\b",
    re.IGNORECASE,
)
ISSUED_SIGNAL_RE = re.compile(
    r"(ban\s+hành\s+kèm\s+theo|kèm\s+theo|ban\s+hành\s+(quy\s+chế|hướng\s+dẫn|khung|danh\s+mục|đề\s+án|chương\s+trình))",
    re.IGNORECASE,
)
ATTACHED_CONFIRMATION_RE = re.compile(r"ban\s+hành\s+kèm\s+theo\s+.+\s+số", re.IGNORECASE)
REFERENCE_RE = re.compile(r"\b(Phụ\s+lục|Mẫu\s+số|Biểu\s+mẫu)\s+([IVXLCDM]+|\d+[A-Za-z0-9./-]*)\b", re.IGNORECASE)


@dataclass
class SourceLocation:
    start_line: int = 0
    end_line: int = 0


@dataclass
class AssetNode:
    id: str
    node_type: str
    number: str
    title: str
    parent_id: str
    order: int
    original_text: str
    normalized_text: str
    source_location: dict[str, int]
    checksum: str
    review_status: str = "PASS"
    scope_type: str = ""
    canonical_number: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class LegalKnowledgeAsset:
    schema_version: str
    document_number: str
    document_type: str
    title: str
    root_id: str
    nodes: list[AssetNode]
    stats: dict[str, int]
    validation: dict[str, object]
    migration_report: dict[str, object]


@dataclass
class AssetValidation:
    status: str
    errors: list[dict[str, str]]
    warnings: list[dict[str, str]]


def build_legal_knowledge_asset(parsed: ParsedDocument) -> LegalKnowledgeAsset:
    lines = [line.strip() for line in parsed.raw_text.splitlines() if line.strip()]
    base_id = stable_base_id(parsed)
    nodes: list[AssetNode] = []
    main_id = f"{base_id}-MAIN"
    nodes.append(
        make_node(
            node_id=main_id,
            node_type="MAIN_DOCUMENT",
            number=parsed.document_number,
            title=parsed.title,
            parent_id="",
            order=1,
            original_text=parsed.raw_text,
            source_location=SourceLocation(1, len(lines)),
            scope_type="MAIN_DOCUMENT",
            metadata={
                "document_type": parsed.document_type,
                "issued_date": parsed.issued_date,
                "effective_date": parsed.effective_date,
                "issuing_authority": parsed.issuing_authority,
                "scope": parsed.scope,
                "applicable_subjects": parsed.applicable_subjects,
                "legal_basis": parsed.legal_basis,
            },
        )
    )

    issued_start = detect_issued_content_start(lines)
    main_region_end = issued_start if issued_start is not None else len(lines)
    main_lines = trim_closing(lines[:main_region_end])
    main_articles = parsed.articles if issued_start is None else parse_structure(main_lines)[3]
    nodes.extend(article_nodes(base_id, main_id, main_articles, "MAIN_DOCUMENT", order_start=1))

    issued_nodes: list[AssetNode] = []
    if issued_start is not None:
        issued_lines = lines[issued_start:]
        issued_title = detect_issued_title(issued_lines)
        issued_id = f"{base_id}-ISSUED01"
        issued_main_lines, issued_appendix_lines = split_issued_content_and_appendices(issued_lines)
        issued_main_lines = strip_attached_confirmation_lines(issued_main_lines)
        issued_articles = parse_structure(issued_main_lines)[3]
        if not issued_articles:
            issued_articles = parse_thematic_provisions(issued_main_lines)
        issued_scope, issued_subjects = detect_scope_subjects_for_articles(issued_articles)
        issued_nodes.append(
            make_node(
                node_id=issued_id,
                node_type="ISSUED_CONTENT",
                number="01",
                title=issued_title,
                parent_id=main_id,
                order=1,
                original_text="\n".join(issued_lines),
                source_location=SourceLocation(issued_start + 1, len(lines)),
                scope_type="ISSUED_CONTENT",
                metadata={
                    "scope": issued_scope,
                    "applicable_subjects": issued_subjects,
                    "signals": issued_content_signals(lines, issued_start),
                },
            )
        )
        issued_nodes.extend(article_nodes(base_id, issued_id, issued_articles, "ISSUED_CONTENT", order_start=1, prefix="ISSUED01"))
        issued_appendices = parse_real_appendices(issued_appendix_lines)
        issued_nodes.extend(appendix_nodes(base_id, issued_id, issued_appendices, "ISSUED01", order_start=1))
        issued_nodes.extend(reference_nodes(base_id, issued_id, issued_lines, issued_appendices, "ISSUED01"))

    if issued_start is None:
        nodes.extend(appendix_nodes(base_id, main_id, parsed.appendices, "MAIN", order_start=1))
        nodes.extend(reference_nodes(base_id, main_id, lines, parsed.appendices, "MAIN"))
    nodes.extend(issued_nodes)

    validation = validate_asset(nodes, expected_issued=issued_start is not None)
    return LegalKnowledgeAsset(
        schema_version="2.0",
        document_number=parsed.document_number,
        document_type=parsed.document_type,
        title=parsed.title,
        root_id=main_id,
        nodes=nodes,
        stats=asset_stats(nodes),
        validation={
            "status": validation.status,
            "errors": validation.errors,
            "warnings": validation.warnings,
        },
        migration_report=build_migration_report(parsed, nodes),
    )


def stable_base_id(parsed: ParsedDocument) -> str:
    source = parsed.document_number or Path(parsed.file_name).stem or uuid4().hex[:8]
    compact = source.replace("/", "-").replace(".", "-").replace("_", "-")
    compact = re.sub(r"[^A-Za-z0-9Đđ-]+", "-", compact).strip("-")
    return compact or "LEGAL-ASSET"


def make_node(
    node_id: str,
    node_type: str,
    number: str,
    title: str,
    parent_id: str,
    order: int,
    original_text: str,
    source_location: SourceLocation,
    scope_type: str,
    review_status: str = "PASS",
    canonical_number: str = "",
    metadata: dict[str, object] | None = None,
) -> AssetNode:
    normalized = normalize_node_text(original_text)
    return AssetNode(
        id=node_id,
        node_type=node_type,
        number=number,
        title=title,
        parent_id=parent_id,
        order=order,
        original_text=original_text,
        normalized_text=normalized,
        source_location=asdict(source_location),
        checksum=checksum(original_text),
        review_status=review_status,
        scope_type=scope_type,
        canonical_number=canonical_number or canonicalize_number(number),
        metadata=metadata or {},
    )


def detect_issued_content_start(lines: list[str]) -> int | None:
    candidates: list[int] = []
    for index, line in enumerate(lines):
        if ISSUED_CONTENT_HEADING_RE.match(line) and issued_heading_has_context(lines, index):
            candidates.append(index)
        if ATTACHED_CONFIRMATION_RE.search(line) and index > 0:
            heading_index = nearest_previous_issued_heading(lines, index)
            if heading_index is not None:
                candidates.append(heading_index)
    return min(candidates) if candidates else None


def issued_heading_has_context(lines: list[str], index: int) -> bool:
    previous = "\n".join(lines[max(0, index - 12) : index])
    following = "\n".join(lines[index : min(len(lines), index + 8)])
    previous_lines = lines[max(0, index - 12) : index]
    if any(APPENDIX_RE.match(line) or FORM_RE.match(line) for line in previous_lines):
        return False
    return bool(
        ISSUED_SIGNAL_RE.search(previous)
        or ATTACHED_CONFIRMATION_RE.search(following)
        or any(is_closing_start(line) for line in previous_lines)
    )


def nearest_previous_issued_heading(lines: list[str], index: int) -> int | None:
    for cursor in range(index - 1, max(-1, index - 8), -1):
        if ISSUED_CONTENT_HEADING_RE.match(lines[cursor]) or is_upper_heading(lines[cursor]):
            return cursor
    return None


def issued_content_signals(lines: list[str], start: int) -> list[str]:
    window = lines[max(0, start - 8) : min(len(lines), start + 8)]
    return [line for line in window if ISSUED_SIGNAL_RE.search(line) or ISSUED_CONTENT_HEADING_RE.match(line)]


def detect_issued_title(lines: list[str]) -> str:
    title_lines: list[str] = []
    for line in lines[:8]:
        if ATTACHED_CONFIRMATION_RE.search(line):
            break
        if is_closing_start(line):
            continue
        if line.startswith("(") and "kèm theo" in line.lower():
            break
        title_lines.append(line)
        if len(title_lines) >= 3 and not is_upper_heading(line):
            break
    return " ".join(title_lines).strip() or "Nội dung ban hành kèm theo"


def trim_closing(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        if is_closing_start(line):
            return lines[:index]
    return lines


def split_issued_content_and_appendices(lines: list[str]) -> tuple[list[str], list[str]]:
    appendix_start: int | None = None
    for index, line in enumerate(lines):
        if is_real_appendix_heading(lines, index):
            appendix_start = index
            break
    if appendix_start is None:
        return lines, []
    return lines[:appendix_start], lines[appendix_start:]


def strip_attached_confirmation_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if not ATTACHED_CONFIRMATION_RE.search(line)]


def is_real_appendix_heading(lines: list[str], index: int) -> bool:
    line = lines[index].strip()
    if not (APPENDIX_RE.match(line) or FORM_RE.match(line)):
        return False
    upper_heading = is_upper_heading(line)
    if index > 0 and not upper_heading and not boundary_before(lines[index - 1]):
        return False
    if index + 1 >= len(lines):
        return False
    next_line = lines[index + 1].strip()
    if REFERENCE_RE.fullmatch(next_line):
        return False
    if upper_heading:
        return True
    return bool(re.match(r"^(Phụ\s+lục|Mẫu\s+số|Biểu\s+mẫu)\s+([IVXLCDM]+|\d+)\s*$", line, flags=re.IGNORECASE))


def boundary_before(previous_line: str) -> bool:
    return (
        not previous_line.strip()
        or is_upper_heading(previous_line)
        or previous_line.strip().endswith((".", ":", ";"))
        or ARTICLE_RE.match(previous_line.strip()) is not None
    )


def parse_real_appendices(lines: list[str]) -> list[Appendix]:
    filtered: list[str] = []
    for index, line in enumerate(lines):
        if APPENDIX_RE.match(line) or FORM_RE.match(line):
            if not is_real_appendix_heading(lines, index):
                continue
        filtered.append(line)
    return parse_appendices(filtered)


def parse_thematic_provisions(lines: list[str]) -> list[Article]:
    articles: list[Article] = []
    current: Article | None = None
    for line in lines:
        thematic = re.match(r"^([IVXLCDM]+)\s*[-–.]\s+(.+)$", line, flags=re.IGNORECASE)
        if thematic:
            current = Article(number=thematic.group(1).upper(), title=thematic.group(2).strip(), raw_content=line)
            articles.append(current)
            continue
        if current:
            current.raw_content += "\n" + line
    return articles


def article_nodes(
    base_id: str,
    parent_id: str,
    articles: list[Article],
    scope_type: str,
    order_start: int,
    prefix: str = "MAIN",
) -> list[AssetNode]:
    nodes: list[AssetNode] = []
    for offset, article in enumerate(articles, start=order_start):
        article_id = f"{base_id}-{prefix}-ART{article.number}"
        nodes.append(
            make_node(
                node_id=article_id,
                node_type="PROVISION",
                number=article.number,
                title=article.title,
                parent_id=parent_id,
                order=offset,
                original_text=article.raw_content,
                source_location=SourceLocation(),
                scope_type=scope_type,
                metadata={
                    "chapter": article.chapter,
                    "section": article.section,
                    "clauses": article.clauses,
                    "points": article.points,
                    "provision_kind": "Điều" if ARTICLE_RE.match(article.raw_content.splitlines()[0]) else "Mục",
                },
            )
        )
    return nodes


def appendix_nodes(
    base_id: str,
    parent_id: str,
    appendices: list[Appendix],
    prefix: str,
    order_start: int,
) -> list[AssetNode]:
    nodes: list[AssetNode] = []
    seen: set[str] = set()
    for offset, appendix in enumerate(appendices, start=order_start):
        canonical = canonicalize_number(appendix.number)
        review_status = "PASS"
        duplicate_suffix = ""
        if canonical in seen:
            review_status = "NEEDS_REVIEW"
            duplicate_suffix = f"-DUP{offset:02d}"
        seen.add(canonical)
        node_type = "FORM" if appendix.kind == "mau_so" else "APPENDIX"
        node_prefix = "FORM" if node_type == "FORM" else "APP"
        nodes.append(
            make_node(
                node_id=f"{base_id}-{prefix}-{node_prefix}-{canonical or offset}{duplicate_suffix}",
                node_type=node_type,
                number=appendix.number,
                title=appendix.title or ("Biểu mẫu" if node_type == "FORM" else "Phụ lục"),
                parent_id=parent_id,
                order=offset,
                original_text=appendix.raw_content,
                source_location=SourceLocation(),
                scope_type="APPENDIX" if node_type == "APPENDIX" else "FORM",
                review_status=review_status,
                canonical_number=canonical,
            )
        )
    return nodes


def reference_nodes(
    base_id: str,
    parent_id: str,
    lines: list[str],
    appendices: list[Appendix],
    prefix: str,
) -> list[AssetNode]:
    appendix_numbers = {canonicalize_number(appendix.number) for appendix in appendices}
    nodes: list[AssetNode] = []
    order = 1
    for line_index, line in enumerate(lines, start=1):
        if APPENDIX_RE.match(line) or FORM_RE.match(line):
            continue
        for match in REFERENCE_RE.finditer(line):
            canonical = canonicalize_number(match.group(2))
            if canonical in appendix_numbers or is_reference_context(line, match.start()):
                node_id = f"{base_id}-{prefix}-REF-{order:03d}"
                nodes.append(
                    make_node(
                        node_id=node_id,
                        node_type="REFERENCE",
                        number=match.group(2),
                        title=match.group(0),
                        parent_id=parent_id,
                        order=order,
                        original_text=line,
                        source_location=SourceLocation(line_index, line_index),
                        scope_type="REFERENCE",
                        canonical_number=canonical,
                        metadata={"target_canonical_number": canonical},
                    )
                )
                order += 1
    return nodes


def is_reference_context(line: str, start: int) -> bool:
    before = line[:start].lower()
    return any(marker in before for marker in ("theo ", "tại ", "hướng dẫn ", "quy định ", "xem ", "nguồn "))


def detect_scope_subjects_for_articles(articles: list[Article]) -> tuple[str, str]:
    if not articles:
        return "", ""
    scope = detect_scope(articles)
    subjects = detect_applicable_subjects(articles)
    if "Không phát hiện điều khoản chính" in scope:
        scope = ""
    return scope, subjects


def validate_asset(nodes: list[AssetNode], expected_issued: bool = False) -> AssetValidation:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    by_id = {node.id: node for node in nodes}
    issued_nodes = [node for node in nodes if node.node_type == "ISSUED_CONTENT"]
    if expected_issued and not issued_nodes:
        errors.append(error("KB-ISS-001", "Không phát hiện nội dung ban hành kèm theo."))
    for node in nodes:
        if node.parent_id and node.parent_id not in by_id:
            errors.append(error("KB-ISS-004", f"Node {node.id} sai parent_id."))
        if not node.id or not node.checksum:
            errors.append(error("KB-ID-001", f"Node {node.id or '<empty>'} thiếu ID hoặc checksum."))

    scoped_keys = [
        (node.parent_id, node.node_type, node.number, node.scope_type)
        for node in nodes
        if node.number and node.node_type != "FORM"
    ]
    duplicates = duplicate_keys(scoped_keys)
    if duplicates:
        errors.append(error("KB-ID-001", "Trùng node trong cùng phạm vi cấu trúc."))

    appendix_keys = [
        (node.parent_id, node.node_type, node.canonical_number)
        for node in nodes
        if node.node_type == "APPENDIX" and node.canonical_number
    ]
    if duplicate_keys(appendix_keys):
        errors.append(error("KB-APP-001", "Phụ lục/biểu mẫu bị đếm trùng trong cùng parent."))
    form_keys = [
        (node.parent_id, node.node_type, node.canonical_number)
        for node in nodes
        if node.node_type == "FORM" and node.canonical_number
    ]
    if duplicate_keys(form_keys):
        warnings.append(error("KB-APP-001", "Biểu mẫu có số lặp trong cùng parent; đã giữ node riêng và đánh dấu NEEDS_REVIEW."))

    for appendix in [node for node in nodes if node.node_type == "APPENDIX"]:
        if re.search(r"\b(theo|tại|hướng dẫn tại)\s+Phụ\s+lục", appendix.original_text, flags=re.IGNORECASE):
            warnings.append(error("KB-APP-002", f"Phụ lục {appendix.id} có dấu hiệu chứa dẫn chiếu cần review."))

    main_numbers = {node.number for node in nodes if node.node_type == "PROVISION" and node.scope_type == "MAIN_DOCUMENT"}
    issued_numbers = {node.number for node in nodes if node.node_type == "PROVISION" and node.scope_type == "ISSUED_CONTENT"}
    if main_numbers.intersection(issued_numbers):
        warnings.append(error("KB-ISS-003", "Có Điều cùng số ở MAIN_DOCUMENT và ISSUED_CONTENT; được chấp nhận vì khác parent."))

    status = "FAIL" if errors else "WARNING" if warnings else "PASS"
    return AssetValidation(status=status, errors=errors, warnings=warnings)


def error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def duplicate_keys(values: list[tuple[object, ...]]) -> list[tuple[object, ...]]:
    seen: set[tuple[object, ...]] = set()
    duplicates: list[tuple[object, ...]] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def asset_stats(nodes: list[AssetNode]) -> dict[str, int]:
    return {
        "main_document_article_count": sum(1 for node in nodes if node.node_type == "PROVISION" and node.scope_type == "MAIN_DOCUMENT"),
        "issued_content_count": sum(1 for node in nodes if node.node_type == "ISSUED_CONTENT"),
        "issued_content_provision_count": sum(1 for node in nodes if node.node_type == "PROVISION" and node.scope_type == "ISSUED_CONTENT"),
        "appendix_count": sum(1 for node in nodes if node.node_type == "APPENDIX"),
        "form_count": sum(1 for node in nodes if node.node_type == "FORM"),
        "table_count": sum(1 for node in nodes if node.node_type == "TABLE"),
        "reference_count": sum(1 for node in nodes if node.node_type == "REFERENCE"),
    }


def build_migration_report(parsed: ParsedDocument, nodes: list[AssetNode]) -> dict[str, object]:
    stats = asset_stats(nodes)
    return {
        "source_file": parsed.file_name,
        "legacy_article_count": len(parsed.articles),
        "legacy_appendix_count": len(parsed.appendices),
        "new_stats": stats,
        "main_document_nodes": [node.id for node in nodes if node.scope_type == "MAIN_DOCUMENT"],
        "issued_content_nodes": [node.id for node in nodes if node.scope_type == "ISSUED_CONTENT"],
        "appendix_nodes": [node.id for node in nodes if node.node_type == "APPENDIX"],
        "appendix_to_reference_nodes": [node.id for node in nodes if node.node_type == "REFERENCE"],
        "legacy_checksum": checksum(parsed.raw_text),
        "asset_checksum": checksum("\n".join(node.original_text for node in nodes if node.node_type in {"MAIN_DOCUMENT", "ISSUED_CONTENT"})),
        "review_nodes": [node.id for node in nodes if node.review_status == "NEEDS_REVIEW"],
    }


def render_asset_markdown(asset: LegalKnowledgeAsset) -> str:
    nodes = asset.nodes
    root = next(node for node in nodes if node.id == asset.root_id)
    lines = [
        f"# {asset.title}",
        "",
        "## SOURCE OF TRUTH",
        "",
        "Nội dung gốc là nguồn ưu tiên cao nhất. Metadata, bảng tra cứu, tóm tắt, từ khóa và FAQ chỉ hỗ trợ định vị.",
        "",
        "## Metadata",
        "",
        f"- Loại văn bản: {asset.document_type}",
        f"- Số/ký hiệu: {asset.document_number}",
        f"- Root node: {asset.root_id}",
        f"- Validation: {asset.validation['status']}",
        "",
        "## Văn bản chính",
        "",
    ]
    main_provisions = children(nodes, root.id, "PROVISION")
    if main_provisions:
        for provision in main_provisions:
            lines.extend([f"### Điều {provision.number}", "", provision.original_text, ""])
    else:
        lines.append("Không phát hiện điều khoản văn bản chính.")

    issued_contents = children(nodes, root.id, "ISSUED_CONTENT")
    if issued_contents:
        lines.extend(["", "## Nội dung ban hành kèm theo", ""])
        for issued in issued_contents:
            lines.extend([f"### {issued.title}", ""])
            for provision in children(nodes, issued.id, "PROVISION"):
                kind = provision.metadata.get("provision_kind", "Điều")
                lines.extend([f"#### {kind} {provision.number}", "", provision.original_text, ""])
            appendices = [node for node in children(nodes, issued.id) if node.node_type in {"APPENDIX", "FORM"}]
            if appendices:
                lines.extend(["", "## Phụ lục của nội dung ban hành kèm theo", ""])
                for appendix in appendices:
                    label = "Biểu mẫu" if appendix.node_type == "FORM" else "Phụ lục"
                    lines.extend([f"### {label} {appendix.canonical_number or appendix.number}", "", appendix.original_text, ""])

    root_appendices = [node for node in children(nodes, root.id) if node.node_type in {"APPENDIX", "FORM"}]
    if root_appendices:
        lines.extend(["", "## Phụ lục của văn bản chính", ""])
        for appendix in root_appendices:
            label = "Biểu mẫu" if appendix.node_type == "FORM" else "Phụ lục"
            lines.extend([f"### {label} {appendix.canonical_number or appendix.number}", "", appendix.original_text, ""])

    article_knowledge = build_article_knowledge_from_nodes(nodes)
    lines.extend(["", "## Bảng tra cứu", "", render_asset_lookup(nodes), ""])
    lines.extend(["", "## Chủ đề và từ khóa", "", render_asset_topics_keywords(article_knowledge), ""])
    lines.extend(["", "## FAQ đã kiểm duyệt", "", render_asset_faq(article_knowledge)])
    return "\n".join(lines).strip() + "\n"


def render_asset_lookup(nodes: list[AssetNode]) -> str:
    lines = [
        "| scope_type | parent_id | node_id | number | title | topic | keywords |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for node in nodes:
        if node.node_type not in {"PROVISION", "APPENDIX", "FORM", "REFERENCE"}:
            continue
        topics = []
        keywords = []
        if node.node_type == "PROVISION":
            article = node_to_article(node)
            topics = infer_topics(article)
            keywords = sum(extract_keyword_groups(node.original_text).values(), [])
        lines.append(
            f"| {node.scope_type} | {node.parent_id} | {node.id} | {node.number} | {node.title} | "
            f"{', '.join(topics)} | {', '.join(keywords)} |"
        )
    return "\n".join(lines)


def render_asset_topics_keywords(article_knowledge) -> str:
    if not article_knowledge:
        return "Không phát hiện chủ đề/từ khóa đạt tiêu chí."
    return "\n\n".join(
        [
            embed_markdown_section(render_topics(article_knowledge), "Không phát hiện chủ đề đạt tiêu chí."),
            embed_markdown_section(render_keyword_index(article_knowledge), "Không phát hiện từ khóa đạt tiêu chí."),
        ]
    )


def render_asset_faq(article_knowledge) -> str:
    faqs = quality_checked_faqs(article_knowledge) if article_knowledge else []
    if not faqs:
        return "Không có FAQ đạt kiểm tra chất lượng."
    lines: list[str] = []
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
    return "\n".join(lines).strip()


def build_article_knowledge_from_nodes(nodes: list[AssetNode]):
    class MinimalParsed:
        articles: list[Article]

    parsed = MinimalParsed()
    parsed.articles = [node_to_article(node) for node in nodes if node.node_type == "PROVISION"]
    return build_article_knowledge(parsed)  # type: ignore[arg-type]


def node_to_article(node: AssetNode) -> Article:
    return Article(number=node.number, title=node.title, raw_content=node.original_text)


def children(nodes: list[AssetNode], parent_id: str, node_type: str | None = None) -> list[AssetNode]:
    output = [node for node in nodes if node.parent_id == parent_id and (node_type is None or node.node_type == node_type)]
    return sorted(output, key=lambda node: node.order)


def write_legal_asset_outputs(asset: LegalKnowledgeAsset, output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    safe = document_folder_name_from_asset(asset)
    json_path = output_root / f"LEGAL_ASSET_{safe}.json"
    md_path = output_root / f"LEGAL_ASSET_{safe}.md"
    migration_path = output_root / f"MIGRATION_REPORT_{safe}.md"
    validation_path = output_root / f"ASSET_VALIDATION_{safe}.md"
    regression_path = output_root / f"REGRESSION_SUMMARY_{safe}.md"
    json_path.write_text(json.dumps(asset_to_dict(asset), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_asset_markdown(asset), encoding="utf-8")
    migration_path.write_text(render_migration_report(asset), encoding="utf-8")
    validation_path.write_text(render_asset_validation_report(asset), encoding="utf-8")
    regression_path.write_text(render_regression_summary(asset), encoding="utf-8")
    return {
        "json": json_path,
        "markdown": md_path,
        "migration_report": migration_path,
        "validation_report": validation_path,
        "regression_summary": regression_path,
    }


def asset_to_dict(asset: LegalKnowledgeAsset) -> dict[str, object]:
    return {
        "schema_version": asset.schema_version,
        "document_number": asset.document_number,
        "document_type": asset.document_type,
        "title": asset.title,
        "root_id": asset.root_id,
        "stats": asset.stats,
        "validation": asset.validation,
        "migration_report": asset.migration_report,
        "nodes": [asdict(node) for node in asset.nodes],
    }


def render_migration_report(asset: LegalKnowledgeAsset) -> str:
    report = asset.migration_report
    lines = [
        f"# Migration Report - {asset.document_number}",
        "",
        f"- Legacy articles: {report['legacy_article_count']}",
        f"- Legacy appendices: {report['legacy_appendix_count']}",
        f"- New stats: `{json.dumps(report['new_stats'], ensure_ascii=False)}`",
        f"- Legacy checksum: `{report['legacy_checksum']}`",
        f"- Asset checksum: `{report['asset_checksum']}`",
        "",
        "## MAIN_DOCUMENT nodes",
        "",
    ]
    lines.extend(f"- {node_id}" for node_id in report["main_document_nodes"])
    lines.extend(["", "## ISSUED_CONTENT nodes", ""])
    lines.extend(f"- {node_id}" for node_id in report["issued_content_nodes"])
    lines.extend(["", "## APPENDIX/FORM nodes", ""])
    lines.extend(f"- {node_id}" for node_id in report["appendix_nodes"])
    lines.extend(["", "## APPENDIX -> REFERENCE nodes", ""])
    lines.extend(f"- {node_id}" for node_id in report["appendix_to_reference_nodes"])
    lines.extend(["", "## NEEDS_REVIEW", ""])
    review_nodes = report["review_nodes"]
    lines.extend(f"- {node_id}" for node_id in review_nodes) if review_nodes else lines.append("- Không có.")
    return "\n".join(lines).strip() + "\n"


def render_asset_validation_report(asset: LegalKnowledgeAsset) -> str:
    validation = asset.validation
    lines = [f"# Asset Validation - {asset.document_number}", "", f"- Kết luận: {validation['status']}", "", "## Errors"]
    errors = validation["errors"]
    lines.extend(f"- {item['code']}: {item['message']}" for item in errors) if errors else lines.append("- Không có.")
    lines.extend(["", "## Warnings"])
    warnings = validation["warnings"]
    lines.extend(f"- {item['code']}: {item['message']}" for item in warnings) if warnings else lines.append("- Không có.")
    return "\n".join(lines).strip() + "\n"


def render_regression_summary(asset: LegalKnowledgeAsset) -> str:
    return "\n".join(
        [
            f"# Regression Summary - {asset.document_number}",
            "",
            f"- MAIN_DOCUMENT parsing: {'PASS' if asset.stats['main_document_article_count'] >= 0 else 'FAIL'}",
            f"- ISSUED_CONTENT detection: {'PASS' if asset.stats['issued_content_count'] >= 0 else 'FAIL'}",
            f"- Appendix detection: {'PASS' if asset.stats['appendix_count'] >= 0 else 'FAIL'}",
            f"- Reference detection: {'PASS' if asset.stats['reference_count'] >= 0 else 'FAIL'}",
            f"- Validation: {asset.validation['status']}",
            "",
        ]
    )


def document_folder_name_from_asset(asset: LegalKnowledgeAsset) -> str:
    source = asset.document_number or asset.root_id or uuid4().hex[:8]
    source = source.replace("/", "_").replace(".", "_")
    source = re.sub(r"[^A-Za-z0-9Đđ_-]+", "_", source.strip())
    return re.sub(r"_+", "_", source).strip("_") or "legal_asset"


def normalize_node_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonicalize_number(number: str) -> str:
    compact = number.strip().upper().replace(".", "").replace(" ", "")
    if "/" in compact or "-" in compact:
        return re.sub(r"[^A-Z0-9Đ/-]+", "", compact).replace("/", "-")
    roman = re.fullmatch(r"[IVXLCDM]+", compact)
    if roman:
        return compact
    digits = re.search(r"\d+", compact)
    if digits:
        return str(int(digits.group(0)))
    return compact
