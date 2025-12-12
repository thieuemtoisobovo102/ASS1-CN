import socket
import threading
import requests
import json
import time
import sys

# --- CONFIGURATION ---
TRACKER_URL = "http://127.0.0.1:8000" # The address of your start_sampleapp.py server
# ---------------------

def get_my_ip():
    """Finds the local IP address used for outbound connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)) # Connect to Google's DNS
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1" # Fallback
    finally:
        s.close()
    return ip

class P2PChatClient:
    def __init__(self,username, my_port):
        self.username = username
        self.my_port = my_port
        self.my_ip = get_my_ip()
        self.tracker_url = TRACKER_URL
        
        # Sockets we are *sending* data to
        self.outgoing_connections = []
        
        print(f"[Client] Starting as {self.username} at {self.my_ip}:{self.my_port}")

    def start_server_thread(self):
        """
        This thread listens for INCOMING connections from other peers.
        """
        # Create a TCP socket to listen for connections
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(('', self.my_port)) # Listen on all interfaces at my port
        server_socket.listen(5)
        
        print(f"[Server] Listening for peers on port {self.my_port}...")
        
        while True:
            try:
                # Wait for a peer to connect
                peer_socket, peer_address = server_socket.accept()
                print(f"[Server] Accepted connection from: {peer_address}")
                
                # Start a new thread to handle messages from this *specific* peer
                handler_thread = threading.Thread(
                    target=self.handle_peer_messages, 
                    args=(peer_socket, peer_address), 
                    daemon=True
                )
                handler_thread.start()
            except Exception as e:
                print(f"[Server] Error accepting connection: {e}")

    def register_with_tracker(self):
        """
        Calls the /submit-info API on the tracker server.
        """
        payload = {
            "peer_id": self.username,  # ThÃªm dÃ²ng nÃ y
            "ip": self.my_ip,
            "port": self.my_port
        }
        try:
            r = requests.post(f"{self.tracker_url}/submit-info", json=payload)
            if r.status_code == 200:
                print(f"[Tracker] Registered successfully: {r.json()}")
            else:
                # In ra lá»—i chi tiáº¿t tá»« server Ä‘á»ƒ dá»… debug
                print(f"[Tracker] Failed to register. Status: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"[Tracker] ERROR: Could not connect to tracker: {e}")
    def get_and_connect_to_peers(self):
        """
        Calls /get-list and connects to all peers (except self).
        This is the "client" part of the P2P connection.
        """
        try:
            r = requests.get(f"{self.tracker_url}/get-list")
            if r.status_code != 200:
                print(f"[Tracker] Could not get peer list. Status: {r.status_code}")
                return
                
            response_data = r.json() 
            peers_map = response_data.get("peers", {}) 
            
            print(f"[Tracker] Got peer list: {peers_map}")
            
            # --- This is the core P2P connection logic ---
            for peer_id, addr_str in peers_map.items():
                try:
                    target_ip, target_port_str = addr_str.split(":")
                    target_port = int(target_port_str)
                except ValueError:
                    print(f"[Client] Invalid address format for {peer_id}: {addr_str}")
                    continue

                # Kiá»ƒm tra náº¿u lÃ  chÃ­nh mÃ¬nh thÃ¬ bá» qua
                if (target_ip, target_port) == (self.my_ip, self.my_port):
                    continue 
                
                # Kiá»ƒm tra xem Ä‘Ã£ káº¿t ná»‘i chÆ°a
                if any(sock.getpeername() == (target_ip, target_port) for sock in self.outgoing_connections):
                    continue
                    
                try:
                    # Táº¡o káº¿t ná»‘i socket (OUTGOING connection)
                    peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    peer_socket.connect((target_ip, target_port))
                    print(f"[Client] Connected to peer {peer_id}: {(target_ip, target_port)}")
                    
                    # LÆ°u vÃ o danh sÃ¡ch káº¿t ná»‘i
                    self.outgoing_connections.append(peer_socket)
                    
                except Exception as e:
                    print(f"[Client] Failed to connect to peer {(target_ip, target_port)}: {e}")
                    
        except Exception as e:
            print(f"[Tracker] ERROR: Could not get peer list: {e}")

    def handle_peer_messages(self, peer_socket, peer_address):
        """
        This thread handles RECEIVING messages from a single peer.
        Direct Peer Communication
        """
        while True:
            try:
                data = peer_socket.recv(1024)
                if not data:
                    break # Peer disconnected
                
                print(f"\n[Message from {peer_address}]: {data.decode('utf-8')}\n> ", end="")
                
            except Exception as e:
                print(f"[Handler] Error with {peer_address}: {e}")
                break
        
        print(f"[Handler] Peer {peer_address} disconnected.")
        peer_socket.close()

    def broadcast_message(self, message):
        """
        Sends a message to all connected peers.
        Broadcast Connection
        """
        print(f"[Broadcast] Sending '{message}' to {len(self.outgoing_connections)} peers.")
        for sock in self.outgoing_connections:
            try:
                sock.sendall(message.encode('utf-8'))
            except Exception as e:
                print(f"[Broadcast] Failed to send to {sock.getpeername()}: {e}")
                # Remove broken socket
                self.outgoing_connections.remove(sock)

    def run(self):
        # 1. Start the listening server in a background thread
        server_thread = threading.Thread(target=self.start_server_thread, daemon=True)
        server_thread.start()
        
        # 2. Register with the tracker
        self.register_with_tracker()
        
        # 3. Get peers and connect (first time)
        self.get_and_connect_to_peers()
        
        print("\n--- Chat Started. Type a message and press Enter to broadcast. ---")
        
        # 4. Main loop for user input (broadcast)
        try:
            while True:
                # Refresh peer list every 10 seconds (simple way to find new peers)
                time.sleep(10)
                print("\n[Client] Refreshing peer list...")
                self.get_and_connect_to_peers()
                
                message = input("> ")
                if message:
                    self.broadcast_message(message)
                    
        except KeyboardInterrupt:
            print("\n[Client] Shutting down...")
            for sock in self.outgoing_connections:
                sock.close()
            print("[Client] Goodbye.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python chat_client.py <username> <my_port>")
        print("Example: python chat_client.py bach 9090")
        sys.exit(1)
    username = sys.argv[1]
    my_port = int(sys.argv[2])
    
    client = P2PChatClient(username,my_port)
    client.run()