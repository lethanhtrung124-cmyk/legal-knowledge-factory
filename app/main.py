import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import ALLOWED_EXTENSIONS, FRONTEND_ORIGIN, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, OUTPUT_DIR, UPLOAD_DIR
from .document_processor import parse_document
from .knowledge_pack import build_knowledge_pack

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Legal Knowledge Factory", version="0.1.0", lifespan=lifespan)

allowed_origins = [
    origin.strip()
    for origin in FRONTEND_ORIGIN.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Validation-Status"],
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/knowledge-pack", response_model=None)
async def create_knowledge_pack(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .docx hoặc .pdf.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File tải lên rỗng.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File vượt quá giới hạn {MAX_UPLOAD_MB} MB.")

    upload_path = UPLOAD_DIR / f"{uuid4().hex}_{original_name}"
    upload_path.write_bytes(content)
    logger.info("Uploaded %s (%s bytes)", original_name, len(content))

    try:
        parsed = parse_document(upload_path)
        zip_path = build_knowledge_pack(parsed)
        report_path = zip_path.with_suffix("") / "validation_report.md"
        validation_report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        if "- Kết luận: FAIL" in validation_report:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Knowledge Pack chưa đạt validation PASS/WARNING.",
                    "validation_report": validation_report,
                },
            )
    except ValueError as exc:
        logger.warning("Processing failed for %s: %s", original_name, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected processing error for %s", original_name)
        raise HTTPException(status_code=500, detail="Có lỗi khi xử lý văn bản.") from exc

    download_name = f"{Path(original_name).stem}_knowledge_pack.zip"
    response = FileResponse(zip_path, media_type="application/zip", filename=download_name)
    if validation_report:
        status_line = next((line for line in validation_report.splitlines() if line.startswith("- Kết luận:")), "")
        response.headers["X-Validation-Status"] = status_line.replace("- Kết luận:", "").strip()
    return response


INDEX_HTML = """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Legal Knowledge Factory</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #16202a;
      --muted: #5b6876;
      --line: #d7dde3;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-dark: #0b5f59;
      --bg: #f5f7f8;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    main {
      width: min(860px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0;
    }
    h1 {
      margin: 0 0 8px;
      font-size: clamp(30px, 5vw, 46px);
      line-height: 1.08;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0 0 28px;
      color: var(--muted);
      font-size: 17px;
      line-height: 1.5;
    }
    .workspace {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 18px 42px rgba(22, 32, 42, 0.08);
    }
    .upload-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 14px;
      align-items: center;
    }
    .file-label {
      display: flex;
      min-height: 58px;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      border: 1px dashed #9aa7b4;
      border-radius: 8px;
      padding: 14px 16px;
      background: #fbfcfd;
      cursor: pointer;
    }
    .file-name {
      min-width: 0;
      overflow-wrap: anywhere;
      color: var(--muted);
    }
    .file-pill {
      flex: 0 0 auto;
      color: var(--accent);
      font-weight: 700;
    }
    input[type="file"] {
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }
    button, .download {
      min-height: 44px;
      border: 0;
      border-radius: 8px;
      padding: 0 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      background: var(--accent);
      color: white;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      white-space: nowrap;
    }
    button:hover, .download:hover { background: var(--accent-dark); }
    button:disabled {
      cursor: not-allowed;
      background: #9aa7b4;
    }
    .status {
      margin-top: 18px;
      min-height: 24px;
      color: var(--muted);
      line-height: 1.45;
    }
    .status.error { color: var(--danger); }
    .download-area {
      margin-top: 18px;
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .notes {
      margin-top: 24px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }
    @media (max-width: 680px) {
      main { padding: 28px 0; }
      .workspace { padding: 18px; }
      .upload-row { grid-template-columns: 1fr; }
      button { width: 100%; }
      .file-label { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <main>
    <h1>Legal Knowledge Factory</h1>
    <p class="subtitle">Tải lên văn bản pháp luật Việt Nam dạng .docx hoặc .pdf và tạo Knowledge Pack dạng .zip để nạp vào Custom GPT.</p>

    <section class="workspace">
      <form id="packForm">
        <div class="upload-row">
          <label class="file-label" for="fileInput">
            <span id="fileName" class="file-name">Chưa chọn file</span>
            <span class="file-pill">Chọn .docx hoặc .pdf</span>
          </label>
          <input id="fileInput" type="file" accept=".docx,.pdf" />
          <button id="submitButton" type="submit" disabled>Tạo Knowledge Pack</button>
        </div>
      </form>
      <div id="status" class="status"></div>
      <div id="downloadArea" class="download-area"></div>
      <div class="notes">MVP xử lý cục bộ trên máy chủ đang chạy ứng dụng, kiểm tra định dạng file, giới hạn dung lượng cấu hình bằng biến môi trường MAX_UPLOAD_MB và không gửi dữ liệu ra ngoài.</div>
    </section>
  </main>

  <script>
    const fileInput = document.getElementById("fileInput");
    const fileName = document.getElementById("fileName");
    const submitButton = document.getElementById("submitButton");
    const statusBox = document.getElementById("status");
    const downloadArea = document.getElementById("downloadArea");
    const form = document.getElementById("packForm");

    fileInput.addEventListener("change", () => {
      const file = fileInput.files[0];
      fileName.textContent = file ? file.name : "Chưa chọn file";
      submitButton.disabled = !file;
      statusBox.textContent = "";
      statusBox.classList.remove("error");
      downloadArea.innerHTML = "";
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const file = fileInput.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append("file", file);
      submitButton.disabled = true;
      statusBox.textContent = "Đang đọc văn bản và tạo Knowledge Pack...";
      statusBox.classList.remove("error");
      downloadArea.innerHTML = "";

      try {
        const response = await fetch("/api/knowledge-pack", { method: "POST", body: formData });
        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: "Không xử lý được file." }));
          const report = error.validation_report ? "\\n\\n" + error.validation_report : "";
          throw new Error((error.detail || "Không xử lý được file.") + report);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const baseName = file.name.replace(/\\.[^.]+$/, "");
        const link = document.createElement("a");
        link.href = url;
        link.download = `${baseName}_knowledge_pack.zip`;
        link.className = "download";
        link.textContent = "Tải file .zip";
        downloadArea.appendChild(link);
        statusBox.textContent = "Hoàn tất. Knowledge Pack đã sẵn sàng.";
      } catch (error) {
        statusBox.textContent = error.message;
        statusBox.classList.add("error");
      } finally {
        submitButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""
