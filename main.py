import argparse
import sys
from pathlib import Path

from app.document_processor import parse_document
from app.knowledge_pack import build_knowledge_pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Legal Knowledge Pack 1.0")
    parser.add_argument("--input", required=True, help="Path to .docx or .pdf legal document")
    parser.add_argument("--output", default="knowledge_packs", help="Output folder for knowledge packs")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_root = Path(args.output)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    parsed = parse_document(input_path)
    zip_path = build_knowledge_pack(parsed, output_root=output_root)
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
