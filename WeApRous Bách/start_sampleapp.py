#
# Copyright (C) 2025 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
#
# WeApRous release
#

"""
start_sampleapp (Tracker Server HoÃ n thiá»‡n)
~~~~~~~~~~~~~~~~~

This module provides the centralized "Tracker" server for the chat
application, handling peer registration, channel management, and message queuing
for the Web UI (Polling mechanism).
"""

import argparse
import json
import time
from daemon.weaprous import WeApRous

# Stores {peer_id: {'ip': str, 'port': int, 'messages': list}}
peer_storage = {} # tracker list
channel_storage = {'public': {}} 

# Default port 
PORT = 8000

app = WeApRous()

def json_response(status_code, status, message_or_data):
    """Helper to generate a complete HTTP JSON response."""
    if status == 'error':
        response_body = json.dumps({"status": status, "message": message_or_data})
    else:
        response_body = json.dumps({"status": status, **message_or_data})

    return (
        f"HTTP/1.1 {status_code} {status.upper()}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(response_body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
        f"{response_body}"
    ).encode('utf-8')
# -------------------------
def leave_all_channels(peer_id):
    """
    Helper function: Removes peer_id from ALL existing channels.
    This ensures the user is only in one channel at a time (Single-Room mode).
    """
    global channel_storage
    for ch_name in channel_storage:
        # Check if peer exists in this channel
        if peer_id in channel_storage[ch_name]:
            del channel_storage[ch_name][peer_id]
            print(f"[Tracker] Removed Peer {peer_id} from old channel: {ch_name}")
# -------------------------

@app.route('/submit-info', methods=['POST'])
def submit_info(headers="guest", body="anonymous"):
    """API 1: Handles peer registration (via peer_id)."""
    global peer_storage
    try:
        data = json.loads(body)
        peer_id = data.get('peer_id')
        ip = data.get('ip')
        port = int(data.get('port')) 

        if not peer_id or not ip or not port:
            return json_response(400, "error", "Missing 'peer_id', 'ip', or 'port' in JSON body")

        # 1. Store peer info and init message queue
        peer_storage[peer_id] = {
            'ip': ip, 
            'port': port, 
            'messages': [] # Message Queue
        }
        leave_all_channels(peer_id)
        # 2. Add to public channel by default
        global channel_storage
        channel_storage['public'][peer_id] = peer_id

        print(f"[Tracker] Registered peer: {peer_id} at {ip}:{port}. Total peers: {len(peer_storage)}")
        
        return json_response(200, "success", {"peer_id": peer_id, "message": "Peer registered"})
        
    except Exception as e:
        print(f"[Tracker] Error in /submit-info: {e}")
        return json_response(400, "error", f"Error processing request: {e}")


@app.route('/get-list', methods=['GET'])
def get_list(headers="guest", body="anonymous"):
    """API 2: Handles peer discovery and list all channels."""
    
    # Clean peer_storage to return a simplified list {peer_id: "ip:port"}
    simplified_peers = {
        pid: f"{data['ip']}:{data['port']}" 
        for pid, data in peer_storage.items()
    }
    
    # Clean channel_storage to return simplified list {channel_name: member_count}
    simplified_channels = {
        cname: len(members) for cname, members in channel_storage.items()
    }
    
    data = {
        "peers": simplified_peers,
        "lists": simplified_channels # UI calls this 'lists'
    }
    
    print(f"[Tracker] Sending peer/channel list. Peers: {len(peer_storage)}")
    
    return json_response(200, "success", data)

# /add-list -> /create-list
@app.route('/create-list', methods=['POST'])
def create_list(headers="guest", body="anonymous"):
    """API 3: Handles channel creation and automatically joins the creator."""
    try:
        data = json.loads(body)
        list_name = data.get('list_name')
        peer_id = data.get('peer_id')
        
        if not list_name or not peer_id:
            return json_response(400, "error", "Missing 'list_name' or 'peer_id'")

        if list_name in channel_storage:
             return json_response(400, "error", f"Channel '{list_name}' already exists.")

        if peer_id not in peer_storage:
             return json_response(400, "error", f"Peer ID '{peer_id}' not registered.")
        leave_all_channels(peer_id)
        # 1. Create the channel
        channel_storage[list_name] = {}
        
        # 2. Add creator to the channel
        channel_storage[list_name][peer_id] = peer_id

        print(f"[Tracker] Channel created: {list_name} by {peer_id}")
        
        return json_response(200, "success", {"list_name": list_name, "message": "Channel created and joined"})
        
    except Exception as e:
        return json_response(400, "error", f"Error creating channel: {e}")


