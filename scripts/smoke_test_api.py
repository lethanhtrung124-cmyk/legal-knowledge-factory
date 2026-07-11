import http.client
from pathlib import Path


def main() -> None:
    boundary = "----codexboundary"
    source = Path("data/test_input.docx")
    output = Path("data/api_test.zip")
    data = source.read_bytes()

    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{source.name}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n"
        "\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = head + data + tail

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    connection = http.client.HTTPConnection("127.0.0.1", 8001, timeout=30)
    connection.request("POST", "/api/knowledge-pack", body, headers)
    response = connection.getresponse()
    payload = response.read()

    print(response.status, len(payload))
    if response.status != 200:
        raise SystemExit(payload[:500].decode("utf-8", errors="replace"))

    output.write_bytes(payload)
    print(output)


if __name__ == "__main__":
    main()
