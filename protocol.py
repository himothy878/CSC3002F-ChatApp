# protocol.py

def receive_message(sock):
    """
    Receives a CCP/1.0 message from a socket.
    Handles Content-Length and ensures full message is read.
    """
    data = b""

    # Read until we get full headers
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        data += chunk

    header_part, body_part = data.split(b"\r\n\r\n", 1)
    headers = header_part.decode()

    # Extract Content-Length
    content_length = 0
    for line in headers.split("\r\n"):
        if line.lower().startswith("content-length"):
            content_length = int(line.split(":")[1].strip())

    # Read body if needed
    while len(body_part) < content_length:
        chunk = sock.recv(4096)
        if not chunk:
            break
        body_part += chunk

    full_message = header_part + b"\r\n\r\n" + body_part
    return full_message.decode()


def build_response(command, body=""):
    """
    Builds a CCP/1.0 formatted response message.
    """
    response = f"{command}\r\n"
    response += f"Content-Length: {len(body)}\r\n"
    response += "\r\n"
    response += body
    return response