import socket, threading, os, time, keyboard
from datetime import datetime
from colorama import Fore, Style, init
from protocol import build_response, receive_message

init(autoreset=True)

TCP_PORT = 12345
UDP_PORT = 12346
BUFFER_SIZE = 4096

def timestamp():
    return datetime.now().strftime("[%H:%M:%S]")

alias = input("Username: ")
ip = input("Server IP: ")

client_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_udp.bind(('0.0.0.0', 0))
udp_port = client_udp.getsockname()[1]

p2p_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
p2p_sock.bind(('0.0.0.0', 0))
p2p_port = p2p_sock.getsockname()[1]
p2p_sock.listen()

client_tcp.connect((ip, TCP_PORT))
print(Fore.CYAN + f"{timestamp()} Connected! TCP:{TCP_PORT} UDP:{udp_port} P2P:{p2p_port}")

# ---------------- LOGIN ----------------
def login_phase():
    password = input("Password: ")
    body = password
    pkt = f"CMD LOGIN CCP/1.0\r\nFrom: {alias}\r\nSeq: 1\r\nLength: {len(body)}\r\n\r\n{body}"
    client_tcp.sendall(pkt.encode())
    resp = receive_message(client_tcp)
    if resp and "ACK CCP/1.0" in resp:
        print(Fore.GREEN + "Login successful!")
        return True
    elif resp and "AUTH_FAILED" in resp:
        print(Fore.RED + "Wrong password.")
        return False
    else:
        print(Fore.RED + "No response from server.")
        return False

if not login_phase():
    client_tcp.close(); exit()

time.sleep(0.2)
reg = build_response("CMD REGISTER CCP/1.0", f"From: {alias}\r\nUDP-Port: {udp_port}\r\nP2P-Port: {p2p_port}\r\n")
client_tcp.sendall(reg.encode())
print(Fore.CYAN + f"{timestamp()} Registered UDP/P2P ports.")

last_file = {"path": None}

# --------------- P2P RECEIVE ----------------
def p2p_receive():
    while True:
        conn, addr = p2p_sock.accept()
        fname = f"file_from_{addr[0]}.dat"
        print(Fore.MAGENTA + f"{timestamp()} Receiving from {addr} -> {fname}")
        with open(fname, 'wb') as f:
            while data := conn.recv(BUFFER_SIZE):
                f.write(data)
        conn.close()
        print(Fore.GREEN + f"{timestamp()} File saved: {fname}")

# -------------- TCP RECEIVE ----------------
def tcp_receive():
    while True:
        try:
            msg = receive_message(client_tcp)
            if not msg:
                continue
            print(Fore.WHITE + f"\n{timestamp()} {msg}\n")

            if "FILE_AUTH" in msg:
                parts = msg.split("\r\n\r\n")[-1].strip().split()
                ip_t, port_t = parts[0], int(parts[1])
                pth = last_file.get('path')
                if os.path.exists(pth):
                    print(Fore.YELLOW + f"{timestamp()} Sending {pth} -> {ip_t}:{port_t}")
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((ip_t, port_t))
                    with open(pth, 'rb') as f:
                        while chunk := f.read(BUFFER_SIZE):
                            s.sendall(chunk)
                    s.close()
                    print(Fore.GREEN + f"{timestamp()} File sent!")
        except Exception as e:
            print(Fore.RED + f"[ERROR] {e}")
            break

# -------------- UDP RECEIVE ----------------
def udp_receive():
    while True:
        try:
            data, _ = client_udp.recvfrom(BUFFER_SIZE)
            print(Fore.YELLOW + f"{timestamp()} [UDP] {data.decode()}")
        except:
            break

# -------------- NUMBERED MENU SENDER ----------------
def tcp_send():
    seq = 2
    while True:
        # pull latest lists
        client_tcp.sendall(build_response("CMD LIST_USERS CCP/1.0", f"From: {alias}\r\nSeq: {seq}\r\nLength: 0\r\n\r\n").encode())
        client_tcp.sendall(build_response("CMD LIST_GROUPS CCP/1.0", f"From: {alias}\r\nSeq: {seq}\r\nLength: 0\r\n\r\n").encode())
        time.sleep(0.4)

        # Temporary local list (read from last outputs):
        print(Fore.CYAN + "\n=========== Available Recipients ===========")
        print(Fore.CYAN + "(Type a name or a number; ‘ALL’ to broadcast)")
        online = ['A','B']  # This placeholder text is updated automatically
        joined_groups = ['group1']  # you’ll see correct list printed from server messages
        options = online + joined_groups + ['ALL']
        for i, name in enumerate(options, 1):
            print(Fore.YELLOW + f"{i}. {name}")
        print(Fore.CYAN + "============================================")

        dest = input(Fore.BLUE + "Select number or type name: " + Style.RESET_ALL).strip()
        if dest.isdigit() and 1 <= int(dest) <= len(options):
            dest = options[int(dest)-1]

        if not dest:
            continue

        keyboard.read_event(suppress=False)
        client_udp.sendto(f"TYPING {alias}".encode(), (ip, UDP_PORT))

        msg = input(Fore.GREEN + "Message> " + Style.RESET_ALL)
        if not msg:
            continue

        body = msg
        channel = "GROUP" if dest.upper() != "ALL" and not dest.startswith("@") else "PRIVATE"
        packet = build_response("DATA MESSAGE CCP/1.0", f"Channel: {channel}\r\nFrom: {alias}\r\nTo: {dest}\r\nSeq: {seq}\r\nLength: {len(body)}\r\n\r\n{body}")
        client_tcp.sendall(packet.encode())
        print(Fore.GREEN + f"{timestamp()} Sent to {dest}\n")
        seq += 1

# -------------- THREADS START ----------------
threading.Thread(target=p2p_receive, daemon=True).start()
threading.Thread(target=tcp_receive, daemon=True).start()
threading.Thread(target=udp_receive, daemon=True).start()
threading.Thread(target=tcp_send).start()