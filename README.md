# Legal Knowledge Factory / Knowledge Builder

Ứng dụng Python/FastAPI giúp tải lên văn bản pháp luật Việt Nam dạng `.docx` hoặc `.pdf`, phân tích cấu trúc và tạo **Legal Knowledge Pack 1.0** để nạp vào Custom GPT.

## Tính năng MVP

- Giao diện web tải file lên, hiển thị tên file và tải kết quả `.zip`.
- Hỗ trợ `.docx` bằng `python-docx`.
- Hỗ trợ `.pdf` bằng `PyMuPDF`, tự thử `pdfplumber` nếu PyMuPDF không đọc được.
- Nhận diện loại văn bản: Luật, Nghị định, Thông tư, Quyết định, Công văn.
- Trích metadata: loại văn bản, số/ký hiệu, cơ quan ban hành, ngày ban hành, tên văn bản, căn cứ pháp lý, phạm vi áp dụng.
- Tách cấu trúc phần mở đầu, căn cứ, Chương, Mục, Tiểu mục, Điều, Khoản, Điểm bằng regex + state machine.
- Với Nghị định, chỉ tách Điều từ phần nội dung chính và dừng trước phần Phụ lục.
- Đưa Phụ lục, biểu mẫu, bảng kèm theo sang thư mục `appendices/`.
- Sinh Knowledge Pack gồm metadata, mục lục, giải thích từ ngữ, bảng tra cứu, chủ đề, FAQ, system prompt, nội dung gốc, validation report, articles, appendices và indexes.
- Sinh từ khóa pháp lý/nghiệp vụ/công nghệ/quản lý nhà nước theo catalogue thuật ngữ, không dựa vào đếm từ phổ thông.
- Có kiểm tra định dạng, giới hạn dung lượng file cấu hình được và log xử lý.
- Không gửi dữ liệu ra ngoài ở phiên bản MVP.

## Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Chạy ứng dụng

```powershell
uvicorn app.main:app --reload
```

Mở trình duyệt tại:

```text
http://127.0.0.1:8000
```

Nếu `uvicorn` chưa được nhận diện trong PowerShell, chạy qua Python trong môi trường ảo:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Chạy bằng CLI

```powershell
.\.venv\Scripts\python.exe main.py --input uploads\224_2026_ND-CP_712767.docx --output knowledge_packs
```

Kết quả sẽ nằm trong:

```text
knowledge_packs/{document_number}/
knowledge_packs/{document_number}.zip
```

## Triển khai lên web

Xem hướng dẫn trong [DEPLOYMENT.md](DEPLOYMENT.md). Project đã có sẵn:

- `Dockerfile`
- `render.yaml`
- `Procfile`
- `netlify.toml`
- `web/`
- endpoint health check `/healthz`

## Kiểm thử nhanh

Sau khi cài dependencies, có thể chạy smoke test end-to-end:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test_app.py
```

Smoke test sẽ tự tạo một file `.docx` mẫu, khởi động server tạm thời, upload file và kiểm tra `.zip` đầu ra có đủ các file Knowledge Pack chính.

## Cấu hình

Giới hạn dung lượng mặc định là `25 MB`. Có thể thay đổi bằng biến môi trường:

```powershell
$env:MAX_UPLOAD_MB = "50"
uvicorn app.main:app --reload
```

## Cấu trúc Knowledge Pack

Sau khi xử lý, file `.zip` chứa:

```text
00_metadata.yaml
01_muc_luc.md
02_giai_thich_tu_ngu.md
03_bang_tra_cuu.md
04_chu_de.md
05_faq.md
06_prompt_system.md
07_noi_dung_goc.md
validation_report.md
articles/
  dieu_001.md
  dieu_002.md
  ...
appendices/
  phu_luc_01.md
  mau_so_01.md
  ...
indexes/
  keyword_index.md
  topic_index.md
  article_index.json
  citation_index.json
```

Mỗi file điều khoản có các phần:

- Số điều
- Tên điều
- Nội dung gốc
- Tóm tắt ngắn
- Từ khóa
- Chủ đề
- Điều khoản liên quan
- Câu hỏi thường gặp

## Validation

Sau khi sinh pack, ứng dụng tạo `validation_report.md` với kết luận:

- `PASS`: đủ điều kiện dùng.
- `WARNING`: dùng được nhưng có cảnh báo cần rà soát.
- `FAIL`: không cho tải bản chính thức trên giao diện web.

## Lưu ý

MVP ưu tiên giữ nguyên nội dung gốc và tạo cấu trúc tra cứu nhanh. Với PDF scan ảnh, cần OCR trước khi tải lên vì bản hiện tại chỉ đọc được text layer có sẵn trong PDF.
