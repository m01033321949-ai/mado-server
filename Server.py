"""
MADO Online Server - لوحة تحكم واشتراكات
شغله على أي سيرفر (Render / Railway / VPS)
pip install flask flask-cors
python server.py
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json, os, time, hashlib
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

DATA_FILE = "mado_users.json"
SECRET_SALT = "MADO_V4_SALT_@2026!_Mngf"

# إنشاء ملف البيانات لو مش موجود
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f)

def load_users():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def verify_license_signature(hwid, exp, sig):
    raw = f"{hwid}|{exp}|{SECRET_SALT}"
    expected = hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
    return sig == expected

# ========== API للعميل (البرنامج) ==========

@app.route('/api/auth', methods=['POST'])
def auth():
    """العميل بيعمل auth أول ما يفتح"""
    data = request.json
    hwid = data.get('hwid','').strip().upper()
    license_key = data.get('license_key','').strip()
    
    if not hwid:
        return jsonify({"ok": False, "msg": "HWID ناقص"}), 400
    
    users = load_users()
    
    # لو أول مرة يشوفه، يسجله
    if hwid not in users:
        users[hwid] = {
            "hwid": hwid,
            "name": data.get('pc_name', 'Unknown PC'),
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "is_online": True,
            "status": "idle", # idle, running, paused
            "enabled": True,
            "force_stop": False,
            "expiry": int(time.time()) + 30*86400, # 30 يوم افتراضي للتجربة
            "stats": {"likes":0, "saves":0, "reposts":0, "comments":0, "total":0},
            "version": data.get('version','v4.1'),
            "ip": request.remote_addr
        }
        save_users(users)
    
    user = users[hwid]
    
    # تحقق من الترخيص لو مبعوت
    if license_key:
        try:
            import base64
            payload = base64.b64decode(license_key.encode()).decode()
            l_hwid, exp, sig = payload.split("-")
            l_hwid = l_hwid.upper()
            exp = int(exp)
            if l_hwid == hwid and verify_license_signature(l_hwid, exp, sig):
                user["expiry"] = exp
                user["license_valid"] = True
            else:
                user["license_valid"] = False
        except:
            user["license_valid"] = False
    else:
        user["license_valid"] = False
    
    # تحقق هل ممنوع؟
    if not user.get("enabled", True):
        return jsonify({"ok": False, "msg": "تم إيقاف حسابك - تواصل مع الإدارة", "banned": True}), 403
    
    # تحقق هل انتهت الصلاحية؟
    if time.time() > user.get("expiry", 0):
        return jsonify({"ok": False, "msg": "انتهت صلاحية الاشتراك", "expired": True}), 403
    
    # تحديث آخر ظهور
    user["last_seen"] = datetime.now().isoformat()
    user["is_online"] = True
    user["ip"] = request.remote_addr
    user["pc_name"] = data.get('pc_name', user.get('pc_name'))
    save_users(users)
    
    # هل فيه أمر إيقاف من الأدمن؟
    response = {
        "ok": True,
        "msg": "مرخص",
        "expiry_date": datetime.fromtimestamp(user["expiry"]).strftime("%Y-%m-%d"),
        "force_stop": user.get("force_stop", False),
        "enabled": user.get("enabled", True)
    }
    
    # لو الأدمن طالب إيقاف، رجعه مرة واحدة وامسحه
    if user.get("force_stop"):
        user["force_stop"] = False
        save_users(users)
    
    return jsonify(response)

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """العميل بيبعت نبضة كل 15 ثانية"""
    data = request.json
    hwid = data.get('hwid','').strip().upper()
    if not hwid:
        return jsonify({"ok": False}), 400
    
    users = load_users()
    if hwid not in users:
        return jsonify({"ok": False, "msg": "غير مسجل"}), 404
    
    user = users[hwid]
    
    # لو مقفول
    if not user.get("enabled", True):
        return jsonify({"ok": False, "action": "ban", "msg": "تم إيقافك"}), 403
    
    if time.time() > user.get("expiry", 0):
        return jsonify({"ok": False, "action": "expire", "msg": "انتهى الاشتراك"}), 403
    
    # تحديث الحالة
    user["last_seen"] = datetime.now().isoformat()
    user["is_online"] = True
    user["status"] = data.get('status', 'idle') # running, paused, idle
    user["stats"] = data.get('stats', user.get('stats', {}))
    user["ip"] = request.remote_addr
    
    # هل فيه أمر من الأدمن؟
    action = "none"
    if user.get("force_stop"):
        action = "stop"
        user["force_stop"] = False
    
    if user.get("force_pause"):
        action = "pause"
        user["force_pause"] = False
    
    if user.get("force_resume"):
        action = "resume"
        user["force_resume"] = False
    
    save_users(users)
    
    return jsonify({"ok": True, "action": action})

# ========== API للأدمن (لوحة التحكم) ==========

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    users = load_users()
    # حدد مين أونلاين (آخر نبضة من أقل من 2 دقيقة)
    now = datetime.now()
    result = []
    for hwid, u in users.items():
        try:
            last = datetime.fromisoformat(u.get('last_seen',''))
            diff = (now - last).total_seconds()
            u['is_online'] = diff < 120 # 2 دقيقة
            u['last_seen_ago'] = f"{int(diff//60)} دقيقة" if diff > 60 else f"{int(diff)} ثانية"
        except:
            u['is_online'] = False
            u['last_seen_ago'] = "غير معروف"
        result.append(u)
    
    # ترتيب: الأونلاين أولا
    result.sort(key=lambda x: (not x.get('is_online', False), x.get('last_seen','')), reverse=False)
    return jsonify(result)

@app.route('/api/admin/user/<hwid>/toggle', methods=['POST'])
def toggle_user(hwid):
    hwid = hwid.upper()
    users = load_users()
    if hwid not in users:
        return jsonify({"ok": False}), 404
    users[hwid]["enabled"] = not users[hwid].get("enabled", True)
    save_users(users)
    return jsonify({"ok": True, "enabled": users[hwid]["enabled"]})

@app.route('/api/admin/user/<hwid>/stop', methods=['POST'])
def stop_user(hwid):
    hwid = hwid.upper()
    users = load_users()
    if hwid not in users:
        return jsonify({"ok": False}), 404
    users[hwid]["force_stop"] = True
    save_users(users)
    return jsonify({"ok": True, "msg": f"تم إرسال أمر إيقاف لـ {hwid}"})

@app.route('/api/admin/user/<hwid>/pause', methods=['POST'])
def pause_user(hwid):
    hwid = hwid.upper()
    users = load_users()
    if hwid not in users:
        return jsonify({"ok": False}), 404
    users[hwid]["force_pause"] = True
    save_users(users)
    return jsonify({"ok": True})

@app.route('/api/admin/user/<hwid>/resume', methods=['POST'])
def resume_user(hwid):
    hwid = hwid.upper()
    users = load_users()
    if hwid not in users:
        return jsonify({"ok": False}), 404
    users[hwid]["force_resume"] = True
    save_users(users)
    return jsonify({"ok": True})

@app.route('/api/admin/user/<hwid>/extend', methods=['POST'])
def extend_user(hwid):
    hwid = hwid.upper()
    data = request.json
    days = int(data.get('days', 30))
    users = load_users()
    if hwid not in users:
        return jsonify({"ok": False}), 404
    
    current_exp = users[hwid].get("expiry", int(time.time()))
    if current_exp < time.time():
        current_exp = int(time.time())
    users[hwid]["expiry"] = current_exp + days*86400
    
    # ولد مفتاح جديد
    import base64
    exp = users[hwid]["expiry"]
    raw = f"{hwid}|{exp}|{SECRET_SALT}"
    sig = hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
    payload = f"{hwid}-{exp}-{sig}"
    license_key = base64.b64encode(payload.encode()).decode()
    
    save_users(users)
    return jsonify({"ok": True, "new_expiry": datetime.fromtimestamp(exp).strftime("%Y-%m-%d"), "license_key": license_key})

@app.route('/api/admin/user/<hwid>/delete', methods=['DELETE'])
def delete_user(hwid):
    hwid = hwid.upper()
    users = load_users()
    if hwid in users:
        del users[hwid]
        save_users(users)
    return jsonify({"ok": True})

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    users = load_users()
    total = len(users)
    now = datetime.now()
    online = 0
    running = 0
    for u in users.values():
        try:
            last = datetime.fromisoformat(u.get('last_seen',''))
            if (now - last).total_seconds() < 120:
                online += 1
                if u.get('status') == 'running':
                    running += 1
        except:
            pass
    return jsonify({"total": total, "online": online, "running": running, "offline": total-online})

# ========== صفحة الأدمن ==========
@app.route('/')
def index():
    return """
    <h2>MADO Server Running</h2>
    <p>API:</p>
    <ul>
        <li>GET /api/admin/users - قائمة العملاء</li>
        <li>GET /api/admin/stats - الإحصائيات</li>
        <li>POST /api/auth - تسجيل دخول العميل</li>
        <li>POST /api/heartbeat - نبضة العميل</li>
    </ul>
    <p>افتح لوحة التحكم من الملف admin.html</p>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("="*50)
    print(" MADO Online Server v1.0")
    print(f" شغال على: http://localhost:{port}")
    print("="*50)
    app.run(host='0.0.0.0', port=port, debug=False)
