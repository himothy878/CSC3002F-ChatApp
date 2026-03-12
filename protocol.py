def receive_message(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        data += chunk

    header_part, body_part = data.split(b"\r\n\r\n", 1)
    headers = header_part.decode(errors="replace")
    content_length = 0

    for line in headers.split("\r\n"):
        lower = line.lower()
        if lower.startswith("content-length:") or lower.startswith("length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break

    while len(body_part) < content_length:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        body_part += chunk

    return (header_part + b"\r\n\r\n" + body_part[:content_length]).decode(errors="replace")


def build_response(command, body=""):
    return f"{command}\r\nContent-Length: {len(body)}\r\n\r\n{body}"