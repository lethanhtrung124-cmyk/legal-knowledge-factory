import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)


@dataclass
class Article:
    number: str
    title: str
    raw_content: str
    clauses: list[str] = field(default_factory=list)
    points: list[str] = field(default_factory=list)
    chapter: str = ""
    section: str = ""
    subsection: str = ""


@dataclass
class Appendix:
    number: str
    title: str
    raw_content: str
    kind: str = "phu_luc"


@dataclass
class ParsedDocument:
    file_name: str
    document_type: str
    document_number: str
    issued_date: str
    effective_date: str
    issuing_authority: str
    title: str
    raw_text: str
    preamble: str
    legal_basis: list[str]
    scope: str
    applicable_subjects: str
    main_text: str
    appendix_text: str
    closing_text: str
    chapters: list[str]
    sections: list[str]
    subsections: list[str]
    articles: list[Article]
    appendices: list[Appendix]
    definitions: list[str]
    recipients: list[str] = field(default_factory=list)
    signer: str = ""
    warnings: list[str] = field(default_factory=list)


ARTICLE_RE = re.compile(r"^Điều\s+(\d+[a-zA-Z]?)\.\s*(.*)$", re.IGNORECASE)
THEMATIC_SECTION_RE = re.compile(r"^([IVXLCDM]+)\s*[-–]\s+(.+)$", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)\b\.?\s*(.*)$", re.IGNORECASE)
SECTION_RE = re.compile(r"^Mục\s+(\d+)\b\.?\s*(.*)$", re.IGNORECASE)
SUBSECTION_RE = re.compile(r"^Tiểu\s+mục\s+(\d+)\b\.?\s*(.*)$", re.IGNORECASE)
CLAUSE_RE = re.compile(r"^(\d+)\.\s+")
POINT_RE = re.compile(r"^([a-zđ])\)\s+", re.IGNORECASE)
APPENDIX_RE = re.compile(r"^(PHỤ\s+LỤC|Phụ\s+lục)\s*([IVXLCDM\dA-Z]*)\b\.?\s*(.*)$", re.IGNORECASE)
FORM_RE = re.compile(r"^(Mẫu\s+số|Biểu\s+mẫu)\s*([A-Za-z0-9./-]*)\b\.?\s*(.*)$", re.IGNORECASE)
ATTACHED_RE = re.compile(r"ban\s+hành\s+kèm\s+theo", re.IGNORECASE)
DOCUMENT_KIND_NAMES = ("Luật", "Nghị định", "Nghị quyết", "Thông tư", "Quyết định", "Công văn")
DOCUMENT_KIND_HEADING_RE = re.compile(r"^(LUẬT|NGHỊ\s+ĐỊNH|NGHỊ\s+QUYẾT|THÔNG\s+TƯ|QUYẾT\s+ĐỊNH|CÔNG\s+VĂN)$", re.IGNORECASE)
TYPE_NUMBER_RE = re.compile(
    r"^(Luật|Nghị\s+định|Nghị\s+quyết|Thông\s+tư|Quyết\s+định|Công\s+văn)\s+số\s*:?\s*"
    r"([0-9]+(?:\.[0-9]+)*(?:/[0-9]{4})?(?:/|-)[A-ZĐ0-9]{1,12}(?:[-/][A-ZĐ0-9]{1,12})*)\b",
    re.IGNORECASE,
)
DOCUMENT_NUMBER_RE = re.compile(
    r"\bSố\s*:?\s*([0-9]+(?:\.[0-9]+)*(?:/[0-9]{4})?(?:/|-)[A-ZĐ0-9]{1,12}(?:[-/][A-ZĐ0-9]{1,12})*)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"(?:ngày|ngày\s+ban\s+hành)\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
    re.IGNORECASE,
)
DATE_SLASH_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
LEGAL_BASIS_RE = re.compile(r"^Căn cứ\b", re.IGNORECASE)
PROPOSAL_RE = re.compile(r"^(Theo đề nghị|Xét đề nghị)\b", re.IGNORECASE)
MAIN_START_RE = re.compile(r"^(Chương\s+|Điều\s+1\.)", re.IGNORECASE)
CLOSING_START_RE = re.compile(
    r"^(Nơi\s+nhận\b|TM\.(?:\s|$)|T/M(?:\s|$)|KT\.(?:\s|$)|TL\.(?:\s|$)|TUQ\.(?:\s|$))",
    re.IGNORECASE,
)
SIGNER_TITLE_RE = re.compile(
    r"^(TM\.(?:\s|$)|T/M(?:\s|$)|KT\.(?:\s|$)|TL\.(?:\s|$)|TUQ\.(?:\s|$)|CHỦ\s+TỊCH|BỘ\s+TRƯỞNG|THỦ\s+TƯỚNG|PHÓ\s+THỦ\s+TƯỚNG|CHÁNH\s+ÁN|VIỆN\s+TRƯỞNG|TỔNG\s+BÍ\s+THƯ)",
    re.IGNORECASE,
)
SIGNER_ONLY_TITLE_RE = re.compile(
    r"^(BỘ\s+TRƯỞNG|THỦ\s+TƯỚNG|PHÓ\s+THỦ\s+TƯỚNG|CHỦ\s+TỊCH|PHÓ\s+CHỦ\s+TỊCH|CHÁNH\s+ÁN|VIỆN\s+TRƯỞNG|THỨ\s+TRƯỞNG)\b",
    re.IGNORECASE,
)


