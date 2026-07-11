# Deploy Legal Knowledge Factory len web

Ung dung la FastAPI app, co the deploy bang Render, Railway, Fly.io, VPS hoac Docker.

## Cach de nhat: Render

1. Day thu muc project len GitHub.
2. Vao Render va tao **New Web Service**.
3. Ket noi repo GitHub chua project nay.
4. Render se doc file `render.yaml` neu ban chon deploy bang Blueprint.
5. Neu tao Web Service thu cong, dung cau hinh:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /healthz
```

6. Them bien moi truong neu can:

```text
MAX_UPLOAD_MB=25
```

Sau khi deploy xong, Render se cap URL dang:

```text
https://legal-knowledge-factory.onrender.com
```

## Deploy bang Docker

Build image:

```powershell
docker build -t legal-knowledge-factory .
```

Chay local bang Docker:

```powershell
docker run --rm -p 8000:8000 -e MAX_UPLOAD_MB=25 legal-knowledge-factory
```

Mo:

```text
http://127.0.0.1:8000
```

## Luu y khi dua len public web

- Ban MVP xu ly file tren server deploy, khong gui du lieu sang API ben ngoai.
- Thu muc `data/uploads` va `data/outputs` la tam thoi; tren cac host free co the bi xoa khi service restart.
- Khong nen upload van ban mat/nhay cam len public hosting neu chua co cau hinh bao mat, xoa file dinh ky va gioi han truy cap.
- Neu can dung noi bo co bao mat hon, nen deploy tren VPS/private server va dat dang sau VPN hoac dang nhap.

## Frontend tren Netlify

Thu muc frontend tinh nam tai:

```text
web/
  index.html
  styles.css
  app.js
```

Netlify dung file `netlify.toml` o thu muc goc:

```toml
[build]
  publish = "web"
  command = ""
```

Truoc khi deploy public, sua dong proxy trong `netlify.toml`:

```toml
to = "https://your-fastapi-backend.onrender.com/api/:splat"
```

Khong de `http://127.0.0.1:8000` khi deploy Netlify public, vi dia chi nay chi ton tai tren may local cua ban.

Trong Netlify:

```text
Base directory: de trong
Build command: de trong
Publish directory: web
```
