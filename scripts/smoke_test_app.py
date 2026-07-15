import http.client
import sys
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path

import uvicorn
from docx import Document


HOST = "127.0.0.1"
PORT = 8010
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


def create_sample_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    paragraphs = [
        "CH\u00cdNH PH\u1ee6",
        "S\u1ed1: 12/2026/N\u0110-CP",
        "\u0110\u1ed9c l\u1eadp - T\u1ef1 do - H\u1ea1nh ph\u00fac",
        "H\u00e0 N\u1ed9i, ng\u00e0y 09 th\u00e1ng 7 n\u0103m 2026",
        "NGH\u1eca \u0110\u1ecaNH",
        "Quy \u0111\u1ecbnh v\u1ec1 ki\u1ec3m th\u1eed Knowledge Pack",
        "C\u0103n c\u1ee9 Lu\u1eadt T\u1ed5 ch\u1ee9c Ch\u00ednh ph\u1ee7;",
        "Ch\u01b0\u01a1ng I Quy \u0111\u1ecbnh chung",
    ]
    for index in range(1, 93):
        paragraphs.extend(
            [
                f"\u0110i\u1ec1u {index}. N\u1ed9i dung nghi\u1ec7p v\u1ee5 {index}",
                f"1. C\u01a1 quan, t\u1ed5 ch\u1ee9c, c\u00e1 nh\u00e2n th\u1ef1c hi\u1ec7n tr\u00e1ch nhi\u1ec7m, h\u1ed3 s\u01a1, tr\u00ecnh t\u1ef1, th\u1ee7 t\u1ee5c theo quy \u0111\u1ecbnh t\u1ea1i \u0110i\u1ec1u {index}.",
                "a) \u0110i\u1ec3m nghi\u1ec7p v\u1ee5 \u0111\u01b0\u1ee3c ghi nh\u1eadn \u0111\u1ec3 ki\u1ec3m tra t\u00e1ch \u0111i\u1ec3m.",
            ]
        )
    paragraphs.extend(
        [
            "PH\u1ee4 L\u1ee4C I",
            "M\u1eabu bi\u1ec3u k\u00e8m theo Ngh\u1ecb \u0111\u1ecbnh",
            "\u0110i\u1ec1u 93. D\u00f2ng n\u00e0y n\u1eb1m trong ph\u1ee5 l\u1ee5c v\u00e0 kh\u00f4ng \u0111\u01b0\u1ee3c coi l\u00e0 \u0111i\u1ec1u kho\u1ea3n ch\u00ednh.",
        ]
    )
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def wait_for_server() -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            connection = http.client.HTTPConnection(HOST, PORT, timeout=2)
            connection.request("GET", "/")
            response = connection.getresponse()
            response.read()
            if response.status == 200:
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("Server did not start in time.")


def upload_docx(path: Path) -> tuple[bytes, dict[str, str]]:
    boundary = "----codexboundary"
    data = path.read_bytes()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n"
        "\r\n"
    ).encode("utf-8")
    body = head + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("POST", "/api/knowledge-pack", body, headers)
    response = connection.getresponse()
    payload = response.read()
    if response.status != 200:
        raise RuntimeError(payload[:500].decode("utf-8", errors="replace"))
    headers = {
        "gpt_markdown": response.getheader("X-GPT-Knowledge-Url") or "",
        "asset_json": response.getheader("X-Legal-Asset-Json-Url") or "",
        "asset_structure": response.getheader("X-Legal-Asset-Structure-Url") or "",
        "asset_markdown": response.getheader("X-Legal-Asset-Markdown-Url") or "",
        "asset_word": response.getheader("X-Legal-Asset-Word-Url") or "",
        "asset_validation": response.getheader("X-Legal-Asset-Validation-Url") or "",
        "asset_runtime_log": response.getheader("X-Legal-Asset-Runtime-Log-Url") or "",
    }
    return payload, headers


def download_text(path_url: str) -> str:
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("GET", path_url)
    response = connection.getresponse()
    payload = response.read()
    if response.status != 200:
        raise RuntimeError(payload[:500].decode("utf-8", errors="replace"))
    return payload.decode("utf-8")


def download_bytes(path_url: str) -> bytes:
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("GET", path_url)
    response = connection.getresponse()
    payload = response.read()
    if response.status != 200:
        raise RuntimeError(payload[:500].decode("utf-8", errors="replace"))
    return payload


