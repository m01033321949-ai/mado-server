
from flask import Flask, request, jsonify
from flask_cors import CORS
import json, os, time
from datetime import datetime

app = Flask(__name__)
CORS(app)

DATA_FILE = "/tmp/mado_users.json"
if not os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
    except:
        pass

def load_users():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except:
        pass

@app.route('/')
def index():
    return jsonify({"status": "MADO Server Running on Netlify", "api": "/api/auth"})

@app.route('/api/auth', methods=['POST', 'GET'])
def auth():
    data = request.json if request.is_json else {}
    hwid = data.get('hwid','').strip().upper() if data.get('hwid') else request.args.get('hwid','').strip().upper()
    if not hwid: return jsonify({"ok": False, "msg": "HWID ناقص"}), 400
    users = load_users()
    if hwid not in users:
        users[hwid] = {
            "hwid": hwid,
            "name": data.get('pc_name','Unknown'),
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "is_online": True,
            "status": "idle",
            "enabled": True,
            "force_stop": False,
            "expiry": int(time.time()) + 30*86400,
            "stats": {"likes":0,"saves":0,"reposts":0,"comments":0,"total":0},
            "version": data.get('version','v4.1'),
        }
        save_users(users)
    user = users[hwid]
    if not user.get("enabled", True):
        return jsonify({"ok": False, "msg": "موقوف", "banned": True}), 403
    if time.time() > user.get("expiry", 0):
        return jsonify({"ok": False, "msg": "انتهى الاشتراك", "expired": True}), 403
    user["last_seen"] = datetime.now().isoformat()
    user["is_online"] = True
    save_users(users)
    return jsonify({"ok": True, "msg": "مرخص", "expiry_date": datetime.fromtimestamp(user["expiry"]).strftime("%Y-%m-%d"), "force_stop": user.get("force_stop", False)})

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json or {}
    hwid = data.get('hwid','').strip().upper()
    users = load_users()
    if hwid not in users: return jsonify({"ok": False}), 404
    user = users[hwid]
    if not user.get("enabled", True): return jsonify({"ok": False, "action":"ban"}), 403
    if time.time() > user.get("expiry", 0): return jsonify({"ok": False, "action":"expire"}), 403
    user["last_seen"] = datetime.now().isoformat()
    user["status"] = data.get('status','idle')
    user["stats"] = data.get('stats', user.get('stats', {}))
    action = "none"
    if user.get("force_stop"):
        action = "stop"
        user["force_stop"] = False
    save_users(users)
    return jsonify({"ok": True, "action": action})

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    users = load_users()
    now = datetime.now()
    result=[]
    for hwid, u in users.items():
        try:
            last = datetime.fromisoformat(u.get('last_seen',''))
            diff = (now-last).total_seconds()
            u['is_online'] = diff < 120
            u['last_seen_ago'] = f"{int(diff//60)} دقيقة" if diff>60 else f"{int(diff)} ث"
        except:
            u['is_online']=False
            u['last_seen_ago']="غير معروف"
        result.append(u)
    result.sort(key=lambda x: (not x.get('is_online', False)))
    return jsonify(result)

@app.route('/api/admin/user/<hwid>/stop', methods=['POST'])
def stop_user(hwid):
    hwid=hwid.upper()
    users=load_users()
    if hwid in users:
        users[hwid]["force_stop"]=True
        save_users(users)
    return jsonify({"ok": True})

@app.route('/api/admin/user/<hwid>/toggle', methods=['POST'])
def toggle_user(hwid):
    hwid=hwid.upper()
    users=load_users()
    if hwid in users:
        users[hwid]["enabled"]=not users[hwid].get("enabled", True)
        save_users(users)
        return jsonify({"ok": True, "enabled": users[hwid]["enabled"]})
    return jsonify({"ok": False}), 404

@app.route('/api/admin/stats', methods=['GET'])
def stats():
    users=load_users()
    total=len(users)
    now=datetime.now()
    online=0
    for u in users.values():
        try:
            last=datetime.fromisoformat(u.get('last_seen',''))
            if (now-last).total_seconds() < 120: online+=1
        except: pass
    return jsonify({"total":total,"online":online,"offline":total-online})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
