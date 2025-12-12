#
# start_webpeer.py (Refactored to match Sample Code Logic)
#

import json
import argparse
import threading
from daemon.weaprous import WeApRous
from chat_client import PeerClient 

PORT = 8002

peer_instances = {}
peer_instances_lock = threading.Lock()

app = WeApRous()

def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
        "Content-Type": "application/json"
    }

# --- OPTIONS HANDLERS ---
@app.route('/init-peer', methods=['OPTIONS'])
@app.route('/connect-peer', methods=['OPTIONS'])
@app.route('/send-peer', methods=['OPTIONS'])
@app.route('/broadcast-peer', methods=['OPTIONS'])
@app.route('/get-messages', methods=['OPTIONS'])
@app.route('/join-channel', methods=['OPTIONS'])
@app.route('/status', methods=['OPTIONS'])
def handle_options(headers="guest", body="anonymous"):
    return ("200 OK", get_cors_headers(), "")

# --- API HANDLERS ---

@app.route('/init-peer', methods=['POST'])
def init_peer(headers="guest", body="anonymous"):
    print("[WebPeer] Init peer request")
    try:
        data = json.loads(body) if body and body != "anonymous" else {}
        username = data.get("username", "")
        peer_port = data.get("peer_port", 0)
        
        # FIX: Point to port 8001 by default
        tracker_ip = data.get("tracker_ip", "127.0.0.1")
        tracker_port = data.get("tracker_port", 8001) 
        
        if not username or not peer_port:
            return ("400 Bad Request", get_cors_headers(), json.dumps({"status": "failed"}))
        
        with peer_instances_lock:
            if username in peer_instances:
                try: peer_instances[username].stop()
                except: pass
            
            peer = PeerClient(username, "127.0.0.1", peer_port, tracker_ip, tracker_port)
            peer.start() 
            peer.register_with_tracker()
            
            peer_instances[username] = peer
            print(f"[WebPeer] Initialized: {username}:{peer_port}")
        
        return ("200 OK", get_cors_headers(), json.dumps({"status": "success", "message": "Initialized"}))
    except Exception as e:
        return ("500 Error", get_cors_headers(), json.dumps({"status": "error", "message": str(e)}))

@app.route('/connect-peer', methods=['POST'])
def connect_peer(headers="guest", body="anonymous"):
    try:
        data = json.loads(body)
        username = data.get("username")
        peer_username = data.get("peer_username")
        peer_ip = data.get("peer_ip")
        peer_port = data.get("peer_port")
        
        with peer_instances_lock:
            if username not in peer_instances:
                return ("400 Bad Request", get_cors_headers(), json.dumps({"status": "failed", "message": "Not initialized"}))
            peer = peer_instances[username]
        
        success = peer.connect_peer(peer_username, peer_ip, peer_port)
        status = "success" if success else "failed"
        return ("200 OK", get_cors_headers(), json.dumps({"status": status}))
    except Exception as e:
        return ("500 Error", get_cors_headers(), json.dumps({"status": "error", "message": str(e)}))

@app.route('/join-channel', methods=['POST'])
def join_channel(headers="guest", body="anonymous"):
    try:
        data = json.loads(body)
        username = data.get("username")
        channel = data.get("channel")
        
        with peer_instances_lock:
            if username not in peer_instances:
                return ("400 Bad Request", get_cors_headers(), json.dumps({"status": "failed"}))
            peer = peer_instances[username]
            
        success = peer.join_channel(channel)
        return ("200 OK", get_cors_headers(), json.dumps({"status": "success" if success else "failed"}))
    except Exception as e:
        return ("500 Error", get_cors_headers(), json.dumps({"status": "error", "message": str(e)}))

@app.route('/send-peer', methods=['POST'])
def send_peer(headers="guest", body="anonymous"):
    try:
        data = json.loads(body)
        username = data.get("username")
        peer_username = data.get("peer_username")
        message = data.get("message")
        
        with peer_instances_lock:
            if username not in peer_instances:
                return ("400 Bad Request", get_cors_headers(), json.dumps({"status": "failed"}))
            peer = peer_instances[username]
        
        success = peer.send_peer(peer_username, message)
        return ("200 OK", get_cors_headers(), json.dumps({"status": "success" if success else "failed"}))
    except Exception as e:
        return ("500 Error", get_cors_headers(), json.dumps({"message": str(e)}))

@app.route('/broadcast-peer', methods=['POST'])
def broadcast_peer(headers="guest", body="anonymous"):
    try:
        data = json.loads(body)
        username = data.get("username")
        message = data.get("message")
        channel = data.get("channel", "broadcast")
        
        with peer_instances_lock:
            if username not in peer_instances:
                return ("400 Bad Request", get_cors_headers(), json.dumps({"status": "failed"}))
            peer = peer_instances[username]
        
        count = peer.broadcast_peer(message, channel)
        return ("200 OK", get_cors_headers(), json.dumps({"status": "success", "count": count}))
    except Exception as e:
        return ("500 Error", get_cors_headers(), json.dumps({"message": str(e)}))

@app.route('/get-messages', methods=['POST'])
def get_messages(headers="guest", body="anonymous"):
    try:
        data = json.loads(body)
        username = data.get("username")
        channel = data.get("channel", None)
        
        with peer_instances_lock:
            if username not in peer_instances:
                return ("200 OK", get_cors_headers(), json.dumps({"status": "success", "messages": []}))
            peer = peer_instances[username]
        
        messages = peer.get_messages(channel)
        return ("200 OK", get_cors_headers(), json.dumps({"status": "success", "messages": messages}))
    except Exception as e:
        return ("500 Error", get_cors_headers(), json.dumps({"message": str(e)}))

@app.route('/status', methods=['GET'])
def status(headers="guest", body="anonymous"):
    with peer_instances_lock:
        active = len(peer_instances)
    return ("200 OK", get_cors_headers(), json.dumps({"status": "online", "active_peers": active}))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-ip', default='0.0.0.0')
    parser.add_argument('--server-port', type=int, default=PORT)
    args = parser.parse_args()

    print(f"Starting WebPeer Bridge at {args.server_ip}:{args.server_port}")
    app.prepare_address(args.server_ip, args.server_port)
    app.run()