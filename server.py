# server.py (Mainly Person A, with P2P signaling for Person C)
import socket
import threading
from session_manager import SessionManager

HOST = "127.0.0.1"
PORT = 5000
session_manager = SessionManager()

# Store P2P ports for each user: username -> p2p_port
user_p2p_ports = {}

def handle_client(client_socket, address):
    print(f"[NEW CONNECTION] {address}")
    username = None

    while True:
        try:
            message = client_socket.recv(4096).decode('utf-8')
            if not message:
                break
            
            lines = message.split("\r\n")
            first_line = lines[0]

            # --- PERSON A: LOGIN & RELAY LOGIC ---
            if "CMD LOGIN" in first_line:
                username = lines[2].split("From: ")[1].strip()
                p2p_port = lines[5].split("Length: ")[1].strip() # We'll sneak the P2P port in the length/body for the prototype
                
                session_manager.add_user(username, client_socket)
                user_p2p_ports[username] = int(p2p_port)
                print(f"[LOGIN] {username} joined. P2P Port: {p2p_port}")
                
                client_socket.sendall(f"CTRL ACK CCP/1.0\r\nTo: {username}\r\nSeq: 1\r\nLength: 0\r\n\r\n".encode())

            elif "DATA MESSAGE" in first_line:
                # Relay text to all other users
                target = lines[3].split("To: ")[1].strip()
                for user in session_manager.list_users():
                    if user != username:
                        sock = session_manager.get_user_socket(user)
                        sock.sendall(message.encode('utf-8'))

            # --- PERSON C: P2P SIGNALLING LOGIC ---
            elif "CMD FILE_REQUEST" in first_line:
                target_user = lines[3].split("To: ")[1].strip()
                if target_user in user_p2p_ports:
                    target_ip = "127.0.0.1" # Assuming localhost for prototype
                    target_port = user_p2p_ports[target_user]
                    
                    # Send FILE_AUTH back to sender with IP and Port
                    auth_msg = f"CMD FILE_AUTH CCP/1.0\r\nTo: {username}\r\nLength: 0\r\n\r\n{target_ip}:{target_port}"
                    client_socket.sendall(auth_msg.encode('utf-8'))
                else:
                    client_socket.sendall(f"CTRL ERROR CCP/1.0\r\nLength: 0\r\n\r\nUSER_NOT_FOUND".encode())

        except Exception as e:
            print(f"Error: {e}")
            break

    if username:
        session_manager.remove_user(username)
        if username in user_p2p_ports:
            del user_p2p_ports[username]
    client_socket.close()

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen()
    print(f"[LISTENING] Server running on {HOST}:{PORT}")

    while True:
        client_socket, address = server_socket.accept()
        threading.Thread(target=handle_client, args=(client_socket, address)).start()

if __name__ == "__main__":
    start_server()
