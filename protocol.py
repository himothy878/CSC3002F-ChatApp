def receive_message(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        data += chunk

    header_part, body_part = data.split(b"\r\n\r\n", 1)
    headers = header_part.decode()
    content_length = 0

    for line in headers.split("\r\n"):
        if line.lower().startswith("length"):
            content_length = int(line.split(":" )[1].strip())

    while len(body_part) < content_length:
        body_part += sock.recv(4096)

    return (header_part + b"\r\n\r\n" + body_part).decode()

def build_response(command, body=""):
    return f"{command}\r\nContent-Length: {len(body)}\r\n\r\n{body}"