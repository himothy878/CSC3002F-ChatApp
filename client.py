import os
import socket
import threading
import time
from datetime import datetime

from colorama import Fore, Style, init

from protocol import build_response, receive_message

init(autoreset=True)

TCP_PORT = 12345
UDP_PORT = 12346
BUFFER_SIZE = 4096


def timestamp():
    return datetime.now().strftime("[%H:%M:%S]")


alias = input("Username: ").strip()
ip = input("Server IP: ").strip()

client_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_udp.bind(("0.0.0.0", 0))
udp_port = client_udp.getsockname()[1]

p2p_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
p2p_sock.bind(("0.0.0.0", 0))
p2p_port = p2p_sock.getsockname()[1]
p2p_sock.listen()

client_tcp.connect((ip, TCP_PORT))
print(Fore.CYAN + f"{timestamp()} Connected! TCP:{TCP_PORT} UDP:{udp_port} P2P:{p2p_port}")


# ---------------- LOGIN ----------------
def login_phase():
    password = input("Password: ")
    body = password
    pkt = (
        f"CMD LOGIN CCP/1.0\r\n"
        f"From: {alias}\r\n"
        f"Seq: 1\r\n"
        f"Length: {len(body)}\r\n\r\n"
        f"{body}"
    )
    client_tcp.sendall(pkt.encode())
    resp = receive_message(client_tcp)

    if resp and "ACK CCP/1.0" in resp:
        print(Fore.GREEN + "Login successful!")
        return True
    if resp and "AUTH_FAILED" in resp:
        print(Fore.RED + "Wrong password.")
        return False

    print(Fore.RED + "No response from server.")
    return False


if not login_phase():
    client_tcp.close()
    raise SystemExit(1)

time.sleep(0.2)
reg = build_response(
    "CMD REGISTER CCP/1.0",
    f"From: {alias}\r\nUDP-Port: {udp_port}\r\nP2P-Port: {p2p_port}\r\n",
)
client_tcp.sendall(reg.encode())
print(Fore.CYAN + f"{timestamp()} Registered UDP/P2P ports.")

last_file = {"path": None}
online_users = []
joined_groups = []
list_lock = threading.Lock()


def _extract_body(msg):
    return msg.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in msg else ""


def _parse_lines(body):
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return [line for line in lines if line.lower() != "(no groups)"]


def _send_ctrl(seq, cmd, to_value="", body=""):
    headers = [f"From: {alias}", f"Seq: {seq}"]
    if to_value:
        headers.append(f"To: {to_value}")
    headers.append(f"Length: {len(body)}")
    payload = "\r\n".join(headers) + "\r\n\r\n" + body
    client_tcp.sendall(build_response(cmd, payload).encode())




def _apply_group_ack(body):
    body = body.strip()
    if body.startswith("Joined "):
        group = body[len("Joined "):].strip()
        if group:
            with list_lock:
                if group not in joined_groups:
                    joined_groups.append(group)
                    joined_groups.sort()
        return True

    if body.startswith("Left "):
        group = body[len("Left "):].strip()
        if group:
            with list_lock:
                joined_groups[:] = [g for g in joined_groups if g != group]
        return True

    return False


def _handle_slash_command(raw, seq):
    parts = raw.split(maxsplit=2)
    cmd = parts[0].lower()

    if cmd == "/join" and len(parts) >= 2:
        _send_ctrl(seq, "CMD JOIN_GROUP CCP/1.0", to_value=parts[1])
        print(Fore.CYAN + f"{timestamp()} Join request sent: {parts[1]}")
        return True

    if cmd == "/leave" and len(parts) >= 2:
        _send_ctrl(seq, "CMD LEAVE_GROUP CCP/1.0", to_value=parts[1])
        print(Fore.CYAN + f"{timestamp()} Leave request sent: {parts[1]}")
        return True

    if cmd == "/whois" and len(parts) >= 2:
        _send_ctrl(seq, "CMD WHOIS CCP/1.0", to_value=parts[1])
        print(Fore.CYAN + f"{timestamp()} Whois request sent: {parts[1]}")
        return True

    if cmd == "/file" and len(parts) >= 3:
        target, filepath = parts[1], parts[2]
        if not os.path.isfile(filepath):
            print(Fore.RED + f"{timestamp()} File not found: {filepath}")
            return False
        last_file["path"] = filepath
        _send_ctrl(seq, "CMD FILE_REQUEST CCP/1.0", to_value=target, body=os.path.basename(filepath))
        print(Fore.CYAN + f"{timestamp()} File request sent to {target}: {os.path.basename(filepath)}")
        return True

    print(Fore.YELLOW + "Commands: /join <group>, /leave <group>, /whois <user>, /file <user> <path>")
    return False


# --------------- P2P RECEIVE ----------------
def p2p_receive():
    while True:
        conn, addr = p2p_sock.accept()
        fname = f"file_from_{addr[0]}.dat"
        print(Fore.MAGENTA + f"{timestamp()} Receiving from {addr} -> {fname}")
        with open(fname, "wb") as f:
            while True:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break
                f.write(data)
        conn.close()
        print(Fore.GREEN + f"{timestamp()} File saved: {fname}")


