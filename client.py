# client.py
import socket
import threading

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5000
UDP_PORT = 5555 # Changed to 5555 to avoid WinError 10013

class ChatClient:
    def __init__(self, alias):
        self.alias = alias
        
        # 1. Server TCP Socket (Person A)
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # 2. UDP Socket (Person B)
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # FIX: Allow multiple clients on the same machine to share the UDP port
        self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
        self.udp_sock.bind(('', UDP_PORT)) 
        
        # 3. P2P TCP Listener Socket (Person C)
        self.p2p_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.p2p_listener.bind(('', 0)) # Bind to any available ephemeral port
        self.p2p_port = self.p2p_listener.getsockname()[1]
        self.p2p_listener.listen()

    def start(self):
        # Connect to main server
        self.tcp_sock.connect((SERVER_HOST, SERVER_PORT))
        
        # Login and tell the server our P2P port
        login_msg = f"CMD LOGIN CCP/1.0\r\nChannel: PRIVATE\r\nFrom: {self.alias}\r\nTo: SERVER\r\nSeq: 1\r\nLength: {self.p2p_port}\r\n\r\n"
        self.tcp_sock.sendall(login_msg.encode('utf-8'))

        print(f"Connected! Your P2P port is {self.p2p_port}")

        # Start all listening threads
        threading.Thread(target=self.listen_tcp_server, daemon=True).start()
        threading.Thread(target=self.listen_udp, daemon=True).start()
        threading.Thread(target=self.listen_p2p, daemon=True).start()

        self.user_input_loop()

    # --- PERSON A: TCP SERVER RELAY ---
    def listen_tcp_server(self):
        while True:
            try:
                msg = self.tcp_sock.recv(4096).decode('utf-8')
                if not msg:
                    break
                if "CMD FILE_AUTH" in msg:
                    # Server gave us the P2P IP:Port! Let's send the file.
                    body = msg.split("\r\n\r\n")[1]
                    target_ip, target_port = body.split(":")
                    self.send_file_p2p(target_ip, int(target_port))
                elif "DATA MESSAGE" in msg:
                    body = msg.split("\r\n\r\n")[1]
                    print(f"\n[CHAT] {body}")
            except Exception as e:
                print(f"TCP Listen Error: {e}")
                break

    # --- PERSON B: UDP PRESENCE & TYPING ---
    def listen_udp(self):
        while True:
            try:
                data, addr = self.udp_sock.recvfrom(1024)
                print(f"\n[UDP PRESENCE] {data.decode('utf-8')}")
            except Exception as e:
                print(f"UDP Listen Error: {e}")
                break

    def send_udp_presence(self, status):
        msg = f"DATA PRESENCE CCP/1.0\r\nFrom: {self.alias}\r\n\r\n{status}"
        self.udp_sock.sendto(msg.encode('utf-8'), ('255.255.255.255', UDP_PORT))

    # --- PERSON C: P2P FILE TRANSFER ---
    def listen_p2p(self):
        while True:
            try:
                conn, addr = self.p2p_listener.accept()
                print(f"\n[P2P] Incoming connection from {addr}...")
                # Receive the file in chunks
                with open(f"received_by_{self.alias}.txt", "wb") as f:
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk: break
                        f.write(chunk)
                print("[P2P] File received successfully!")
                conn.close()
            except Exception as e:
                print(f"P2P Listen Error: {e}")
                break

    def request_file_transfer(self, target_user):
        print(f"Requesting P2P connection to {target_user}...")
        req = f"CMD FILE_REQUEST CCP/1.0\r\nFrom: {self.alias}\r\nTo: {target_user}\r\nSeq: 2\r\nLength: 0\r\n\r\n"
        self.tcp_sock.sendall(req.encode('utf-8'))

    def send_file_p2p(self, ip, port):
        print(f"[P2P] Connecting directly to {ip}:{port} to send file...")
        try:
            p2p_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            p2p_sock.connect((ip, port))
            # Send a dummy file for the prototype
            p2p_sock.sendall(b"Hello! This is a P2P file payload chunk.")
            p2p_sock.close()
            print("[P2P] File sent directly to peer!")
        except Exception as e:
            print(f"[P2P Error] {e}")

    # --- USER INTERFACE ---
    def user_input_loop(self):
        while True:
            cmd = input(f"{self.alias} > ")
            if cmd == "/file":
                target = input("Who do you want to send a file to? ")
                self.request_file_transfer(target)
            elif cmd == "/status":
                status = input("Enter status: ")
                self.send_udp_presence(status)
            else:
                # Send normal text chat
                msg = f"DATA MESSAGE CCP/1.0\r\nChannel: GROUP\r\nFrom: {self.alias}\r\nTo: ALL\r\nSeq: 2\r\nLength: {len(cmd)}\r\n\r\n{self.alias}: {cmd}"
                self.tcp_sock.sendall(msg.encode('utf-8'))

if __name__ == "__main__":
    alias = input("Enter your alias: ")
    client = ChatClient(alias)
    client.start()
