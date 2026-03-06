import socket, threading, os, time, keyboard
from datetime import datetime
from colorama import Fore, Style, init
from protocol import build_response, receive_message

init(autoreset=True)

TCP_PORT = 12345
UDP_PORT = 12346
BUFFER_SIZE = 4096

alias = input("Username: ")
ip = input("Server IP: ")

def timestamp():
    return datetime.now().strftime("[%H:%M:%S]")

client_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_udp.bind(('0.0.0.0', 0))
udp_port = client_udp.getsockname()[1]

p2p_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
p2p_socket.bind(('0.0.0.0', 0))
p2p_port = p2p_socket.getsockname()[1]
p2p_socket.listen()

client_tcp.connect((ip, TCP_PORT))
print(Fore.CYAN + f"{timestamp()} Connected. TCP:{TCP_PORT} UDP:{udp_port} P2P:{p2p_port}")

# login first
password = input("Password: ")
body = password
login_msg = f"CMD LOGIN CCP/1.0\r\nFrom: {alias}\r\nSeq: 1\r\nLength: {len(body)}\r\n\r\n{body}"
client_tcp.sendall(login_msg.encode())
print(Fore.CYAN + f"{timestamp()} Sent LOGIN")

ack = receive_message(client_tcp)
if ack and "ACK CCP/1.0" in ack:
    print(Fore.GREEN + f"Login success!")
else:
    print(Fore.RED + "Login failed")
    client_tcp.close()
    exit()

time.sleep(0.2)
reg = build_response("CMD REGISTER CCP/1.0", f"From: {alias}\r\nUDP-Port: {udp_port}\r\nP2P-Port: {p2p_port}\r\n")
client_tcp.sendall(reg.encode())
last_file = {"path": None}

def p2p_recv():
    while True:
        conn, addr = p2p_socket.accept()
        fname = f"file_from_{addr[0]}.dat"
        with open(fname, 'wb') as f:
            while data := conn.recv(BUFFER_SIZE):
                f.write(data)
        print(Fore.GREEN + f"File saved: {fname}")
        conn.close()

def tcp_recv():
    while True:
        msg = receive_message(client_tcp)
        if not msg:
            continue
        print(Fore.WHITE + f"\n{timestamp()} {msg}\n")
        if "FILE_AUTH" in msg:
            parts = msg.split("\r\n\r\n")[-1].strip().split()
            ip_t, port_t = parts[0], int(parts[1])
            path = last_file.get('path')
            if os.path.exists(path):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((ip_t, port_t))
                with open(path, 'rb') as f:
                    while chunk := f.read(BUFFER_SIZE):
                        s.sendall(chunk)
                s.close()
                print(Fore.GREEN + "File sent!")

def udp_recv():
    while True:
        data, _ = client_udp.recvfrom(BUFFER_SIZE)
        print(Fore.YELLOW + f"[UDP] {data.decode()}")

def tcp_send():
    seq = 2
    while True:
        keyboard.read_event(suppress=False)
        client_udp.sendto(f"TYPING {alias}".encode(), (ip, UDP_PORT))
        msg = input(Fore.BLUE + f"{alias}> " + Style.RESET_ALL)

        if msg.startswith("/join"):
            _, g = msg.split()
            client_tcp.sendall(build_response("CMD JOIN_GROUP CCP/1.0", f"To: {g}\r\nSeq: {seq}\r\nLength: 0\r\n\r\n").encode())
        elif msg.startswith("/leave"):
            _, g = msg.split()
            client_tcp.sendall(build_response("CMD LEAVE_GROUP CCP/1.0", f"To: {g}\r\nSeq: {seq}\r\nLength: 0\r\n\r\n").encode())
        elif msg.strip() == "/users":
            client_tcp.sendall(build_response("CMD LIST_USERS CCP/1.0", f"From: {alias}\r\nSeq: {seq}\r\nLength: 0\r\n\r\n").encode())
        elif msg.startswith("/file"):
            _, r, path = msg.split()
            last_file['path'] = path
            client_tcp.sendall(build_response("CMD FILE_REQUEST CCP/1.0", f"To: {r}\r\nSeq: {seq}\r\nLength: {len(path)}\r\n\r\n{path}").encode())
        elif msg.startswith("@"):
            r = msg.split()[0][1:]
            text = msg.split(maxsplit=1)[1]
            packet = build_response("DATA MESSAGE CCP/1.0", f"Channel: PRIVATE\r\nFrom: {alias}\r\nTo: {r}\r\nSeq: {seq}\r\nLength: {len(text)}\r\n\r\n{text}")
            client_tcp.sendall(packet.encode())
        else:
            body = msg
            packet = build_response("DATA MESSAGE CCP/1.0", f"Channel: GROUP\r\nFrom: {alias}\r\nTo: ALL\r\nSeq: {seq}\r\nLength: {len(body)}\r\n\r\n{body}")
            client_tcp.sendall(packet.encode())
        seq += 1

threading.Thread(target=p2p_recv, daemon=True).start()
threading.Thread(target=tcp_recv, daemon=True).start()
threading.Thread(target=udp_recv, daemon=True).start()
threading.Thread(target=tcp_send).start()