@app.route('/send-message', methods=['POST'])
def send_message(headers="guest", body="anonymous"):
    """
    API 4: Handles message push to target Peer or Channel message queue.
    /connect-peer and /broadcast-peer 
    """
    try:
        data = json.loads(body)
        sender_id = data.get('sender_id')
        target_id = data.get('target_id')
        message = data.get('message')

        if not sender_id or not target_id or not message:
            return json_response(400, "error", "Missing sender, target, or message.")

        new_message = {
            'sender': sender_id,
            'message': message,
            'timestamp': time.time()
        }

        # --- LOGIC Gá»¬I Äáº¾N PEER Cá»¤ THá»‚ (DIRECT) ---
        if target_id in peer_storage:
            peer_storage[target_id]['messages'].append(new_message)
            print(f"[Tracker] Direct message from {sender_id} to {target_id}")
            
        # --- LOGIC Gá»¬I Äáº¾N KÃŠNH (BROADCAST) ---
        elif target_id in channel_storage:
            # QUAN TRá»ŒNG: Gáº¯n thÃªm tÃªn kÃªnh vÃ o tin nháº¯n Ä‘á»ƒ ngÆ°á»i nháº­n biáº¿t Ä‘Ã¢y lÃ  tin nhÃ³m
            channel_message = new_message.copy()
            channel_message['channel'] = target_id 

            members = channel_storage[target_id]
            for pid in members.keys():
                if pid != sender_id: 
                    if pid in peer_storage:
                        # Gá»­i gÃ³i tin Ä‘Ã£ cÃ³ info channel
                        peer_storage[pid]['messages'].append(channel_message)
            print(f"[Tracker] Broadcast from {sender_id} to Channel {target_id} ({len(members)} members)")
        else:
            return json_response(400, "error", f"Target ID '{target_id}' is not a valid Peer or Channel.")

        return json_response(200, "success", {"message": "Message queued"})
        
    except Exception as e:
        return json_response(400, "error", f"Error sending message: {e}")


@app.route('/get-messages', methods=['POST'])
def get_messages(headers="guest", body="anonymous"):
    """API 5: Handles message pull from Peer's message queue (Polling)."""
    try:
        data = json.loads(body)
        peer_id = data.get('peer_id')

        if not peer_id:
            return json_response(400, "error", "Missing 'peer_id'.")

        peer_data = peer_storage.get(peer_id)
        if not peer_data:
            return json_response(400, "error", f"Peer ID '{peer_id}' not found.")

        # Tráº£ vá» táº¥t cáº£ tin nháº¯n trong queue vÃ  xÃ³a queue Ä‘Ã³
        messages = peer_data['messages']
        peer_data['messages'] = []
        
        return json_response(200, "success", {"messages": messages})

    except Exception as e:
        return json_response(400, "error", f"Error retrieving messages: {e}")
    

@app.route('/join-list', methods=['POST'])
def join_list(headers="guest", body="anonymous"):
    """API X: Handles joining an existing channel."""
    global channel_storage
    try:
        data = json.loads(body)
        list_name = data.get('list_name')
        peer_id = data.get('peer_id')
        
        if not list_name or not peer_id:
            return json_response(400, "error", "Missing 'list_name' or 'peer_id'")

        # 1. Check if the channel exists
        if list_name not in channel_storage:
            return json_response(400, "error", f"Channel '{list_name}' not found.")

        # 2. Check if the peer is registered
        if peer_id not in peer_storage:
             return json_response(400, "error", f"Peer ID '{peer_id}' not registered.")

        # 3. Check if peer is already a member
        if peer_id in channel_storage[list_name]:
             return json_response(400, "error", f"Peer ID '{peer_id}' already a member of '{list_name}'.")
        leave_all_channels(peer_id)
        # 4. Add peer to the channel
        channel_storage[list_name][peer_id] = peer_id
        
        system_msg = {
            'sender': 'SYSTEM',
            'message': f'ðŸ‘‹ {peer_id} Ä‘Ã£ tham gia kÃªnh.',
            'timestamp': time.time(),
            'channel': list_name # Gáº¯n tháº» kÃªnh
        }

        print(f"[Tracker] Peer {peer_id} joined Channel: {list_name}")
        
        return json_response(200, "success", {"list_name": list_name, "message": "Channel joined successfully"})
        
    except Exception as e:
        return json_response(400, "error", f"Error joining channel: {e}")

# Giá»¯ láº¡i logic login/get-list/submit-info cÅ© (náº¿u cÃ³) nhÆ°ng á»Ÿ Ä‘Ã¢y chÃºng ta Ä‘Ã£ thay tháº¿ báº±ng logic Chat API.
# RiÃªng API /login, báº¡n sáº½ tháº¥y nÃ³ váº«n cÃ²n trong file start_sampleapp.py cÅ©. 
# Tuy nhiÃªn, chá»©c nÄƒng login HTTP (Task 1) Ä‘Æ°á»£c xá»­ lÃ½ bá»Ÿi HttpAdapter trong Backend Server (start_backend.py)
# nÃªn tÃ´i sáº½ loáº¡i bá» logic Login/Hello cÅ© khá»i file nÃ y, chá»‰ giá»¯ láº¡i cÃ¡c API chat.

if __name__ == "__main__":
    """Entry point for launching the Tracker server."""
    
    parser = argparse.ArgumentParser(
        prog='TrackerServer',
        description='Start the Hybrid Chat Tracker process',
        epilog='Tracker daemon for http_daemon application'
    )
    parser.add_argument('--server-ip',
        type=str,
        default='0.0.0.0',
        help='IP address to bind the server. Default is 0.0.0.0'
    )
    parser.add_argument(
        '--server-port',
        type=int,
        default=PORT,
        help=f'Port number to bind the server. Default is {PORT}.'
    )
 
    args = parser.parse_args()
    ip = args.server_ip
    port = args.server_port

    # Configure the WeApRous app with the IP and Port
    app.prepare_address(ip, port)
    

    print("*" * 60)
    print("Starting Chat Tracker Server")
    print("IP: {}".format(ip))
    print("Port: {}".format(port))
    print("*" * 60)
    
    # Start the server
    app.run()