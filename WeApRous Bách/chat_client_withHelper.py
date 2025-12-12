import socket
import threading
import requests
import json
import time
import sys
import argparse

# --- CẤU HÌNH ---
# Đảm bảo port này khớp với port bạn chạy start_sampleapp.py (thường là 8001 theo README)
TRACKER_URL = "http://127.0.0.1:8001" 

def get_my_ip():
    """Lấy IP LAN của máy hiện tại."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

class P2PChatClient:
    def __init__(self, username, my_port, tracker_url):
        self.username = username
        self.my_port = my_port
        self.my_ip = get_my_ip()
        self.tracker_url = tracker_url
        self.running = True
        
        # Quản lý kết nối P2P: { 'username': socket_obj }
        self.peers = {} 
        # Để mapping ngược từ socket sang username khi nhận tin
        self.socket_to_user = {}

        print(f"\n[SYSTEM] Client started as '{self.username}' at {self.my_ip}:{self.my_port}")

    # --- PHẦN 1: TƯƠNG TÁC VỚI TRACKER (HTTP) ---

    def register_with_tracker(self):
        payload = {"peer_id": self.username, "ip": self.my_ip, "port": self.my_port}
        try:
            r = requests.post(f"{self.tracker_url}/submit-info", json=payload)
            if r.status_code == 200:
                print("[TRACKER] Registered successfully.")
            else:
                print(f"[TRACKER] Registration failed: {r.text}")
        except Exception as e:
            print(f"[TRACKER] Error connecting to tracker: {e}")

    def get_peer_list(self):
        try:
            r = requests.get(f"{self.tracker_url}/get-list")
            if r.status_code == 200:
                data = r.json()
                print("\n--- AVAILABLE PEERS & CHANNELS ---")
                print("Peers:", data.get("peers", {}))
                print("Channels:", data.get("lists", {}))
                print("----------------------------------")
                return data
            else:
                print(f"[TRACKER] Error getting list: {r.status_code}")
        except Exception as e:
            print(f"[TRACKER] Connection error: {e}")
        return None

    def join_channel_api(self, channel_name):
        """Gọi API join-list hoặc create-list trên Tracker"""
        # Thử tạo trước (nếu chưa có), sau đó join logic được xử lý bởi server
        # Lưu ý: Code server mẫu của bạn gộp logic create/join khá linh hoạt
        # Ở đây ta giả lập hành động 'join' bằng cách gọi API tương ứng
        payload = {"list_name": channel_name, "peer_id": self.username}
        try:
            # Thử tạo channel (nếu chưa tồn tại)
            r = requests.post(f"{self.tracker_url}/create-list", json=payload)
            if r.status_code == 200:
                print(f"[CHANNEL] Created and joined channel '{channel_name}'")
                return

            # Nếu tạo thất bại (do đã tồn tại), thì gọi join
            r = requests.post(f"{self.tracker_url}/join-list", json=payload)
            if r.status_code == 200:
                print(f"[CHANNEL] Joined channel '{channel_name}'")
            else:
                print(f"[CHANNEL] Failed to join: {r.text}")
        except Exception as e:
            print(f"[CHANNEL] Error: {e}")

    # --- PHẦN 2: KẾT NỐI SOCKET P2P (TCP) ---

    def start_server_thread(self):
        """Lắng nghe kết nối đến từ các Peer khác."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind(('', self.my_port))
            server_socket.listen(5)
            # print(f"[P2P] Listening for incoming connections on port {self.my_port}...")
            
            while self.running:
                try:
                    client_sock, addr = server_socket.accept()
                    # Khởi tạo luồng nhận tin nhắn cho kết nối mới này
                    threading.Thread(target=self.handle_incoming_message, args=(client_sock,), daemon=True).start()
                except OSError:
                    break
        except Exception as e:
            print(f"[P2P SERVER ERROR] {e}")
        finally:
            server_socket.close()

    def handle_incoming_message(self, sock):
        """Xử lý tin nhắn nhận được từ một Peer."""
        peer_name = "Unknown"
        try:
            # Bước bắt tay đầu tiên: Nhận tên của người gửi
            peer_name = sock.recv(1024).decode('utf-8')
            if not peer_name: return
            
            # Lưu vào danh sách kết nối
            self.peers[peer_name] = sock
            self.socket_to_user[sock] = peer_name
            print(f"\n[P2P] Connected with peer: {peer_name}")
            print("> ", end="", flush=True)

            while self.running:
                data = sock.recv(4096)
                if not data: break
                msg = data.decode('utf-8')
                print(f"\n[Message from {peer_name}]: {msg}")
                print("> ", end="", flush=True)
        except Exception:
            pass
        finally:
            print(f"\n[P2P] Peer {peer_name} disconnected.")
            if peer_name in self.peers: del self.peers[peer_name]
            sock.close()
            print("> ", end="", flush=True)

    def connect_to_peer(self, target_username, target_ip, target_port):
        """Chủ động kết nối tới một Peer khác."""
        if target_username in self.peers:
            print(f"[P2P] Already connected to {target_username}")
            return

        if target_username == self.username:
            print("[P2P] Cannot connect to yourself.")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((target_ip, int(target_port)))
            
            # Gửi tên mình để định danh (Handshake đơn giản)
            s.sendall(self.username.encode('utf-8'))
            
            self.peers[target_username] = s
            self.socket_to_user[s] = target_username
            
            # Bắt đầu luồng lắng nghe chiều ngược lại
            threading.Thread(target=self.handle_incoming_message, args=(s,), daemon=True).start()
            # print(f"[P2P] Successfully connected to {target_username}")
        except Exception as e:
            print(f"[P2P] Failed to connect to {target_username}: {e}")

    def send_direct(self, target_username, message):
        """Gửi tin nhắn riêng (Unicast)."""
        if target_username not in self.peers:
            print(f"[ERROR] Not connected to {target_username}. Use 'connect' first.")
            return
        try:
            self.peers[target_username].sendall(message.encode('utf-8'))
            print(f"[Me -> {target_username}]: {message}")
        except Exception as e:
            print(f"[ERROR] Sending failed: {e}")

    def broadcast(self, message):
        """Gửi tin nhắn cho tất cả Peer đã kết nối."""
        if not self.peers:
            print("[INFO] No peers connected.")
            return
        print(f"[Broadcast -> {len(self.peers)} peers]: {message}")
        for peer, sock in self.peers.items():
            try:
                sock.sendall(message.encode('utf-8'))
            except:
                pass

    # --- PHẦN 3: GIAO DIỆN DÒNG LỆNH (CLI) ---

    def print_help(self):
        print("\n--- COMMANDS ---")
        print("1. list                  : Show online peers & channels")
        print("2. join <channel>        : Join/Create a channel (Tracker)")
        print("3. connect <user> <ip> <port> : Connect to a peer (P2P)")
        print("4. send <user> <msg>     : Send direct message")
        print("5. broadcast <msg>       : Send to all connected peers")
        print("6. help                  : Show this menu")
        print("7. exit                  : Quit")
        print("----------------")

    def run(self):
        # 1. Start Server Thread (Background)
        threading.Thread(target=self.start_server_thread, daemon=True).start()
        
        # 2. Register
        self.register_with_tracker()
        
        # 3. Main Loop
        self.print_help()
        time.sleep(0.5) # Chờ in ấn ổn định
        
        while self.running:
            try:
                cmd_input = input("> ").strip()
                if not cmd_input: continue
                
                parts = cmd_input.split()
                cmd = parts[0].lower()
                
                if cmd == "list":
                    self.get_peer_list()
                    
                elif cmd == "join":
                    if len(parts) < 2: print("Usage: join <channel_name>"); continue
                    self.join_channel_api(parts[1])
                    
                elif cmd == "connect":
                    # Cú pháp: connect alice 127.0.0.1 9000
                    if len(parts) < 4: 
                        print("Usage: connect <username> <ip> <port>")
                        # Tự động fetch list để user tiện nhìn
                        data = self.get_peer_list() 
                        continue
                    self.connect_to_peer(parts[1], parts[2], int(parts[3]))
                    
                elif cmd == "send":
                    # Cú pháp: send alice Hello there
                    if len(parts) < 3: print("Usage: send <username> <message>"); continue
                    target = parts[1]
                    msg = " ".join(parts[2:])
                    self.send_direct(target, msg)
                    
                elif cmd == "broadcast":
                    if len(parts) < 2: print("Usage: broadcast <message>"); continue
                    msg = " ".join(parts[1:])
                    self.broadcast(msg)
                    
                elif cmd == "help":
                    self.print_help()
                    
                elif cmd == "exit":
                    self.running = False
                    print("Bye!")
                    sys.exit(0)
                else:
                    print("Unknown command. Type 'help'.")
                    
            except KeyboardInterrupt:
                print("\nExiting...")
                self.running = False
                break
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2P Chat Client")
    parser.add_argument("--username", required=True, help="Your display name")
    parser.add_argument("--peer-port", type=int, required=True, help="Port to listen for P2P connections")
    parser.add_argument("--tracker-ip", default="127.0.0.1", help="Tracker IP")
    parser.add_argument("--tracker-port", type=int, default=8001, help="Tracker Port") # Default 8001 như README

    args = parser.parse_args()
    
    # Cập nhật URL Tracker từ tham số
    TRACKER_URL = f"http://{args.tracker_ip}:{args.tracker_port}"
    
    client = P2PChatClient(args.username, args.peer_port, TRACKER_URL)
    client.run()