def parse_document(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    logger.info("Reading document %s", path.name)

    if suffix == ".docx":
        raw_text = read_docx(path)
    elif suffix == ".pdf":
        raw_text = read_pdf(path)
    else:
        raise ValueError("Định dạng file không được hỗ trợ.")

    normalized = normalize_text(raw_text)
    if not normalized.strip():
        raise ValueError("Không đọc được nội dung văn bản hoặc file rỗng.")

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    main_lines, appendix_lines, closing_lines = split_main_appendix_closing(lines)
    document_type = detect_document_type(lines)
    document_number = detect_document_number(lines)
    issued_date = detect_issued_date(lines)
    issuing_authority = detect_issuing_authority(lines, document_type, closing_lines)
    title = detect_title(lines, document_type)
    preamble_lines, legal_basis = split_preamble_and_basis(lines)
    chapters, sections, subsections, articles = parse_structure(main_lines)
    if not articles:
        chapters, sections, subsections, articles = parse_thematic_structure(main_lines)
    appendices = parse_appendices(appendix_lines)
    definitions = extract_definitions(articles)
    scope = detect_scope(articles)
    applicable_subjects = detect_applicable_subjects(articles)
    effective_date = detect_effective_date(articles, issued_date)
    recipients, signer = extract_closing_metadata(closing_lines)
    warnings = collect_parse_warnings(
        document_number=document_number,
        issued_date=issued_date,
        issuing_authority=issuing_authority,
        articles=articles,
        appendices=appendices,
    )

    logger.info(
        "Parsed %s: type=%s number=%s articles=%s appendices=%s",
        path.name,
        document_type,
        document_number,
        len(articles),
        len(appendices),
    )

    return ParsedDocument(
        file_name=path.name,
        document_type=document_type,
        document_number=document_number,
        issued_date=issued_date,
        effective_date=effective_date,
        issuing_authority=issuing_authority,
        title=title,
        raw_text=normalized,
        preamble="\n".join(preamble_lines),
        legal_basis=legal_basis,
        scope=scope,
        applicable_subjects=applicable_subjects,
        main_text="\n".join(main_lines),
        appendix_text="\n".join(appendix_lines),
        closing_text="\n".join(closing_lines),
        chapters=chapters,
        sections=sections,
        subsections=subsections,
        articles=articles,
        appendices=appendices,
        definitions=definitions,
        recipients=recipients,
        signer=signer,
        warnings=warnings,
    )


def read_docx(path: Path) -> str:
    try:
        doc = Document(path)
        lines: list[str] = []
        for section in doc.sections:
            for container in (section.header, section.footer):
                lines.extend(read_docx_container(container))
        lines.extend(read_docx_container(doc))
        return "\n".join(unique_lines_preserve_order(lines))
    except Exception as exc:
        logger.exception("Could not read docx %s", path)
        raise ValueError("Không đọc được file .docx.") from exc


def read_docx_container(container) -> list[str]:
    lines: list[str] = []
    for block in iter_block_items(container):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                lines.append(text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    for cell in cells:
                        lines.extend(line.strip() for line in cell.splitlines() if line.strip())
    return lines


def iter_block_items(parent):
    parent_elm = parent.element.body if isinstance(parent, DocxDocument) else parent._element
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def unique_lines_preserve_order(lines: list[str]) -> list[str]:
    output: list[str] = []
    for line in lines:
        if not output or output[-1] != line:
            output.append(line)
    return output


def read_pdf(path: Path) -> str:
    try:
        import fitz

        with fitz.open(path) as pdf:
            return "\n".join(page.get_text("text") for page in pdf)
    except Exception as pymupdf_exc:
        logger.warning("PyMuPDF failed for %s: %s", path.name, pymupdf_exc)

    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception as exc:
        logger.exception("Could not read pdf %s", path)
        raise ValueError("Không đọc được file .pdf.") from exc


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_document_type(lines: Iterable[str]) -> str:
    for line in lines_before_basis(list(lines)[:120]):
        type_number_match = TYPE_NUMBER_RE.match(line)
        if type_number_match:
            return normalize_document_type(type_number_match.group(1))

        heading_match = DOCUMENT_KIND_HEADING_RE.match(line.strip())
        if heading_match:
            return normalize_document_type(heading_match.group(1))
    return "Văn bản pháp luật"


def detect_document_number(lines: list[str]) -> str:
    for line in lines[:80]:
        if LEGAL_BASIS_RE.match(line):
            break
        type_number_match = TYPE_NUMBER_RE.match(line)
        if type_number_match:
            return type_number_match.group(2)
        match = DOCUMENT_NUMBER_RE.search(line)
        if match:
            return match.group(1)
    return ""


def detect_issued_date(lines: list[str]) -> str:
    for line in lines[:120]:
        if LEGAL_BASIS_RE.match(line):
            break
        match = DATE_RE.search(line)
        if match:
            day, month, year = match.groups()
            return f"{int(day):02d}/{int(month):02d}/{year}"
        slash_match = DATE_SLASH_RE.search(line)
        if slash_match:
            day, month, year = slash_match.groups()
            return f"{int(day):02d}/{int(month):02d}/{year}"
    return ""


def detect_issuing_authority(lines: list[str], document_type: str, closing_lines: list[str] | None = None) -> str:
    authority_from_signature = detect_issuing_authority_from_signature(closing_lines or [])
    if authority_from_signature:
        return normalize_authority_name(authority_from_signature)

    upper_type = document_type.upper()
    authority_markers = (
        "CHÍNH PHỦ",
        "QUỐC HỘI",
        "ỦY BAN THƯỜNG VỤ QUỐC HỘI",
        "THỦ TƯỚNG CHÍNH PHỦ",
        "BỘ ",
        "NGÂN HÀNG NHÀ NƯỚC",
        "TÒA ÁN NHÂN DÂN TỐI CAO",
        "VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO",
        "ỦY BAN NHÂN DÂN",
        "HỘI ĐỒNG NHÂN DÂN",
        "BAN CHẤP HÀNH TRUNG ƯƠNG",
        "BỘ CHÍNH TRỊ",
    )
    for index, line in enumerate(lines[:80]):
        if LEGAL_BASIS_RE.match(line):
            break
        compact = line.strip()
        upper = compact.upper()
        if not compact or "SỐ" == upper[:2] or DATE_RE.search(compact) or DATE_SLASH_RE.search(compact):
            continue
        if is_signer_title(compact):
            continue
        if upper_type == "NGHỊ ĐỊNH" and "CHÍNH PHỦ" in upper:
            return normalize_authority_name(collect_authority_heading(lines, index))
        if upper_type == "NGHỊ QUYẾT" and ("CHÍNH PHỦ" in upper or "QUỐC HỘI" in upper or "ỦY BAN THƯỜNG VỤ QUỐC HỘI" in upper):
            return normalize_authority_name(collect_authority_heading(lines, index))
        if upper_type == "NGHỊ QUYẾT" and ("BỘ CHÍNH TRỊ" in upper or "BAN CHẤP HÀNH TRUNG ƯƠNG" in upper):
            return normalize_authority_name(collect_authority_heading(lines, index))
        if upper_type == "THÔNG TƯ" and ("BỘ " in upper or "NGÂN HÀNG NHÀ NƯỚC" in upper):
            return normalize_authority_name(collect_authority_heading(lines, index))
        if upper_type == "QUYẾT ĐỊNH" and any(marker in upper for marker in ("THỦ TƯỚNG", "BỘ ", "ỦY BAN")):
            return normalize_authority_name(collect_authority_heading(lines, index))
        if upper_type == "LUẬT" and "QUỐC HỘI" in upper:
            return normalize_authority_name(collect_authority_heading(lines, index))
        if any(marker in upper for marker in authority_markers):
            return normalize_authority_name(collect_authority_heading(lines, index))
    return ""


def detect_issuing_authority_from_signature(lines: list[str]) -> str:
    for line in lines:
        compact = line.strip()
        upper = compact.upper()
        if upper.startswith("TM."):
            authority = compact[3:].strip()
            return "" if is_signer_title(authority) else normalize_authority_name(authority)
        if upper.startswith("T/M"):
            authority = re.sub(r"^T/M\.?\s*", "", compact, flags=re.IGNORECASE).strip()
            return "" if is_signer_title(authority) else normalize_authority_name(authority)
        if upper.startswith(("KT.", "TL.", "TUQ.")):
            continue
        if upper in {"CHÍNH PHỦ", "QUỐC HỘI", "BỘ CHÍNH TRỊ", "BAN CHẤP HÀNH TRUNG ƯƠNG"} or upper.startswith(("BỘ ", "ỦY BAN NHÂN DÂN", "HỘI ĐỒNG NHÂN DÂN")):
            return "" if is_signer_title(compact) else compact
    return ""


def collect_authority_heading(lines: list[str], start_index: int) -> str:
    parts = [lines[start_index].strip()]
    for line in lines[start_index + 1 : min(start_index + 6, len(lines))]:
        compact = line.strip()
        if not is_authority_heading_continuation(compact):
            break
        parts.append(compact)
    return " ".join(parts)


def is_authority_heading_continuation(line: str) -> bool:
    if not line:
        return False
    if DATE_RE.search(line) or DATE_SLASH_RE.search(line):
        return False
    if is_signer_title(line):
        return False
    if re.match(r"^(Số|CỘNG\s+HÒA|Độc\s+lập|Hà\s+Nội|TP\.|Luật\s+số|Nghị\s+định\s+số|Thông\s+tư\s+số|Quyết\s+định\s+số)\b", line, flags=re.IGNORECASE):
        return False
    if DOCUMENT_KIND_HEADING_RE.match(line) or TYPE_NUMBER_RE.match(line) or DOCUMENT_NUMBER_RE.search(line):
        return False
    letters = [char for char in line if char.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return uppercase_ratio >= 0.75


def is_signer_title(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value.strip())
    if not compact:
        return False
    if re.match(r"^(KT\.|TL\.|TUQ\.)\s+", compact, flags=re.IGNORECASE):
        return True
    without_tm = re.sub(r"^(TM\.|T/M\.?)\s+", "", compact, flags=re.IGNORECASE)
    upper = without_tm.upper()
    if upper.startswith(("BỘ TRƯỞNG BỘ ", "THỦ TRƯỞNG CƠ QUAN ")):
        return False
    return bool(SIGNER_ONLY_TITLE_RE.match(without_tm))


def is_signer_heading_line(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value.strip())
    without_tm = re.sub(r"^TM\.\s+", "", compact, flags=re.IGNORECASE)
    return bool(SIGNER_ONLY_TITLE_RE.match(without_tm))


def is_issuer_subtitle_line(value: str) -> bool:
    upper = re.sub(r"\s+", " ", value.strip()).upper()
    return upper in {
        "CỦA BỘ CHÍNH TRỊ",
        "CỦA BAN BÍ THƯ",
        "CỦA BAN CHẤP HÀNH TRUNG ƯƠNG",
        "CỦA CHÍNH PHỦ",
        "CỦA QUỐC HỘI",
        "CỦA ỦY BAN THƯỜNG VỤ QUỐC HỘI",
    }


def normalize_authority_name(value: str) -> str:
    compact = re.sub(r"\s+", " ", value.strip())
    if not compact:
        return ""
    letters = [char for char in compact if char.isalpha()]
    if letters and (
        sum(1 for char in letters if char.isupper()) / len(letters) > 0.75
        or compact == compact.lower()
    ):
        compact = " ".join(word[:1].upper() + word[1:].lower() for word in compact.split())
    replacements = {
        "Chính Phủ": "Chính phủ",
        "Quốc Hội": "Quốc hội",
        "Ủy Ban Thường Vụ Quốc Hội": "Ủy ban Thường vụ Quốc hội",
        "Thủ Tướng Chính Phủ": "Thủ tướng Chính phủ",
        "Bộ Tài Chính": "Bộ Tài chính",
        "Bộ Khoa Học Và Công Nghệ": "Bộ Khoa học và Công nghệ",
        "Ngân Hàng Nhà Nước": "Ngân hàng Nhà nước",
        "Tòa Án Nhân Dân Tối Cao": "Tòa án nhân dân tối cao",
        "Viện Kiểm Sát Nhân Dân Tối Cao": "Viện kiểm sát nhân dân tối cao",
        "Ủy Ban Nhân Dân": "Ủy ban nhân dân",
        "Hội Đồng Nhân Dân": "Hội đồng nhân dân",
        "Ban Chấp Hành Trung Ương": "Ban Chấp hành Trung ương",
        "Bộ Chính Trị": "Bộ Chính trị",
        " Và ": " và ",
        " Của ": " của ",
        " Trực Thuộc ": " trực thuộc ",
    }
    for old, new in replacements.items():
        compact = compact.replace(old, new)
    return compact


def detect_title(lines: list[str], document_type: str) -> str:
    stop_markers = (
        "căn cứ",
        "theo đề nghị",
        "xét đề nghị",
        "chương ",
        "điều ",
        "nghị định này",
        "nghị quyết này",
        "thông tư này",
        "quyết định này",
        "luật này",
    )
    type_index = -1
    for index, line in enumerate(lines[:120]):
        if LEGAL_BASIS_RE.match(line) or MAIN_START_RE.match(line):
            break
        if TYPE_NUMBER_RE.match(line) and normalize_document_type(TYPE_NUMBER_RE.match(line).group(1)) == document_type:
            type_index = index
            break
        heading_match = DOCUMENT_KIND_HEADING_RE.match(line.strip())
        if heading_match and normalize_document_type(heading_match.group(1)) == document_type:
            type_index = index
            break
    if type_index >= 0:
        title_lines: list[str] = []
        for next_line in lines[type_index + 1 : min(type_index + 10, len(lines))]:
            lowered = next_line.lower()
            if lowered.startswith(stop_markers):
                break
            if is_signer_heading_line(next_line):
                break
            if is_issuer_subtitle_line(next_line):
                continue
            if TYPE_NUMBER_RE.match(next_line) or DOCUMENT_KIND_HEADING_RE.match(next_line.strip()):
                continue
            if re.search(r"^(Số|CỘNG HÒA|Độc lập|Hà Nội|TP\.)\b", next_line, flags=re.IGNORECASE):
                continue
            if title_lines and is_upper_heading(title_lines[-1]) and not is_upper_heading(next_line):
                break
            if len(next_line) > 260:
                break
            title_lines.append(next_line)
        title = " ".join(title_lines).strip()[:300] or lines[type_index][:300]
        return normalize_title(title)
    return lines[0][:300] if lines else "Văn bản pháp luật"


def lines_before_basis(lines: list[str]) -> list[str]:
    output: list[str] = []
    for line in lines:
        if LEGAL_BASIS_RE.match(line):
            break
        output.append(line)
    return output


def normalize_document_type(value: str) -> str:
    compact = re.sub(r"\s+", " ", value.strip()).lower()
    mapping = {
        "luật": "Luật",
        "nghị định": "Nghị định",
        "nghị quyết": "Nghị quyết",
        "thông tư": "Thông tư",
        "quyết định": "Quyết định",
        "công văn": "Công văn",
    }
    return mapping.get(compact, value.strip())


def normalize_title(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    letters = [char for char in compact if char.isalpha()]
    if letters and sum(1 for char in letters if char.isupper()) / len(letters) > 0.8:
        compact = compact.lower()
        compact = compact[:1].upper() + compact[1:]
        replacements = {
            "luật chuyển đổi số": "Luật Chuyển đổi số",
            "luật": "Luật",
            "nghị định": "Nghị định",
            "nghị quyết": "Nghị quyết",
            "thông tư": "Thông tư",
            "quyết định": "Quyết định",
        }
        for old, new in replacements.items():
            compact = compact.replace(old, new)
    return compact


def split_preamble_and_basis(lines: list[str]) -> tuple[list[str], list[str]]:
    preamble: list[str] = []
    basis: list[str] = []
    in_basis = False
    for line in lines:
        if MAIN_START_RE.match(line):
            break
        if LEGAL_BASIS_RE.match(line):
            in_basis = True
            basis.append(line)
            continue
        if in_basis and (PROPOSAL_RE.match(line) or re.search(r"\bban\s+hành\b", line, flags=re.IGNORECASE)):
            continue
        if in_basis and line.endswith(";"):
            basis.append(line)
        else:
            preamble.append(line)
    return preamble, basis


def split_main_and_appendix(lines: list[str]) -> tuple[list[str], list[str]]:
    main_lines, appendix_lines, _ = split_main_appendix_closing(lines)
    return main_lines, appendix_lines


def split_main_appendix_closing(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    main_start = 0
    for index, line in enumerate(lines):
        if MAIN_START_RE.match(line):
            main_start = index
            break

    appendix_start: int | None = None
    closing_start: int | None = None
    for index, line in enumerate(lines[main_start:], start=main_start):
        if is_appendix_start(line):
            appendix_start = index
            break
        if is_closing_start(line):
            if closing_start is None:
                closing_start = index
            continue

    if appendix_start is not None:
        if closing_start is not None and closing_start < appendix_start:
            adjusted_appendix_start = adjust_appendix_start(lines, appendix_start, closing_start)
            return lines[main_start:closing_start], lines[adjusted_appendix_start:], lines[closing_start:adjusted_appendix_start]
        main_lines = lines[main_start:appendix_start]
        appendix_lines = lines[appendix_start:]
        return main_lines, appendix_lines, []

    if closing_start is not None:
        return lines[main_start:closing_start], [], lines[closing_start:]
    return lines[main_start:], [], []


def is_appendix_start(line: str) -> bool:
    if ARTICLE_RE.match(line):
        return False
    return bool(APPENDIX_RE.match(line) or FORM_RE.match(line) or ATTACHED_RE.search(line))


def adjust_appendix_start(lines: list[str], appendix_start: int, closing_start: int) -> int:
    if APPENDIX_RE.match(lines[appendix_start].strip()) or FORM_RE.match(lines[appendix_start].strip()):
        return appendix_start
    previous_index = appendix_start - 1
    if previous_index <= closing_start:
        return appendix_start
    previous_line = lines[previous_index].strip()
    if previous_line and not is_closing_start(previous_line) and not previous_line.startswith("-") and is_upper_heading(previous_line):
        return previous_index
    return appendix_start


def is_upper_heading(line: str) -> bool:
    letters = [char for char in line if char.isalpha()]
    return bool(letters) and sum(1 for char in letters if char.isupper()) / len(letters) >= 0.75


def is_closing_start(line: str) -> bool:
    return bool(CLOSING_START_RE.match(line.strip()))


def parse_structure(lines: list[str]) -> tuple[list[str], list[str], list[str], list[Article]]:
    chapters: list[str] = []
    sections: list[str] = []
    subsections: list[str] = []
    articles: list[Article] = []
    current_article: Article | None = None
    current_chapter = ""
    current_section = ""
    current_subsection = ""

    for line in lines:
        if is_appendix_start(line) or is_closing_start(line):
            break

        chapter_match = CHAPTER_RE.match(line)
        if chapter_match:
            current_chapter = line
            current_section = ""
            current_subsection = ""
            chapters.append(line)
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            current_section = line
            current_subsection = ""
            sections.append(line)
            continue

        subsection_match = SUBSECTION_RE.match(line)
        if subsection_match:
            current_subsection = line
            subsections.append(line)
            continue

        article_match = ARTICLE_RE.match(line)
        if article_match:
            current_article = Article(
                number=article_match.group(1),
                title=article_match.group(2).strip(),
                raw_content=line,
                chapter=current_chapter,
                section=current_section,
                subsection=current_subsection,
            )
            articles.append(current_article)
            continue

        if current_article:
            current_article.raw_content += "\n" + line
            if CLAUSE_RE.match(line):
                current_article.clauses.append(line)
            if POINT_RE.match(line):
                current_article.points.append(line)

    return chapters, sections, subsections, articles


def parse_thematic_structure(lines: list[str]) -> tuple[list[str], list[str], list[str], list[Article]]:
    chapters: list[str] = []
    sections: list[str] = []
    articles: list[Article] = []
    current_article: Article | None = None

    for line in lines:
        if is_appendix_start(line) or is_closing_start(line):
            break
        section_match = THEMATIC_SECTION_RE.match(line)
        if section_match:
            current_heading = line
            chapters.append(line)
            current_article = Article(
                number=section_match.group(1).upper(),
                title=section_match.group(2).strip(),
                raw_content=line,
                chapter=current_heading,
            )
            articles.append(current_article)
            continue
        if current_article:
            current_article.raw_content += "\n" + line
            if CLAUSE_RE.match(line):
                current_article.clauses.append(line)
            if POINT_RE.match(line):
                current_article.points.append(line)

    return chapters, sections, [], articles


def parse_appendices(lines: list[str]) -> list[Appendix]:
    appendices: list[Appendix] = []
    current: Appendix | None = None

    for line in lines:
        appendix_match = APPENDIX_RE.match(line)
        form_match = FORM_RE.match(line)
        if appendix_match or form_match:
            match = appendix_match or form_match
            kind = "phu_luc" if appendix_match else "mau_so"
            number = match.group(2).strip() or f"{len(appendices) + 1:02d}"
            title = match.group(3).strip()
            current = Appendix(number=number, title=title, raw_content=line, kind=kind)
            appendices.append(current)
            continue

        if current:
            current.raw_content += "\n" + line
        elif line.strip():
            current = Appendix(number=f"{len(appendices) + 1:02d}", title="Phụ lục", raw_content=line)
            appendices.append(current)

    return appendices


def extract_definitions(articles: list[Article]) -> list[str]:
    definitions: list[str] = []
    definition_markers = ("giải thích từ ngữ", "được hiểu là", "trong văn bản này")
    for article in articles:
        lowered = article.raw_content.lower()
        if any(marker in lowered for marker in definition_markers):
            definitions.append(f"Điều {article.number}. {article.title}\n{article.raw_content}")
    return definitions


def detect_scope(articles: list[Article]) -> str:
    for article in articles[:5]:
        text = article.raw_content.lower()
        title = article.title.lower()
        first_line = article.raw_content.splitlines()[0].lower() if article.raw_content else ""
        if "phạm vi điều chỉnh" in title or "phạm vi điều chỉnh" in first_line or "phạm vi điều chỉnh" in text:
            return extract_scope_text(article)
    if articles:
        first_article_body = article_body_text(articles[0])
        return first_article_body or articles[0].title or articles[0].raw_content
    return "Không phát hiện điều khoản chính để xác định phạm vi điều chỉnh."


def detect_applicable_subjects(articles: list[Article]) -> str:
    for article in articles[:8]:
        text = article.raw_content.lower()
        title = article.title.lower()
        first_line = article.raw_content.splitlines()[0].lower() if article.raw_content else ""
        if "đối tượng áp dụng" in title or "đối tượng áp dụng" in first_line:
            subjects = extract_subject_items(article)
            return format_subject_items(subjects)
    inferred = infer_applicable_subjects(articles)
    return format_subject_items(inferred)


def format_subject_items(subjects: list[str]) -> str:
    lines: list[str] = []
    for subject in subjects:
        if subject.startswith("  - "):
            lines.append(subject)
        else:
            lines.append(f"- {subject}")
    return "\n".join(lines)


def article_body_text(article: Article) -> str:
    lines = article.raw_content.splitlines()
    body = "\n".join(lines[1:]).strip()
    return body or article.title.strip()


def extract_scope_text(article: Article) -> str:
    body_lines = [normalize_subject_text(line) for line in article.raw_content.splitlines()[1:]]
    scope_lines: list[str] = []
    for line in body_lines:
        if not line:
            continue
        lowered = line.lower()
        if is_applicable_subject_line(line):
            continue
        if "quy định" in lowered or "phạm vi điều chỉnh" in lowered:
            scope_lines.append(line)
    if scope_lines:
        return "\n".join(unique_texts(scope_lines))
    return article_body_text(article)


def extract_subject_items(article: Article) -> list[str]:
    body_lines = article.raw_content.splitlines()[1:]
    normalized_lines = [normalize_subject_text(line) for line in body_lines]
    application_lines = [line for line in normalized_lines if is_applicable_subject_line(line)]
    source_lines = application_lines or normalized_lines
    items: list[str] = []
    for compact in source_lines:
        if not compact:
            continue
        if looks_like_subject_intro(compact):
            intro_items = split_subject_sentence(compact)
            items.extend(intro_items)
            continue
        items.append(compact)
    return normalize_subject_activity_items(unique_texts(items))


def infer_applicable_subjects(articles: list[Article]) -> list[str]:
    candidate_texts = [article_body_text(article) for article in articles[:5]]
    for text in candidate_texts:
        if is_applicable_subject_line(text):
            return [extract_sentence_with_subjects(text)]
    return ["Cơ quan, tổ chức, cá nhân có liên quan đến nội dung điều chỉnh của văn bản"]


def is_applicable_subject_line(text: str) -> bool:
    lowered = text.lower()
    return "áp dụng đối với" in lowered or "đối tượng áp dụng" in lowered


def extract_sentence_with_subjects(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip(" ;.")
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    for sentence in sentences:
        lowered = sentence.lower()
        if is_applicable_subject_line(sentence):
            return sentence.strip(" ;.")
    return compact


def normalize_subject_activity_items(items: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in items:
        semantic = split_subject_activity(item)
        if semantic:
            normalized.extend(semantic)
        else:
            normalized.append(item)
    return unique_texts(normalized)


def split_subject_activity(text: str) -> list[str]:
    lowered = text.lower()
    subject_patterns = (
        r"^(?P<subject>cơ quan,\s*tổ chức,\s*cá nhân)\s+(?P<relation>có liên quan đến|liên quan đến)\s+(?P<activity>.+)$",
        r"^(?P<subject>cơ quan,\s*tổ chức,\s*cá nhân)\s+(?P<relation>tham gia trực tiếp hoặc liên quan đến)\s+(?:các\s+)?hoạt động:\s*(?P<activity>.+)$",
        r"^(?P<subject>nhà đầu tư và cơ quan,\s*tổ chức,\s*cá nhân)\s+(?P<relation>có liên quan đến|liên quan đến)\s+(?P<activity>.+)$",
    )
    for pattern in subject_patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            subject = preserve_subject_casing(match.group("subject"), text)
            activities = split_activity_list(match.group("activity"))
            lines = [f"Chủ thể: {subject}", "Hoạt động liên quan:"]
            lines.extend(f"  - {activity}" for activity in activities)
            return lines
    if lowered.startswith("cơ quan, tổ chức, cá nhân có liên quan"):
        return ["Chủ thể: Cơ quan, tổ chức, cá nhân", "Hoạt động liên quan:", "  - nội dung điều chỉnh của văn bản"]
    return []


def preserve_subject_casing(subject: str, source: str) -> str:
    start = source.lower().find(subject.lower())
    if start >= 0:
        return source[start : start + len(subject)].strip()
    return subject.strip()


def split_activity_list(activity: str) -> list[str]:
    cleaned = activity.strip(" ;.")
    if ";" in cleaned or "\n" in cleaned:
        parts = [part.strip(" ;.") for part in re.split(r";|\n", cleaned) if part.strip(" ;.")]
    else:
        parts = [cleaned]
    return parts or [cleaned]


def normalize_subject_text(line: str) -> str:
    compact = re.sub(r"\s+", " ", line).strip(" ;.")
    compact = re.sub(r"^\d+\.\s*", "", compact)
    compact = re.sub(r"^[a-zđ]\)\s*", "", compact, flags=re.IGNORECASE)
    return compact.strip(" ;.")


def looks_like_subject_intro(text: str) -> bool:
    lowered = text.lower()
    return lowered.startswith((
        "văn bản này áp dụng đối với",
        "nghị định này áp dụng đối với",
        "nghị quyết này áp dụng đối với",
        "thông tư này áp dụng đối với",
        "luật này áp dụng đối với",
    ))


def split_subject_sentence(text: str) -> list[str]:
    cleaned = re.sub(
        r"^(văn bản này|nghị định này|nghị quyết này|thông tư này|luật này)\s+áp dụng\s+đối\s+với\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if "các hoạt động:" in cleaned.lower():
        return [cleaned.strip(" ;.")]
    parts = [part.strip(" ;.") for part in re.split(r";|\n", cleaned) if part.strip(" ;.")]
    return parts or [cleaned.strip(" ;.")]


def unique_texts(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def detect_effective_date(articles: list[Article], issued_date: str = "") -> str:
    article = find_effective_article(articles)
    if not article:
        return ""
    text = article.raw_content
    lowered = text.lower()
    if "kể từ ngày ký" in lowered or "từ ngày ký" in lowered:
        return f"Kể từ ngày ký ban hành ({issued_date})" if issued_date else "Kể từ ngày ký ban hành"
    slash_match = DATE_SLASH_RE.search(text)
    if slash_match:
        day, month, year = slash_match.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"
    long_date = DATE_RE.search(text)
    if long_date:
        day, month, year = long_date.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"
    return ""


def find_effective_article(articles: list[Article]) -> Article | None:
    for article in articles:
        title = article.title.lower()
        first_line = article.raw_content.splitlines()[0].lower() if article.raw_content else ""
        if "hiệu lực thi hành" in title or "hiệu lực thi hành" in first_line:
            return article
    for article in articles:
        body = "\n".join(article.raw_content.splitlines()[1:]).lower()
        if "có hiệu lực thi hành" in body or "hiệu lực thi hành kể từ" in body:
            return article
    return None


def extract_closing_metadata(lines: list[str]) -> tuple[list[str], str]:
    recipients: list[str] = []
    signer_candidates: list[str] = []
    in_recipients = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("nơi nhận"):
            in_recipients = True
            recipients.append(stripped)
            continue
        if SIGNER_TITLE_RE.match(stripped):
            in_recipients = False
            signer_candidates.append(stripped)
            continue
        if in_recipients:
            recipients.append(stripped)
        elif signer_candidates or looks_like_person_name(stripped):
            signer_candidates.append(stripped)
    return recipients, "\n".join(signer_candidates).strip()


def looks_like_person_name(value: str) -> bool:
    if len(value) > 80 or any(char.isdigit() for char in value):
        return False
    words = value.split()
    return 2 <= len(words) <= 5 and sum(word[:1].isupper() for word in words) == len(words)


def collect_parse_warnings(
    document_number: str,
    issued_date: str,
    issuing_authority: str,
    articles: list[Article],
    appendices: list[Appendix],
) -> list[str]:
    warnings: list[str] = []
    if not document_number:
        warnings.append("Thiếu số/ký hiệu văn bản.")
    if not issued_date:
        warnings.append("Thiếu ngày ban hành.")
    if not issuing_authority:
        warnings.append("Thiếu cơ quan ban hành.")
    if not articles:
        warnings.append("Không phát hiện điều khoản chính.")
    return warnings
