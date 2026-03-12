import os
import socket
import threading
import time
from typing import Callable, Dict, Optional

from protocol import build_response, receive_message

TCP_PORT = 12345
UDP_PORT = 12346
BUFFER_SIZE = 4096


class ClientNetwork:
    def __init__(self):
        self.alias = ""
        self.server_ip = ""
        self.seq = 2

        self.tcp = None
        self.udp = None
        self.p2p = None
        self.udp_port = 0
        self.p2p_port = 0

        self.running = False
        self.pending_file_path = None

        self.on_users: Optional[Callable[[list], None]] = None
        self.on_groups: Optional[Callable[[list], None]] = None
        self.on_ack: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_message: Optional[Callable[[Dict[str, str]], None]] = None
        self.on_file_request: Optional[Callable[[str, str], None]] = None
        self.on_whois: Optional[Callable[[str], None]] = None
        self.on_udp: Optional[Callable[[str], None]] = None
        self.on_disconnect: Optional[Callable[[str], None]] = None

    def connect(self, server_ip: str, alias: str, password: str) -> None:
        self.server_ip = server_ip.strip()
        self.alias = alias.strip()
        if not self.server_ip or not self.alias or not password:
            raise ValueError("Server IP, username and password are required")

        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.connect((self.server_ip, TCP_PORT))

        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("0.0.0.0", 0))
        self.udp_port = self.udp.getsockname()[1]

        self.p2p = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.p2p.bind(("0.0.0.0", 0))
        self.p2p_port = self.p2p.getsockname()[1]
        self.p2p.listen()

        body = password
        login_pkt = (
            f"CMD LOGIN CCP/1.0\r\n"
            f"From: {self.alias}\r\n"
            f"Seq: 1\r\n"
            f"Length: {len(body)}\r\n\r\n"
            f"{body}"
        )
        self.tcp.sendall(login_pkt.encode())
        resp = receive_message(self.tcp)
        if not resp or "ACK CCP/1.0" not in resp:
            raise RuntimeError("Authentication failed")

        reg = build_response(
            "CMD REGISTER CCP/1.0",
            f"From: {self.alias}\r\nUDP-Port: {self.udp_port}\r\nP2P-Port: {self.p2p_port}\r\n",
        )
        self.tcp.sendall(reg.encode())

        self.running = True
        threading.Thread(target=self._tcp_loop, daemon=True).start()
        threading.Thread(target=self._udp_loop, daemon=True).start()
        threading.Thread(target=self._p2p_loop, daemon=True).start()

    def close(self):
        self.running = False
        for sock in (self.tcp, self.udp, self.p2p):
            try:
                if sock:
                    sock.close()
            except Exception:
                pass

    def request_lists(self):
        if not self.running:
            return
        self.tcp.sendall(
            build_response(
                "CMD LIST_USERS CCP/1.0",
                f"From: {self.alias}\r\nSeq: {self.seq}\r\nLength: 0\r\n\r\n",
            ).encode()
        )
        self.tcp.sendall(
            build_response(
                "CMD LIST_GROUPS CCP/1.0",
                f"From: {self.alias}\r\nSeq: {self.seq}\r\nLength: 0\r\n\r\n",
            ).encode()
        )
        self.seq += 1

    def join_group(self, group: str):
        self._send_ctrl("CMD JOIN_GROUP CCP/1.0", to_value=group)

    def leave_group(self, group: str):
        self._send_ctrl("CMD LEAVE_GROUP CCP/1.0", to_value=group)

    def whois(self, user: str):
        self._send_ctrl("CMD WHOIS CCP/1.0", to_value=user)

    def request_file(self, target: str, path: str):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        self.pending_file_path = path
        self._send_ctrl("CMD FILE_REQUEST CCP/1.0", to_value=target, body=os.path.basename(path))

    def send_chat(self, target: str, message: str, channel: str):
        if not self.running:
            return
        packet = build_response(
            "DATA MESSAGE CCP/1.0",
            (
                f"Channel: {channel}\r\n"
                f"From: {self.alias}\r\n"
                f"To: {target}\r\n"
                f"Seq: {self.seq}\r\n"
                f"Length: {len(message)}\r\n\r\n"
                f"{message}"
            ),
        )
        self.tcp.sendall(packet.encode())
        self.udp.sendto(f"TYPING {self.alias}".encode(), (self.server_ip, UDP_PORT))
        self.seq += 1

    def _send_ctrl(self, cmd: str, to_value: str = "", body: str = ""):
        headers = [f"From: {self.alias}", f"Seq: {self.seq}"]
        if to_value:
            headers.append(f"To: {to_value}")
        headers.append(f"Length: {len(body)}")
        payload = "\r\n".join(headers) + "\r\n\r\n" + body
        self.tcp.sendall(build_response(cmd, payload).encode())
        self.seq += 1

    def _extract_body(self, msg: str) -> str:
        return msg.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in msg else ""

    def _parse_lines(self, body: str) -> list:
        values = [line.strip() for line in body.splitlines() if line.strip()]
        return [line for line in values if line.lower() != "(no groups)"]

    def _headers(self, msg: str) -> Dict[str, str]:
        parts = msg.split("\r\n\r\n", 1)[0].split("\r\n")
        headers = {}
        for line in parts[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        return headers

    def _tcp_loop(self):
        try:
            while self.running:
                msg = receive_message(self.tcp)
                if not msg:
                    continue

                if "CTRL USERS_LIST" in msg:
                    users = [u for u in self._parse_lines(self._extract_body(msg)) if u != self.alias]
                    if self.on_users:
                        self.on_users(users)
                    continue

                if "CTRL GROUPS_LIST" in msg:
                    groups = self._parse_lines(self._extract_body(msg))
                    if self.on_groups:
                        self.on_groups(groups)
                    continue

                if "CTRL ACK CCP/1.0" in msg:
                    if self.on_ack:
                        self.on_ack(self._extract_body(msg).strip())
                    continue

                if "CTRL ERROR CCP/1.0" in msg:
                    if self.on_error:
                        self.on_error(self._extract_body(msg).strip())
                    continue

                if "CTRL WHOIS CCP/1.0" in msg:
                    if self.on_whois:
                        self.on_whois(self._extract_body(msg).strip())
                    continue

                if "CTRL FILE_REQUEST" in msg:
                    headers = self._headers(msg)
                    sender = headers.get("from", "unknown")
                    name = self._extract_body(msg).strip() or "<unknown file>"
                    if self.on_file_request:
                        self.on_file_request(sender, name)
                    continue

                if "FILE_AUTH" in msg:
                    parts = self._extract_body(msg).strip().split()
                    if len(parts) >= 2 and self.pending_file_path and os.path.exists(self.pending_file_path):
                        self._send_file_data(parts[0], int(parts[1]), self.pending_file_path)
                    else:
                        if self.on_error:
                            self.on_error("File transfer canceled: local file missing.")
                    continue

                if "DATA MESSAGE" in msg:
                    headers = self._headers(msg)
                    payload = {
                        "channel": headers.get("channel", "PRIVATE"),
                        "from": headers.get("from", ""),
                        "to": headers.get("to", ""),
                        "body": self._extract_body(msg),
                    }
                    if self.on_message:
                        self.on_message(payload)
                    continue

                if self.on_ack:
                    self.on_ack(msg.strip())
        except Exception as exc:
            if self.on_disconnect:
                self.on_disconnect(f"TCP error: {exc}")

    def _udp_loop(self):
        try:
            while self.running:
                data, _ = self.udp.recvfrom(BUFFER_SIZE)
                if self.on_udp:
                    self.on_udp(data.decode(errors="replace"))
        except Exception:
            return

    def _p2p_loop(self):
        try:
            while self.running:
                conn, addr = self.p2p.accept()
                name = f"file_from_{addr[0]}_{int(time.time())}.dat"
                with open(name, "wb") as out:
                    while True:
                        data = conn.recv(BUFFER_SIZE)
                        if not data:
                            break
                        out.write(data)
                conn.close()
                if self.on_ack:
                    self.on_ack(f"File saved: {name}")
        except Exception:
            return

    def _send_file_data(self, ip_target: str, port_target: int, path: str):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((ip_target, port_target))
            with open(path, "rb") as source:
                while True:
                    chunk = source.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)
        if self.on_ack:
            self.on_ack(f"File sent: {os.path.basename(path)}")