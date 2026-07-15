const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const submitButton = document.getElementById("submitButton");
const statusBox = document.getElementById("status");
const downloadArea = document.getElementById("downloadArea");
const form = document.getElementById("packForm");

const apiBaseUrl = window.LEGAL_KNOWLEDGE_API_BASE_URL || "";

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
    const response = await fetch(`${apiBaseUrl}/api/knowledge-pack`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Không xử lý được file." }));
      const report = error.validation_report ? `\n\n${error.validation_report}` : "";
      throw new Error((error.detail || "Không xử lý được file.") + report);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const baseName = file.name.replace(/\.[^.]+$/, "");
    const validationStatus = response.headers.get("X-Validation-Status");
    const link = document.createElement("a");
    link.href = url;
    link.download = `${baseName}_knowledge_pack.zip`;
    link.className = "download";
    link.textContent = "Tải file .zip";
    downloadArea.appendChild(link);

    const markdownUrl = response.headers.get("X-GPT-Knowledge-Url");
    if (markdownUrl) {
      const markdownLink = document.createElement("a");
      markdownLink.href = markdownUrl.startsWith("http") ? markdownUrl : `${apiBaseUrl}${markdownUrl}`;
      markdownLink.download = `${baseName}_gpt_knowledge.md`;
      markdownLink.className = "download";
      markdownLink.textContent = "Tải file GPT Markdown";
      downloadArea.appendChild(markdownLink);
    }

    const assetLinks = [
      ["X-Legal-Asset-Json-Url", "Tải Legal Asset JSON", `${baseName}_legal_asset.json`],
      ["X-Legal-Asset-Structure-Url", "Tải structure.json", `${baseName}_structure.json`],
      ["X-Legal-Asset-Markdown-Url", "Tải Legal Asset Markdown", `${baseName}_legal_asset.md`],
      ["X-Legal-Asset-Word-Url", "Tải Legal Asset Word", `${baseName}_legal_asset.docx`],
      ["X-Legal-Asset-Migration-Url", "Tải Migration Report", `${baseName}_migration_report.md`],
      ["X-Legal-Asset-Validation-Url", "Tải Asset Validation", `${baseName}_asset_validation.md`],
      ["X-Legal-Asset-Regression-Url", "Tải Regression Summary", `${baseName}_regression_summary.md`],
      ["X-Legal-Asset-Runtime-Log-Url", "Tải Runtime Log", `${baseName}_runtime.log`],
    ];
    for (const [header, label, downloadName] of assetLinks) {
      const assetUrl = response.headers.get(header);
      if (!assetUrl) continue;
      const assetLink = document.createElement("a");
      assetLink.href = assetUrl.startsWith("http") ? assetUrl : `${apiBaseUrl}${assetUrl}`;
      assetLink.download = downloadName;
      assetLink.className = "download";
      assetLink.textContent = label;
      downloadArea.appendChild(assetLink);
    }

    statusBox.textContent = validationStatus
      ? `Hoàn tất. Validation: ${validationStatus}. Knowledge Pack đã sẵn sàng.`
      : "Hoàn tất. Knowledge Pack đã sẵn sàng.";
  } catch (error) {
    statusBox.textContent = error.message;
    statusBox.classList.add("error");
  } finally {
    submitButton.disabled = false;
  }
});
