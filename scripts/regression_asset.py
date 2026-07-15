import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.document_processor import parse_document
from app.knowledge_pack import build_knowledge_pack
from app.legal_asset import build_legal_knowledge_asset, write_legal_asset_outputs


DEFAULT_PATTERNS = (
    "57-NQ",
    "148_2025",
    "194_2025",
    "224_2026",
    "278_2025",
    "292_QD",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Legal Knowledge Asset regression corpus")
    parser.add_argument("--corpus", required=True, help="Folder containing .docx/.pdf regression documents")
    parser.add_argument("--output", default="knowledge_packs", help="Output folder")
    parser.add_argument("--extra-file", action="append", default=[], help="Additional .docx/.pdf document to include")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    output = Path(args.output)
    files = [
        path
        for path in sorted(corpus.iterdir())
        if path.is_file() and path.suffix.lower() in {".docx", ".pdf"} and any(pattern in path.name for pattern in DEFAULT_PATTERNS)
    ]
    for extra in args.extra_file:
        extra_path = Path(extra)
        if extra_path.exists() and extra_path.suffix.lower() in {".docx", ".pdf"} and extra_path not in files:
            files.append(extra_path)
    rows: list[dict[str, object]] = []
    for path in files:
        parsed = parse_document(path)
        asset = build_legal_knowledge_asset(parsed)
        export_error = ""
        try:
            outputs = write_legal_asset_outputs(asset, output)
        except ValueError as exc:
            export_error = str(exc)
            safe = (asset.document_number or path.stem).replace("/", "_").replace(".", "_")
            outputs = {
                "json": output / f"LEGAL_ASSET_{safe}.json",
                "markdown": output / f"LEGAL_ASSET_{safe}.md",
            }
        zip_path = build_knowledge_pack(parsed, output, emit_gpt_markdown=False)
        rows.append(
            {
                "source_file": str(path),
                "knowledge_pack": str(zip_path),
                "legal_asset_json": str(outputs["json"]),
                "legal_asset_markdown": str(outputs["markdown"]),
                "validation_status": asset.validation["status"],
                "stats": asset.stats,
                "error_codes": [item["code"] for item in asset.validation["errors"]],
                "warning_codes": [item["code"] for item in asset.validation["warnings"]],
                "export_error": export_error,
            }
        )

    status = "FAIL" if any(row["validation_status"] != "PASS" or row["export_error"] for row in rows) else "PASS"
    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / "LEGAL_ASSET_REGRESSION_SUMMARY.json"
    summary_path.write_text(
        json.dumps({"status": status, "count": len(rows), "rows": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(summary_path)
    print(f"status={status} count={len(rows)}")
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
