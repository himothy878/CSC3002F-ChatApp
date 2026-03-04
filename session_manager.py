import threading


class SessionManager:
    def __init__(self):
        self.active_users = {}      # username → socket
        self.groups = {}            # group_name → set(usernames)
        self.lock = threading.Lock()

    def add_user(self, username, socket):
        with self.lock:
            self.active_users[username] = socket

    def remove_user(self, username):
        with self.lock:
            if username in self.active_users:
                del self.active_users[username]

    def get_user_socket(self, username):
        with self.lock:
            return self.active_users.get(username)

    def list_users(self):
        with self.lock:
            return list(self.active_users.keys())

    def create_group(self, group_name):
        with self.lock:
            if group_name not in self.groups:
                self.groups[group_name] = set()

    def add_to_group(self, group_name, username):
        with self.lock:
            if group_name in self.groups:
                self.groups[group_name].add(username)