# -------------- TCP RECEIVE ----------------
def tcp_receive():
    global online_users, joined_groups

    while True:
        try:
            msg = receive_message(client_tcp)
            if not msg:
                continue

            if "CTRL USERS_LIST" in msg:
                users = [u for u in _parse_lines(_extract_body(msg)) if u != alias]
                with list_lock:
                    online_users = users
                continue

            if "CTRL GROUPS_LIST" in msg:
                groups = _parse_lines(_extract_body(msg))
                with list_lock:
                    joined_groups = groups
                continue

            if "CTRL ACK CCP/1.0" in msg:
                body = _extract_body(msg)
                _apply_group_ack(body)
                print(Fore.WHITE + f"\n{timestamp()} {msg}\n")
                continue

            if "CTRL FILE_REQUEST" in msg:
                sender = "unknown"
                for line in msg.split("\r\n"):
                    if line.startswith("From:"):
                        sender = line.split(":", 1)[1].strip()
                        break
                file_name = _extract_body(msg).strip() or "<unknown file>"
                print(Fore.MAGENTA + f"\n{timestamp()} Incoming file request from {sender}: {file_name}")
                print(Fore.MAGENTA + f"{timestamp()} Waiting for sender to start transfer on P2P port {p2p_port}.\n")
                continue

            if "FILE_AUTH" in msg:
                parts = _extract_body(msg).strip().split()
                if len(parts) >= 2:
                    ip_t, port_t = parts[0], int(parts[1])
                    pth = last_file.get("path")
                    if pth and os.path.exists(pth):
                        print(Fore.YELLOW + f"{timestamp()} Sending {pth} -> {ip_t}:{port_t}")
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect((ip_t, port_t))
                        with open(pth, "rb") as f:
                            while True:
                                chunk = f.read(BUFFER_SIZE)
                                if not chunk:
                                    break
                                s.sendall(chunk)
                        s.close()
                        print(Fore.GREEN + f"{timestamp()} File sent!")
                    else:
                        print(Fore.RED + f"{timestamp()} File transfer cancelled: local file path missing.")
                continue

            print(Fore.WHITE + f"\n{timestamp()} {msg}\n")

        except Exception as e:
            print(Fore.RED + f"[ERROR] {e}")
            break


# -------------- UDP RECEIVE ----------------
def udp_receive():
    while True:
        try:
            data, _ = client_udp.recvfrom(BUFFER_SIZE)
            print(Fore.YELLOW + f"{timestamp()} [UDP] {data.decode(errors='replace')}")
        except Exception:
            break


# -------------- NUMBERED MENU SENDER ----------------
def tcp_send():
    seq = 2
    while True:
        client_tcp.sendall(
            build_response(
                "CMD LIST_USERS CCP/1.0",
                f"From: {alias}\r\nSeq: {seq}\r\nLength: 0\r\n\r\n",
            ).encode()
        )
        client_tcp.sendall(
            build_response(
                "CMD LIST_GROUPS CCP/1.0",
                f"From: {alias}\r\nSeq: {seq}\r\nLength: 0\r\n\r\n",
            ).encode()
        )
        time.sleep(0.2)

        with list_lock:
            current_online = list(online_users)
            current_groups = list(joined_groups)

        options = current_online + current_groups + ["ALL"]

        print(Fore.CYAN + "\n=========== Available Recipients ===========")
        print(Fore.CYAN + "(Type a name/number, or /join /leave /whois /file)")
        for i, name in enumerate(options, 1):
            print(Fore.YELLOW + f"{i}. {name}")
        print(Fore.CYAN + "============================================")

        dest_or_cmd = input(Fore.BLUE + "Select number/name or command: " + Style.RESET_ALL).strip()

        if not dest_or_cmd:
            continue

        if dest_or_cmd.startswith("/"):
            if _handle_slash_command(dest_or_cmd, seq):
                seq += 1
            continue

        dest = dest_or_cmd
        if dest.isdigit() and 1 <= int(dest) <= len(options):
            dest = options[int(dest) - 1]

        client_udp.sendto(f"TYPING {alias}".encode(), (ip, UDP_PORT))

        msg = input(Fore.GREEN + "Message> " + Style.RESET_ALL)
        if not msg:
            continue

        with list_lock:
            channel = "GROUP" if dest in joined_groups else "PRIVATE"

        packet = build_response(
            "DATA MESSAGE CCP/1.0",
            (
                f"Channel: {channel}\r\n"
                f"From: {alias}\r\n"
                f"To: {dest}\r\n"
                f"Seq: {seq}\r\n"
                f"Length: {len(msg)}\r\n\r\n"
                f"{msg}"
            ),
        )
        client_tcp.sendall(packet.encode())
        print(Fore.GREEN + f"{timestamp()} Sent to {dest}\n")
        seq += 1


threading.Thread(target=p2p_receive, daemon=True).start()
threading.Thread(target=tcp_receive, daemon=True).start()
threading.Thread(target=udp_receive, daemon=True).start()
threading.Thread(target=tcp_send).start()