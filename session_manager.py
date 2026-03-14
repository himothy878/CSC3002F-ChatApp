import threading


class SessionManager:
    def __init__(self):
        self.active_users = {}      # username -> (socket, udp_port, p2p_port)
        self.groups = {}            # group_name -> set(usernames)
        self.lock = threading.Lock()

    def add_user(self, username, sock, udp_port=None, p2p_port=None):
        with self.lock:
            self.active_users[username] = (sock, udp_port, p2p_port)

    def remove_user(self, username):
        with self.lock:
            self.active_users.pop(username, None)

    def get_user(self, username):
        with self.lock:
            return self.active_users.get(username)

    def list_users(self):
        with self.lock:
            return list(self.active_users.keys())

    def is_online(self, username):
        with self.lock:
            return username in self.active_users

    def get_all_users_safe(self):
        with self.lock:
            return list(self.active_users.items())

    def create_group(self, group_name):
        with self.lock:
            if group_name not in self.groups:
                self.groups[group_name] = set()

    def add_to_group(self, group_name, username):
        with self.lock:
            if group_name in self.groups:
                self.groups[group_name].add(username)