def main() -> None:
    sample_path = Path("data/test_input.docx")
    create_sample_docx(sample_path)

    config = uvicorn.Config("app.main:app", host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    wait_for_server()
    payload, urls = upload_docx(sample_path)
    markdown_url = urls["gpt_markdown"]
    if not markdown_url.startswith("/api/knowledge-markdown/GPT_KNOWLEDGE_"):
        raise RuntimeError(f"Missing GPT Markdown download URL: {markdown_url}")
    markdown = download_text(markdown_url)
    if not urls["asset_json"].startswith("/api/legal-asset/LEGAL_ASSET_"):
        raise RuntimeError(f"Missing Legal Asset JSON download URL: {urls['asset_json']}")
    asset_json = download_text(urls["asset_json"])
    asset_structure = download_text(urls["asset_structure"])
    asset_markdown = download_text(urls["asset_markdown"])
    asset_word = download_bytes(urls["asset_word"])
    asset_validation = download_text(urls["asset_validation"])
    asset_runtime_log = download_text(urls["asset_runtime_log"])
    names = zipfile.ZipFile(BytesIO(payload)).namelist()
    archive = zipfile.ZipFile(BytesIO(payload))
    required = {
        "00_metadata.yaml",
        "01_muc_luc.md",
        "02_giai_thich_tu_ngu.md",
        "03_bang_tra_cuu.md",
        "04_chu_de.md",
        "05_faq.md",
        "06_prompt_system.md",
        "07_noi_dung_goc.md",
        "validation_report.md",
        "articles/dieu_001.md",
        "articles/dieu_092.md",
        "appendices/phu_luc_01.md",
        "indexes/keyword_index.md",
        "indexes/topic_index.md",
        "indexes/article_index.json",
        "indexes/citation_index.json",
    }
    missing = sorted(required.difference(names))
    if missing:
        raise RuntimeError(f"Missing files: {missing}")
    if "articles/dieu_093.md" in names:
        raise RuntimeError("Appendix content was incorrectly parsed as article 93.")
    if any(name.startswith("GPT_KNOWLEDGE_") for name in names):
        raise RuntimeError("GPT Markdown should be downloaded independently, not embedded in the zip.")
    metadata = archive.read("00_metadata.yaml").decode("utf-8")
    faq = archive.read("05_faq.md").decode("utf-8")
    prompt = archive.read("06_prompt_system.md").decode("utf-8")
    appendix = archive.read("appendices/phu_luc_01.md").decode("utf-8")
    article_1 = archive.read("articles/dieu_001.md").decode("utf-8")
    validation = archive.read("validation_report.md").decode("utf-8")
    checks = {
        "document_type": "document_type: \"Nghị định\"" in metadata,
        "document_number": "document_number: \"12/2026/NĐ-CP\"" in metadata,
        "issued_date": "issued_date: \"09/07/2026\"" in metadata,
        "issuing_authority": "issuing_authority: \"Chính phủ\"" in metadata,
        "article_count": "article_count: 92" in metadata,
        "chapter_count": "chapter_count: 1" in metadata,
        "faq_business": "FAQ theo tình huống nghiệp vụ" in faq,
        "faq_scenario": "Khi xử lý nghiệp vụ" in faq,
        "faq_article_92": "Điều 92. Nội dung nghiệp vụ 92" in faq,
        "article_business_keywords": "business_keywords:" in article_1,
        "keyword_ho_so": "hồ sơ" in article_1,
        "keyword_trinh_tu": "trình tự thủ tục" in article_1,
        "prompt_appendix": "Không được coi phụ lục" in prompt,
        "prompt_no_inference": "không suy luận" in prompt.lower(),
        "prompt_priority": "Thứ tự ưu tiên nguồn" in prompt,
        "appendix_note": "Đây không phải là điều khoản chính" in appendix,
        "validation_status": "- Kết luận: PASS" in validation or "- Kết luận: WARNING" in validation,
        "merged_markdown_title": markdown.startswith("# Quy định về kiểm thử Knowledge Pack"),
        "merged_markdown_original": "Điều 92. Nội dung nghiệp vụ 92" in markdown,
        "merged_markdown_no_prompt": "System Prompt" not in markdown,
        "asset_json_schema": '"schema_version": "2.0"' in asset_json,
        "asset_structure": '"asset_id"' in asset_structure and '"tree"' in asset_structure,
        "asset_markdown_truth": "## SOURCE OF TRUTH" in asset_markdown,
        "asset_word_docx": asset_word.startswith(b"PK"),
        "asset_validation_report": "# Asset Validation" in asset_validation,
        "asset_runtime_log": "pipeline=LegalKnowledgeAsset" in asset_runtime_log,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"Nghị định metadata, FAQ, prompt, or appendix checks failed: {failed}")

    server.should_exit = True
    thread.join(timeout=10)
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
