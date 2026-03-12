import queue
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

from client_network import ClientNetwork


def ts():
    return datetime.now().strftime("[%H:%M:%S]")


class ChatGUIApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CCP Messenger")
        self.root.geometry("1040x680")

        self.network = ClientNetwork()
        self.network.on_users = lambda users: self.uiq.put(("users", users))
        self.network.on_groups = lambda groups: self.uiq.put(("groups", groups))
        self.network.on_group_members = (
            lambda group, members: self.uiq.put(("group_members", (group, members)))
        )
        self.network.on_history = lambda _me, entries: self.uiq.put(("history", entries))
        self.network.on_ack = lambda text: self.uiq.put(("log", text))
        self.network.on_error = lambda text: self.uiq.put(("error", text))
        self.network.on_whois = lambda text: self.uiq.put(("whois", text))
        self.network.on_udp = self._handle_udp
        self.network.on_file_request = (
            lambda sender, name: self.uiq.put(("log", f"Incoming file request from {sender}: {name}"))
        )
        self.network.on_message = lambda payload: self.uiq.put(("message", payload))
        self.network.on_disconnect = lambda text: self.uiq.put(("error", text))

        self.uiq = queue.Queue()
        self.online_users = []
        self.joined_groups = []
        self.current_chat_target = None
        self.current_chat_is_group = False
        # chat_history[key] = list of {"ts", "text", "self"}
        self.chat_history = {}
        self.selected_user = None
        self.selected_group = None

        # typing indicator state
        self._typing_after_id = None

        self._build_layout()
        self.show_login()

        self.root.after(100, self.process_ui_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ============== LAYOUT ==============
    def _build_layout(self):
        self.container = ttk.Frame(self.root, padding=10)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.login_frame = ttk.Frame(self.container)
        self.main_frame = ttk.Frame(self.container)
        self.join_group_frame = ttk.Frame(self.container)

        for frame in (self.login_frame, self.main_frame, self.join_group_frame):
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_login_frame()
        self._build_main_frame_whatsapp_style()
        self._build_join_group_frame()

    def _build_login_frame(self):
        card = ttk.Frame(self.login_frame, padding=20)
        card.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(card, text="CCP Chat Login", font=("Arial", 16, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 12)
        )

        ttk.Label(card, text="Server IP").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=4)
        self.server_entry = ttk.Entry(card, width=28)
        self.server_entry.grid(row=1, column=1, sticky="w", pady=4)
        self.server_entry.insert(0, "127.0.0.1")

        ttk.Label(card, text="Username").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=4)
        self.username_entry = ttk.Entry(card, width=28)
        self.username_entry.grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(card, text="Password").grid(row=3, column=0, sticky="e", padx=(0, 8), pady=4)
        self.password_entry = ttk.Entry(card, show="*", width=28)
        self.password_entry.grid(row=3, column=1, sticky="w", pady=4)

        ttk.Button(card, text="Login", command=self.login).grid(row=4, column=0, pady=(12, 0))
        ttk.Button(card, text="Sign Up", command=self.signup).grid(
            row=4, column=1, pady=(12, 0), sticky="w"
        )

    def _build_main_frame_whatsapp_style(self):
        top = ttk.Frame(self.main_frame)
        top.pack(fill=tk.X)

        self.main_title = ttk.Label(top, text="Main", font=("Arial", 14, "bold"))
        self.main_title.pack(side=tk.LEFT)

        ttk.Button(top, text="Join Group", command=self.show_join_group).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(top, text="Refresh", command=self.network.request_lists).pack(side=tk.RIGHT, padx=(8, 0))

        body = ttk.Frame(self.main_frame)
        body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        # LEFT COLUMN
        left = ttk.Frame(body, width=260)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        users_box = ttk.LabelFrame(left, text="Users")
        users_box.pack(fill=tk.BOTH, expand=True, padx=(0, 6), pady=(0, 6))

        self.users_list = tk.Listbox(users_box)
        self.users_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.users_list.bind("<<ListboxSelect>>", self._on_user_select)
        self.users_list.bind("<Double-Button-1>", self.open_user_chat)

        groups_box = ttk.LabelFrame(left, text="Groups")
        groups_box.pack(fill=tk.BOTH, expand=True, padx=(0, 6), pady=(0, 6))

        self.groups_list = tk.Listbox(groups_box)
        self.groups_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.groups_list.bind("<<ListboxSelect>>", self._on_group_select)
        self.groups_list.bind("<Double-Button-1>", self.open_group_chat)

        actions = ttk.Frame(left)
        actions.pack(fill=tk.X, pady=(4, 0))

        ttk.Button(actions, text="Open User", command=self.open_user_chat).pack(side=tk.LEFT)
        ttk.Button(actions, text="Open Group", command=self.open_group_chat).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(actions, text="View Members", command=self.view_group_members).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(actions, text="Add Member", command=self.add_member_to_group).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(actions, text="Leave Group", command=self.leave_selected_group).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(actions, text="Whois", command=self.whois_selected_user).pack(side=tk.LEFT, padx=(4, 0))

        # RIGHT COLUMN
        right = ttk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header = ttk.Frame(right)
        header.pack(fill=tk.X)

        self.chat_title = ttk.Label(header, text="No chat selected", font=("Arial", 13, "bold"))
        self.chat_title.pack(side=tk.LEFT)

        self.typing_label = ttk.Label(header, text="", foreground="gray")
        self.typing_label.pack(side=tk.RIGHT)

        self.chat_text = tk.Text(right, state=tk.DISABLED, wrap=tk.WORD)
        self.chat_text.tag_configure("self", foreground="blue", justify="right")
        self.chat_text.tag_configure("other", foreground="black", justify="left")
        self.chat_text.pack(fill=tk.BOTH, expand=True, pady=(6, 6))

        send = ttk.Frame(right)
        send.pack(fill=tk.X)

        self.chat_input = ttk.Entry(send)
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_input.bind("<Return>", lambda _e: self.send_chat())

        ttk.Button(send, text="Send", command=self.send_chat).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(send, text="Send File", command=self.send_file).pack(side=tk.LEFT, padx=(8, 0))

        self.main_log = tk.Text(self.main_frame, height=8, state=tk.DISABLED)
        self.main_log.pack(fill=tk.X, pady=(8, 0))

    def _build_join_group_frame(self):
        card = ttk.Frame(self.join_group_frame, padding=20)
        card.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(card, text="Join / Create Group", font=("Arial", 14, "bold")).pack(pady=(0, 10))

        self.join_group_entry = ttk.Entry(card, width=30)
        self.join_group_entry.pack(pady=(0, 8))

        ttk.Button(card, text="Join Group", command=self.join_group).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(card, text="Back", command=self.show_main).pack(fill=tk.X)

    # ============== NAV / AUTH ==============
    def show_login(self):
        self.login_frame.tkraise()

    def show_main(self):
        self.main_frame.tkraise()
        self.network.request_lists()

    def show_join_group(self):
        self.join_group_frame.tkraise()

    def login(self):
        self._auth("login")

    def signup(self):
        self._auth("signup")

    def _auth(self, mode: str):
        server_ip = self.server_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not server_ip or not username or not password:
            title = "Sign Up Error" if mode == "signup" else "Login Error"
            messagebox.showwarning(title, "Server IP, username and password are required")
            return

        try:
            self.network.connect(server_ip, username, password)

            self.main_title.config(text=f"Main - {self.network.alias} ({mode})")
            label = "Sign up" if mode == "signup" else "Login"
            self.add_main_log(f"{label} successful")
            self.show_main()
            self.schedule_refresh()

        except RuntimeError as exc:
            if mode == "signup":
                messagebox.showerror(
                    "Sign Up Error",
                    "Username already exists with a different password, or the password is invalid.\n"
                    "Use a new username to create an account, or use Login instead.",
                )
            else:
                messagebox.showerror("Login Error", str(exc))
        except Exception as exc:
            title = "Sign Up Error" if mode == "signup" else "Authentication Error"
            messagebox.showerror(title, str(exc))

    def schedule_refresh(self):
        if not self.network.running:
            return
        self.network.request_lists()
        self.root.after(1200, self.schedule_refresh)

    # ============== UDP HANDLER (TYPING) ==============
    def _handle_udp(self, text: str):
        self.uiq.put(("log", f"[UDP] {text}"))
        stripped = text.strip()
        if stripped.upper().startswith("TYPING "):
            name = stripped.split(" ", 1)[1].strip()
            if name and name != self.network.alias:
                self.uiq.put(("typing", name))

    # ============== SELECTION HELPERS ==============
    def _on_user_select(self, _evt=None):
        sel = self.users_list.curselection()
        if not sel:
            return
        self.selected_user = self.users_list.get(sel[0])
        self.open_user_chat()

    def _on_group_select(self, _evt=None):
        sel = self.groups_list.curselection()
        if not sel:
            return
        self.selected_group = self.groups_list.get(sel[0])
        self.open_group_chat()

    # ============== CHAT OPEN ==============
    def open_user_chat(self, _evt=None):
        if self.selected_user is None:
            sel = self.users_list.curselection()
            if not sel:
                return
            self.selected_user = self.users_list.get(sel[0])
        target = self.selected_user
        self.current_chat_target = target
        self.current_chat_is_group = False
        self.chat_title.config(text=f"Private: {target}")
        self.clear_typing()

        # reset and load history
        self.chat_history[target] = []
        try:
            self.network.request_private_history(target)
        except Exception as exc:
            messagebox.showerror("History Error", str(exc))

        self.render_chat()

    def open_group_chat(self, _evt=None):
        if self.selected_group is None:
            sel = self.groups_list.curselection()
            if not sel:
                return
            self.selected_group = self.groups_list.get(sel[0])
        target = self.selected_group
        self.current_chat_target = target
        self.current_chat_is_group = True
        self.chat_title.config(text=f"Group: {target}")
        self.clear_typing()

        self.chat_history[target] = []
        try:
            self.network.request_group_history(target)
        except Exception as exc:
            messagebox.showerror("History Error", str(exc))

        self.render_chat()

    # ============== GROUP ACTIONS ==============
    def join_group(self):
        name = self.join_group_entry.get().strip()
        if not name:
            messagebox.showwarning("Missing Group", "Enter a group name")
            return
        try:
            self.network.join_group(name)
            self.add_main_log(f"Join request sent: {name}")
            self.join_group_entry.delete(0, tk.END)
            self.show_main()
        except Exception as exc:
            messagebox.showerror("Join Error", str(exc))

    def leave_selected_group(self):
        group = self.selected_group
        if not group:
            messagebox.showwarning("No group", "Select a group first")
            return
        try:
            self.network.leave_group(group)
            self.add_main_log(f"Leave request sent: {group}")
        except Exception as exc:
            messagebox.showerror("Leave Error", str(exc))

    def view_group_members(self):
        group = self.selected_group
        if not group:
            messagebox.showwarning("No group", "Select a group first")
            return
        try:
            self.network.list_group_members(group)
        except Exception as exc:
            messagebox.showerror("Members Error", str(exc))

    def add_member_to_group(self):
        group = self.selected_group
        if not group:
            messagebox.showwarning("No group", "Select a group first")
            return
        username = simpledialog.askstring("Add Member", "Username to add to group:")
        if not username:
            return
        try:
            self.network.add_user_to_group(username.strip(), group)
        except Exception as exc:
            messagebox.showerror("Add Member Error", str(exc))

    def whois_selected_user(self):
        user = self.selected_user
        if not user:
            messagebox.showwarning("No user", "Select a user first")
            return
        try:
            self.network.whois(user)
        except Exception as exc:
            messagebox.showerror("Whois Error", str(exc))

    # ============== SENDING ==============
    def send_chat(self):
        if not self.current_chat_target:
            messagebox.showwarning("No chat", "Select a user or group from the left pane")
            return
        text = self.chat_input.get().strip()
        if not text:
            return
        channel = "GROUP" if self.current_chat_is_group else "PRIVATE"
        try:
            self.network.send_chat(self.current_chat_target, text, channel)
            self.chat_input.delete(0, tk.END)
            self._push_chat_line(self.current_chat_target, f"You: {text}", from_self=True)
        except Exception as exc:
            messagebox.showerror("Send Error", str(exc))

    def send_file(self):
        if not self.current_chat_target:
            messagebox.showwarning("No chat", "Select a user from the left pane first")
            return
        if self.current_chat_is_group:
            messagebox.showwarning("Not supported", "File transfer is only for private user chats")
            return
        path = filedialog.askopenfilename(title="Select file")
        if not path:
            return
        try:
            self.network.request_file(self.current_chat_target, path)
            self.add_main_log(
                f"File request sent to {self.current_chat_target}: {path.split('/')[-1]}"
            )
        except Exception as exc:
            messagebox.showerror("File Error", str(exc))

    # ============== QUEUE HANDLER ==============
    def process_ui_queue(self):
        while not self.uiq.empty():
            kind, data = self.uiq.get()

            if kind == "users":
                self.online_users = data
                self.refresh_lists()

            elif kind == "groups":
                self.joined_groups = data
                self.refresh_lists()

            elif kind == "group_members":
                group, members = data
                msg = "\n".join(members) if members else "(no members)"
                messagebox.showinfo("Group Members", f"Group: {group}\n\n{msg}")

            elif kind == "history":
                entries = data
                for e in entries:
                    chan = e["channel"].upper()
                    sender = e["sender"]
                    target = e["target"]
                    body = e["body"]
                    ts_val = e["ts"]

                    if chan == "GROUP":
                        key = target
                    else:
                        me = self.network.alias
                        if sender == me:
                            key = target
                        elif target == me:
                            key = sender
                        else:
                            key = sender or target

                    from_self = sender == self.network.alias
                    line = f"{sender}: {body}" if not from_self else f"You: {body}"
                    self._push_chat_line_from_ts(key, line, from_self, ts_val)

                self.render_chat()

            elif kind == "message":
                sender = data.get("from", "")
                target = data.get("to", "")
                body = data.get("body", "")
                channel = data.get("channel", "PRIVATE").upper()

                if channel == "GROUP":
                    key = target
                else:
                    me = self.network.alias
                    if sender == me:
                        key = target
                    elif target == me:
                        key = sender
                    else:
                        key = sender or target

                from_self = sender == self.network.alias
                line = f"{sender}: {body}" if not from_self else f"You: {body}"
                self._push_chat_line(key, line, from_self=from_self)
                self.add_main_log(f"New message from {sender}")

            elif kind == "typing":
                name = data
                if (not self.current_chat_is_group) and self.current_chat_target == name:
                    self.show_typing(name)

            elif kind == "whois":
                messagebox.showinfo("Whois", data)

            elif kind == "error":
                self.add_main_log(f"ERROR: {data}")

            elif kind == "log":
                self.add_main_log(data)

        self.root.after(100, self.process_ui_queue)

    # ============== UI HELPERS ==============
    def refresh_lists(self):
        self.users_list.delete(0, tk.END)
        for user in self.online_users:
            if user != self.network.alias:
                self.users_list.insert(tk.END, user)
        self.groups_list.delete(0, tk.END)
        for group in self.joined_groups:
            self.groups_list.insert(tk.END, group)

    def add_main_log(self, text: str):
        self.main_log.config(state=tk.NORMAL)
        self.main_log.insert(tk.END, f"{ts()} {text}\n")
        self.main_log.see(tk.END)
        self.main_log.config(state=tk.DISABLED)

    def _push_chat_line(self, chat_key: str, text: str, from_self: bool):
        # store with current timestamp
        self._push_chat_line_from_ts(chat_key, text, from_self, datetime.now().isoformat())

    def _push_chat_line_from_ts(self, chat_key: str, text: str, from_self: bool, ts_val: str):
        if not chat_key:
            return
        self.chat_history.setdefault(chat_key, []).append(
            {"ts": ts_val, "text": text, "self": from_self}
        )
        if self.current_chat_target == chat_key:
            self.render_chat()

    def render_chat(self):
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)

        if self.current_chat_target:
            last_date = None
            today_str = datetime.now().date().isoformat()

            for entry in self.chat_history.get(self.current_chat_target, []):
                ts_val = entry.get("ts", "")
                try:
                    date_str = ts_val.split("T", 1)[0]
                except Exception:
                    date_str = ""

                # Date separator
                if date_str and date_str != last_date:
                    label = "Today" if date_str == today_str else date_str
                    self.chat_text.insert(tk.END, f"--- {label} ---\n", "other")
                    last_date = date_str

                tag = "self" if entry["self"] else "other"

                time_part = ""
                if ts_val and "T" in ts_val:
                    time_part = ts_val.split("T", 1)[1][:5]

                line = entry["text"]
                if time_part:
                    line = f"{line}  {time_part}"

                self.chat_text.insert(tk.END, line + "\n", tag)

            self.chat_text.see(tk.END)

        self.chat_text.config(state=tk.DISABLED)

    # typing indicator
    def show_typing(self, name: str):
        self.typing_label.config(text=f"{name} is typing…")
        if self._typing_after_id is not None:
            self.root.after_cancel(self._typing_after_id)
        self._typing_after_id = self.root.after(1500, self.clear_typing)

    def clear_typing(self):
        self.typing_label.config(text="")
        if self._typing_after_id is not None:
            self.root.after_cancel(self._typing_after_id)
            self._typing_after_id = None

    def close(self):
        self.network.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    ChatGUIApp(root)
    root.mainloop()