import socket
import threading

alias = input("Enter your alias: ")
ip = input("Enter the IP address of the server: ")
clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
clientSocket.connect((ip, 12345))

def client_receive():
    while True:
        try:
            message = clientSocket.recv(1024).decode('utf-8')
            if message == 'alias?':
                clientSocket.send(alias.encode('utf-8'))
            else:
                print(message)
        except:
            print("An error occurred!")
            clientSocket.close()
            break

def client_send():
     while True:
                message = f'{alias}: {input("")}'
                clientSocket.send(message.encode('utf-8'))
receive_thread = threading.Thread(target=client_receive)
receive_thread.start()
send_thread = threading.Thread(target=client_send)
send_thread.start()           