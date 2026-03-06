import socket, threading
from datetime import datetime
from colorama import Fore, init
from protocol import receive_message, build_response
from session_manager import SessionManager

init(autoreset=True)

TCP_PORT = 12345
UDP_PORT = 12346
BUFFER_SIZE = 4096
sessions = SessionManager()
sessions.groups = {}

def timestamp():
    return datetime.now().strftime("[%H:%M:%S]")

def ensure_group(g):
    if g not in sessions.groups:
        sessions.groups[g] = set()

def handle_udp():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('0.0.0.0', UDP_PORT))
    print(Fore.CYAN + f"{timestamp()} [SERVER] UDP running on {UDP_PORT}")

    while True:
        data, addr = udp.recvfrom(BUFFER_SIZE)
        msg = data.decode()
        print(Fore.YELLOW + f"{timestamp()} [UDP] {addr}: {msg}")
        for n, (s, u_port, _) in sessions.active_users.items():
            ip = s.getpeername()[0]
            if u_port and (ip, u_port) != addr:
                udp.sendto(data, (ip, u_port))

def handle_client(sock):
    user = "?"
    try:
        # 1️⃣ LOGIN
        login = receive_message(sock)
        if not login or "CMD LOGIN CCP/1.0" not in login:
            sock.close()
            return

        user = [l.split(":")[1].strip() for l in login.split("\r\n") if l.startswith("From:")][0]
        print(Fore.GREEN + f"{timestamp()} [LOGIN] from {user}")

        sock.sendall(f"CTRL ACK CCP/1.0\r\nTo: {user}\r\nSeq: 1\r\nLength: 0\r\n\r\n".encode())
        print(Fore.GREEN + f"{timestamp()} [AUTH] ACK sent to {user}")

        # 2️⃣ REGISTER
        reg = receive_message(sock)
        udp_l = [l for l in reg.split("\r\n") if "UDP-Port" in l][0]
        p2p_l = [l for l in reg.split("\r\n") if "P2P-Port" in l][0]
        u_p = int(udp_l.split(":")[1])
        p_p = int(p2p_l.split(":")[1])
        sessions.active_users[user] = (sock, u_p, p_p)
        print(Fore.CYAN + f"{timestamp()} [REGISTER] {user} UDP:{u_p} P2P:{p_p}")

        join_notice = build_response("CTRL USER_JOINED CCP/1.0", f"{user} joined the chat.")
        for n, (s, _, _) in sessions.active_users.items():
            if s != sock:
                s.sendall(join_notice.encode())

        # 3️⃣ MAIN LOOP
        while True:
            msg = receive_message(sock)
            if not msg:
                break

            # JOIN GROUP
            if "CMD JOIN_GROUP CCP/1.0" in msg:
                g = msg.split("To:")[1].split("\r\n")[0].strip()
                ensure_group(g)
                sessions.groups[g].add(user)
                sock.sendall(build_response("CTRL ACK CCP/1.0", f"Joined {g}").encode())
                print(Fore.MAGENTA + f"{timestamp()} [GROUP] {user} joined {g}")

            # LEAVE GROUP
            elif "CMD LEAVE_GROUP CCP/1.0" in msg:
                g = msg.split("To:")[1].split("\r\n")[0].strip()
                if user in sessions.groups.get(g, set()):
                    sessions.groups[g].remove(user)
                sock.sendall(build_response("CTRL ACK CCP/1.0", f"Left {g}").encode())
                print(Fore.MAGENTA + f"{timestamp()} [GROUP] {user} left {g}")

            # LIST USERS
            elif "CMD LIST_USERS CCP/1.0" in msg:
                names = "\n".join(sessions.active_users.keys())
                reply = f"CTRL USERS_LIST CCP/1.0\r\nTo: {user}\r\nLength: {len(names)}\r\n\r\n{names}"
                sock.sendall(reply.encode())
                print(Fore.CYAN + f"{timestamp()} [LIST_USERS] to {user}")

            # FILE REQUEST (fixed flow)
            elif "CMD FILE_REQUEST CCP/1.0" in msg:
                sender = user
                target = msg.split("To:")[1].split("\r\n")[0].strip()
                filename = msg.split("\r\n\r\n")[-1].strip()

                if target in sessions.active_users:
                    # notify receiver
                    notify = (
                        f"CTRL FILE_REQUEST CCP/1.0\r\nFrom: {sender}\r\nTo: {target}\r\nLength: {len(filename)}\r\n\r\n{filename}"
                    )
                    t_sock, _, p2p_p = sessions.active_users[target]
                    t_sock.sendall(notify.encode())

                    # send sender AUTH info
                    ip = t_sock.getpeername()[0]
                    auth = build_response("CTRL FILE_AUTH CCP/1.0", f"{ip} {p2p_p}")
                    sock.sendall(auth.encode())
                    print(Fore.YELLOW + f"{timestamp()} [FILE] {sender} → {target} {filename}")
                else:
                    sock.sendall(build_response("CTRL ERROR CCP/1.0", "USER_OFFLINE").encode())
                    print(Fore.RED + f"{timestamp()} [FILE] target {target} offline")

            # DATA MSG
            elif "DATA MESSAGE CCP/1.0" in msg:
                to_line = [l for l in msg.split("\r\n") if l.startswith("To:")][0]
                tgt = to_line.split(":")[1].strip()
                if tgt == "ALL":
                    for n, (s, _, _) in sessions.active_users.items():
                        if s != sock:
                            s.sendall(msg.encode())
                    print(Fore.WHITE + f"{timestamp()} [BROADCAST] {user} → ALL")
                elif tgt in sessions.groups:
                    for m in sessions.groups[tgt]:
                        if m in sessions.active_users and m != user:
                            sessions.active_users[m][0].sendall(msg.encode())
                    print(Fore.MAGENTA + f"{timestamp()} [GROUP] {user} → {tgt}")
                elif tgt in sessions.active_users:
                    sessions.active_users[tgt][0].sendall(msg.encode())
                    print(Fore.LIGHTBLUE_EX + f"{timestamp()} [PRIVATE] {user} → {tgt}")

    except Exception as e:
        print(Fore.RED + f"{timestamp()} [ERROR] {e}")

    finally:
        if user in sessions.active_users:
            del sessions.active_users[user]
            out = build_response("CTRL USER_LEFT CCP/1.0", f"{user} left the chat.")
            for n,(s,_,_) in sessions.active_users.items():
                s.sendall(out.encode())

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('0.0.0.0', TCP_PORT))
server.listen()
print(Fore.CYAN + f"{timestamp()} [SERVER] TCP running on {TCP_PORT}")
threading.Thread(target=handle_udp, daemon=True).start()
while True:
    s,a = server.accept()
    print(Fore.GREEN + f"{timestamp()} [CONNECT] {a} connected")
    threading.Thread(target=handle_client, args=(s,), daemon=True).start()
