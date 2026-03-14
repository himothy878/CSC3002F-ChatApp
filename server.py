import socket
import threading
from datetime import datetime

from colorama import Fore, init

import database
from protocol import build_response, receive_message
from session_manager import SessionManager


database.init_db()
init(autoreset=True)

TCP_PORT = 12345
UDP_PORT = 12346
BUFFER_SIZE = 4096

sessions = SessionManager()


def timestamp():
    return datetime.now().strftime("[%H:%M:%S]")


def handle_udp():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("0.0.0.0", UDP_PORT))
    print(Fore.CYAN + f"{timestamp()} [SERVER] UDP running {UDP_PORT}")

    while True:
        data, addr = udp.recvfrom(BUFFER_SIZE)
        msg = data.decode(errors="replace")
        print(Fore.YELLOW + f"{timestamp()} [UDP] {addr}: {msg}")

        for _, (sock, udp_port, _) in sessions.get_all_users_safe():
            try:
                ip = sock.getpeername()[0]
                if udp_port and (ip, udp_port) != addr:
                    udp.sendto(data, (ip, udp_port))
            except Exception:
                continue


def _extract_header_value(msg, key):
    prefix = f"{key}:"
    for line in msg.split("\r\n"):
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def handle_client(sock):
    user = "?"
    try:
        login = receive_message(sock)
        if not login or "CMD LOGIN" not in login:
            sock.close()
            return

        user = _extract_header_value(login, "From")
        password = login.split("\r\n\r\n", 1)[1].strip() if "\r\n\r\n" in login else ""

        if not database.verify_or_create_user(user, password):
            sock.sendall(build_response("CTRL ERROR CCP/1.0", "AUTH_FAILED").encode())
            sock.close()
            return

        sock.sendall(
            f"CTRL ACK CCP/1.0\r\nTo: {user}\r\nSeq: 1\r\nLength: 0\r\n\r\n".encode()
        )
        print(Fore.GREEN + f"{timestamp()} [LOGIN] {user}")

        reg = receive_message(sock)
        udp_port = int(_extract_header_value(reg, "UDP-Port"))
        p2p_port = int(_extract_header_value(reg, "P2P-Port"))
        sessions.add_user(user, sock, udp_port, p2p_port)

        while True:
            msg = receive_message(sock)
            if not msg:
                break

            # --- GROUP JOIN/LEAVE ---
            if "CMD JOIN_GROUP" in msg:
                group = _extract_header_value(msg, "To")
                database.add_to_group(user, group)
                sock.sendall(build_response("CTRL ACK CCP/1.0", f"Joined {group}").encode())
                print(Fore.MAGENTA + f"{timestamp()} [GROUP] {user} joined {group}")

            elif "CMD LEAVE_GROUP" in msg:
                group = _extract_header_value(msg, "To")
                database.remove_from_group(user, group)
                sock.sendall(build_response("CTRL ACK CCP/1.0", f"Left {group}").encode())
                print(Fore.MAGENTA + f"{timestamp()} [GROUP] {user} left {group}")

            # --- LIST USERS / GROUPS ---
            elif "CMD LIST_USERS" in msg:
                names = "\n".join(sessions.list_users())
                resp = (
                    f"CTRL USERS_LIST CCP/1.0\r\nTo: {user}\r\nLength: {len(names)}\r\n\r\n" f"{names}"
                )
                sock.sendall(resp.encode())

            elif "CMD LIST_GROUPS" in msg:
                groups = database.get_group_memberships(user)
                glist = "\n".join(groups) if groups else "(no groups)"
                reply = (
                    f"CTRL GROUPS_LIST CCP/1.0\r\nTo: {user}\r\nLength: {len(glist)}\r\n\r\n" f"{glist}"
                )
                sock.sendall(reply.encode())

            # --- NEW: LIST GROUP MEMBERS ---
            elif "CMD LIST_GROUP_MEMBERS" in msg:
                group = _extract_header_value(msg, "To")
                members = database.get_group_members(group)
                if members:
                    body = "Group: " + group + "\n" + "\n".join(members)
                else:
                    body = f"Group: {group}\n(no members)"
                reply = (
                    f"CTRL GROUP_MEMBERS CCP/1.0\r\nTo: {user}\r\nLength: {len(body)}\r\n\r\n" f"{body}"
                )
                sock.sendall(reply.encode())

            # --- NEW: ADD USER TO GROUP ---
            elif "CMD ADD_TO_GROUP" in msg:
                target_user = _extract_header_value(msg, "To")
                group = msg.split("\r\n\r\n", 1)[1].strip() if "\r\n\r\n" in msg else ""
                if target_user and group:
                    database.add_to_group(target_user, group)
                    sock.sendall(
                        build_response(
                            "CTRL ACK CCP/1.0", f"Added {target_user} to {group}"
                        ).encode()
                    )
                    print(
                        Fore.MAGENTA
                        + f"{timestamp()} [GROUP] {user} added {target_user} to {group}"
                    )
                else:
                    sock.sendall(
                        build_response("CTRL ERROR CCP/1.0", "BAD_ADD_TO_GROUP").encode()
                    )

            # --- FILE REQUEST ---
            elif "CMD FILE_REQUEST" in msg:
                target = _extract_header_value(msg, "To")
                fname = msg.split("\r\n\r\n", 1)[1].strip() if "\r\n\r\n" in msg else ""
                target_session = sessions.get_user(target)
                if target_session:
                    t_sock, _, t_p2p_port = target_session
                    t_sock.sendall(
                        f"CTRL FILE_REQUEST CCP/1.0\r\nFrom: {user}\r\nTo: {target}\r\nLength: {len(fname)}\r\n\r\n{fname}".encode()
                    )
                    t_ip = t_sock.getpeername()[0]
                    sock.sendall(
                        build_response("CTRL FILE_AUTH CCP/1.0", f"{t_ip} {t_p2p_port}").encode()
                    )
                else:
                    sock.sendall(
                        build_response("CTRL ERROR CCP/1.0", "USER_OFFLINE").encode()
                    )

            # --- WHOIS ---
            elif "CMD WHOIS" in msg:
                target = _extract_header_value(msg, "To")
                info, groups = database.get_user_info(target)
                if not info:
                    res = f"User '{target}' not found."
                else:
                    online = sessions.is_online(target)
                    res = (
                        f"User: {target}\n"
                        f"Status: {'Online' if online else 'Offline'}\n"
                        f"Groups: {', '.join(groups) if groups else 'None'}\n"
                        f"Last login: {info[1]}\n"
                        f"Location: {info[2]}"
                    )
                reply = (
                    f"CTRL WHOIS CCP/1.0\r\nTo: {user}\r\nLength: {len(res)}\r\n\r\n" f"{res}"
                )
                sock.sendall(reply.encode())

            # --- NEW: PRIVATE HISTORY ---
            elif "CMD HISTORY_PRIVATE" in msg:
                other = _extract_header_value(msg, "To")
                rows = database.get_private_history(user, other, limit=300)
                lines = []
                for ts_val, sender, target, channel, body in rows:
                    lines.append(f"{ts_val}\t{sender}\t{channel}\t{target}\t{body}")
                payload = "\n".join(lines)
                reply = (
                    f"CTRL HISTORY CCP/1.0\r\nTo: {user}\r\nLength: {len(payload)}\r\n\r\n" f"{payload}"
                )
                sock.sendall(reply.encode())

            # --- NEW: GROUP HISTORY ---
            elif "CMD HISTORY_GROUP" in msg:
                group = _extract_header_value(msg, "To")
                rows = database.get_group_history(group, limit=300)
                lines = []
                for ts_val, sender, target, channel, body in rows:
                    lines.append(f"{ts_val}\t{sender}\t{channel}\t{target}\t{body}")
                payload = "\n".join(lines)
                reply = (
                    f"CTRL HISTORY CCP/1.0\r\nTo: {user}\r\nLength: {len(payload)}\r\n\r\n" f"{payload}"
                )
                sock.sendall(reply.encode())

            # --- DATA MESSAGE (PRIVATE / GROUP / ALL) ---
            elif "DATA MESSAGE" in msg:
                target = _extract_header_value(msg, "To")
                channel = _extract_header_value(msg, "Channel") or "PRIVATE"

                # body after inner CCP header
                parts = msg.split("\r\n\r\n", 2)
                if len(parts) >= 3:
                    body = parts[2]
                else:
                    body = parts[-1] if len(parts) >= 2 else ""

                # save message
                ch_up = channel.upper()
                if ch_up == "PRIVATE":
                    database.save_message(user, target, "PRIVATE", body)
                elif ch_up == "GROUP":
                    database.save_message(user, target, "GROUP", body)
                elif target == "ALL":
                    # you can persist broadcasts if you want; skipped for now
                    pass

                if target == "ALL":
                    sender_groups = database.get_group_memberships(user)
                    recipients = set()
                    for grp in sender_groups:
                        for member in database.get_group_members(grp):
                            if member != user:
                                recipients.add(member)
                    for member in recipients:
                        member_session = sessions.get_user(member)
                        if member_session:
                            member_session[0].sendall(msg.encode())
                else:
                    members = database.get_group_members(target)
                    sent = False
                    if members:
                        for member in members:
                            if member != user:
                                member_session = sessions.get_user(member)
                                if member_session:
                                    member_session[0].sendall(msg.encode())
                                    sent = True
                    if not sent:
                        target_session = sessions.get_user(target)
                        if target_session and target != user:
                            target_session[0].sendall(msg.encode())

    except Exception as e:
        print(Fore.RED + f"{timestamp()} [ERROR] {e}")

    finally:
        sessions.remove_user(user)
        leave = build_response("CTRL USER_LEFT CCP/1.0", f"{user} left")
        for _, (peer_sock, _, _) in sessions.get_all_users_safe():
            try:
                peer_sock.sendall(leave.encode())
            except Exception:
                continue


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(("0.0.0.0", TCP_PORT))
server.listen()
print(Fore.CYAN + f"{timestamp()} [SERVER] TCP running {TCP_PORT}")

threading.Thread(target=handle_udp, daemon=True).start()

while True:
    s, a = server.accept()
    print(Fore.GREEN + f"{timestamp()} [CONNECT] {a}")
    threading.Thread(target=handle_client, args=(s,), daemon=True).start()
