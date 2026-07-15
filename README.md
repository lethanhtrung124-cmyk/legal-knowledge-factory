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

Để sinh thêm **Legal Knowledge Asset 2.0** song song với Knowledge Pack cũ:

```powershell
.\.venv\Scripts\python.exe main.py --input uploads\224_2026_ND-CP_712767.docx --output knowledge_packs --asset
```

Các file bổ sung:

```text
LEGAL_ASSET_{document_number}.json
LEGAL_ASSET_{document_number}.md
MIGRATION_REPORT_{document_number}.md
ASSET_VALIDATION_{document_number}.md
REGRESSION_SUMMARY_{document_number}.md
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

Chạy regression cho bộ văn bản chuẩn:

```powershell
.\.venv\Scripts\python.exe scripts\regression_asset.py --corpus "D:\3. Ca nhan\3. VB CNTT, CĐS" --output knowledge_packs
```

Script tạo `LEGAL_ASSET_REGRESSION_SUMMARY.json` và trả mã lỗi nếu có asset `FAIL`.

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

## Legal Knowledge Asset 2.0

Asset 2.0 bổ sung mô hình node cha-con để xử lý văn bản có nội dung ban hành kèm theo:

```text
MAIN_DOCUMENT
└── ISSUED_CONTENT
    ├── PROVISION
    ├── APPENDIX
    ├── FORM
    ├── TABLE
    └── REFERENCE
```

Mỗi node có các trường chính:

```json
{
  "id": "",
  "node_type": "",
  "number": "",
  "title": "",
  "parent_id": "",
  "order": 0,
  "original_text": "",
  "normalized_text": "",
  "source_location": {},
  "checksum": "",
  "review_status": ""
}
```

Quy tắc nhận diện `ISSUED_CONTENT` dùng nhiều tín hiệu: câu “ban hành kèm theo”, heading như `HƯỚNG DẪN`, `QUY CHẾ`, `KHUNG`, `DANH MỤC`, dòng xác nhận “Ban hành kèm theo Quyết định số...” và vị trí sau phần ký. Heading `Phụ lục` hoặc `Mẫu số` không được tự động coi là `ISSUED_CONTENT`.

Quy tắc phân biệt `APPENDIX` và `REFERENCE`: chỉ tạo `APPENDIX` khi “Phụ lục/Mẫu số/Biểu mẫu” là heading riêng tại biên khối mới và có nội dung đi kèm; các câu như “theo Phụ lục IV” hoặc ô bảng chỉ dẫn chiếu được giữ thành `REFERENCE`.

ID ổn định theo phạm vi:

```text
{document}-MAIN
{document}-MAIN-ART1
{document}-ISSUED01
{document}-ISSUED01-ART1
{document}-ISSUED01-APP-I
{document}-ISSUED01-FORM-01
```

Để thêm loại tài liệu ban hành kèm theo mới, cập nhật `ISSUED_CONTENT_HEADING_RE` trong `app/legal_asset.py`, bổ sung từ khóa vào rule tín hiệu nếu cần, rồi thêm test tương ứng trong `tests/test_legal_asset.py`.

## Lưu ý

MVP ưu tiên giữ nguyên nội dung gốc và tạo cấu trúc tra cứu nhanh. Với PDF scan ảnh, cần OCR trước khi tải lên vì bản hiện tại chỉ đọc được text layer có sẵn trong PDF.
