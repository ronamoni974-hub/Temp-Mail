import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import requests
import random
import string
import os
import pyotp
import time
import re
import json
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask
from threading import Thread

# --- কনফিগারেশন ---
BOT_TOKEN = "8705131481:AAF8TnG9nx1U-BZz0nXYP_jxtSWNeSQPbYY"
bot = telebot.TeleBot(BOT_TOKEN)

# আপনার টেলিগ্রাম ইউজার আইডি এখানে দিন (Admin হিসেবে কাজ করার জন্য)
ADMIN_ID = 123456789 # <--- এটি পরিবর্তন করে আপনার ID দিন
SUPPORT_USERNAME = "@YourUsername" # <--- আপনার ইউজারনেম দিন

# --- Firebase সেটআপ ---
# Render Environment Variable থেকে Firebase Credentials নেবে
try:
    firebase_cert = json.loads(os.environ.get("FIREBASE_JSON", "{}"))
    database_url = os.environ.get("FIREBASE_DB_URL", "https://your-db.firebaseio.com")
    cred = credentials.Certificate(firebase_cert)
    firebase_admin.initialize_app(cred, {'databaseURL': database_url})
    db_ref = db.reference('/')
    print("Firebase Connected Successfully!")
except Exception as e:
    print("Firebase Setup Pending or Error:", e)

# API Headers
API_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/114.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

# --- Helper Functions ---
def generate_random_string(length=10):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def extract_otp(text):
    if not text: return None
    spaced = re.search(r'(?:[A-Za-z0-9]\s+){5,}[A-Za-z0-9]', text)
    if spaced: return spaced.group(0).replace(" ", "")
    digits = re.search(r'\b\d{4,8}\b', text)
    if digits: return digits.group(0)
    alnum = re.search(r'\b[A-Z0-9]{5,10}\b', text, re.IGNORECASE)
    if alnum: return alnum.group(0)
    return None

def clean_mail_body(text):
    text = re.sub(r'http[s]?://\S+', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = " ".join(text.split()).replace('*', '').replace('_', '').replace('`', '')
    return text[:100] + "..." if len(text) > 100 else text

# --- Database Helper Functions ---
def get_user_data(user_id):
    try:
        user = db.reference(f'users/{user_id}').get()
        return user if user else {"server": "mail.gw", "mails": {}, "active_mail": "", "banned": False}
    except: return {"server": "mail.gw", "mails": {}, "active_mail": "", "banned": False}

def update_user_data(user_id, data):
    try: db.reference(f'users/{user_id}').update(data)
    except: pass

def get_stats():
    try: return db.reference('stats').get() or {"total_users": 0, "total_generated": 0, "total_deleted": 0}
    except: return {"total_users": 0, "total_generated": 0, "total_deleted": 0}

def increment_stat(key):
    try:
        current = db.reference(f'stats/{key}').get() or 0
        db.reference(f'stats/{key}').set(current + 1)
    except: pass

# --- UI Menus ---
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("✨ Generate Premium Mail"), KeyboardButton("📥 Inbox"))
    markup.add(KeyboardButton("🎛️ Dashboard"), KeyboardButton("👤 Profile"))
    markup.add(KeyboardButton("🌐 Server"), KeyboardButton("🔐 2FA Authenticator"))
    markup.add(KeyboardButton("🎧 Support"))
    if user_id == ADMIN_ID:
        markup.add(KeyboardButton("⚙️ Admin Panel"))
    return markup

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    if user_data.get("banned"):
        bot.reply_to(message, "❌ আপনি এই বট থেকে ব্যানড হয়েছেন।")
        return
        
    db.reference(f'users/{user_id}/id').set(user_id) # Save user
    increment_stat("total_users")
    bot.reply_to(message, "💎 *Premium Temp Mail & 2FA Bot*\n\nঅটোমেটিক ইনবক্স, প্রোফাইল, ড্যাশবোর্ড এবং মাল্টি-সার্ভার সিস্টেম চালু আছে।", parse_mode="Markdown", reply_markup=main_menu(user_id))

# --- Server Selection ---
@bot.message_handler(func=lambda m: m.text == "🌐 Server")
def server_menu(message):
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    current = user_data.get("server", "mail.gw")
    
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton(f"{'✅' if current=='mail.gw' else ''} Mail.gw", callback_data="srv_mail.gw")
    btn2 = InlineKeyboardButton(f"{'✅' if current=='mail.td' else ''} Mail.td", callback_data="srv_mail.td")
    markup.add(btn1, btn2)
    bot.send_message(user_id, f"🌐 **Current Server:** `{current}`\n\nসার্ভার সিলেক্ট করুন:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('srv_'))
def change_server(call):
    new_server = call.data.split('_')[1]
    update_user_data(call.message.chat.id, {"server": new_server})
    bot.answer_callback_query(call.id, f"Server changed to {new_server}")
    bot.edit_message_text(f"✅ **Server Updated to:** `{new_server}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- Profile ---
@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def profile(message):
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    mails = user_data.get("mails", {})
    total_generated = len(mails)
    
    text = f"👤 **Your Profile**\n\n"
    text += f"🆔 **User ID:** `{user_id}`\n"
    text += f"🌐 **Server:** `{user_data.get('server', 'mail.gw')}`\n"
    text += f"📧 **Total Generated:** `{total_generated}`\n"
    text += f"🟢 **Active Mails:** `{total_generated}`\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

# --- Support ---
@bot.message_handler(func=lambda m: m.text == "🎧 Support")
def support(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💬 Contact Admin", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}"))
    text = f"🎧 **Support Center**\n\nযেকোনো সমস্যার জন্য অ্যাডমিনের সাথে যোগাযোগ করুন।\n\n👨‍💻 **Developer:** `{SUPPORT_USERNAME}`"
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# --- Mail Generation ---
@bot.message_handler(func=lambda m: m.text == "✨ Generate Premium Mail")
def generate_mail(message):
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    if user_data.get("banned"): return
    
    server = user_data.get("server", "mail.gw")
    api_base = "https://api.mail.gw" if server == "mail.gw" else "https://api.mail.tm"
    
    loading_msg = bot.send_message(user_id, "⏳ Generating mail...", parse_mode="Markdown")
    try:
        domain_res = requests.get(f'{api_base}/domains', headers=API_HEADERS).json()
        domain = domain_res['hydra:member'][0]['domain'] if 'hydra:member' in domain_res else domain_res[0]['domain']
        
        email = f"{generate_random_string()}@{domain}"
        password = generate_random_string(12)
        acc_data = {"address": email, "password": password}
        
        requests.post(f'{api_base}/accounts', json=acc_data, headers=API_HEADERS)
        token_res = requests.post(f'{api_base}/token', json=acc_data, headers=API_HEADERS).json()
        token = token_res['token']
        
        # Save to Firebase
        mails = user_data.get("mails", {})
        mails[email.replace('.', ',')] = {"token": token, "server": server}
        update_user_data(user_id, {"mails": mails, "active_mail": email})
        increment_stat("total_generated")
        
        bot.delete_message(user_id, loading_msg.message_id)
        msg = f"✨ **Premium Mail Generated!**\n\n👉 `{email}` 👈\n\n🟢 **Status:** Active & Listening..."
        bot.send_message(user_id, msg, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text("❌ Server Error!", user_id, loading_msg.message_id)

# --- Dashboard (Multi-Mail Management) ---
@bot.message_handler(func=lambda m: m.text == "🎛️ Dashboard")
def dashboard(message):
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    mails = user_data.get("mails", {})
    active = user_data.get("active_mail", "")
    
    if not mails:
        bot.send_message(user_id, "⚠️ আপনার কোনো ইমেইল নেই!")
        return
        
    markup = InlineKeyboardMarkup(row_width=1)
    for mail_key in mails:
        real_mail = mail_key.replace(',', '.')
        btn_text = f"🟢 {real_mail}" if real_mail == active else f"⚪ {real_mail}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"switch_{real_mail}"))
        
    markup.add(InlineKeyboardButton("🗑️ Delete Active Mail", callback_data="del_active"))
    bot.send_message(user_id, "🎛️ **Mail Dashboard**\nক্লিক করে মেইল সুইচ করুন:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('switch_') or call.data == 'del_active')
def dash_actions(call):
    user_id = call.message.chat.id
    user_data = get_user_data(user_id)
    
    if call.data.startswith('switch_'):
        new_active = call.data.split('_')[1]
        update_user_data(user_id, {"active_mail": new_active})
        bot.answer_callback_query(call.id, f"Switched to {new_active}")
        bot.edit_message_text(f"✅ **Active Mail Switched:**\n👉 `{new_active}` 👈", user_id, call.message.message_id, parse_mode="Markdown")
        
    elif call.data == 'del_active':
        active = user_data.get("active_mail")
        mails = user_data.get("mails", {})
        if active and active.replace('.', ',') in mails:
            del mails[active.replace('.', ',')]
            new_active = list(mails.keys())[0].replace(',', '.') if mails else ""
            update_user_data(user_id, {"mails": mails, "active_mail": new_active})
            increment_stat("total_deleted")
            bot.answer_callback_query(call.id, "Mail Deleted!")
            bot.edit_message_text("🗑️ **Active Mail Deleted!**", user_id, call.message.message_id, parse_mode="Markdown")

# --- Admin Panel ---
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel" and m.chat.id == ADMIN_ID)
def admin_panel(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("👥 User List", callback_data="admin_users"),
               InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"))
    markup.add(InlineKeyboardButton("📢 Notice", callback_data="admin_notice"),
               InlineKeyboardButton("🚫 Ban/Unban", callback_data="admin_ban"))
    bot.send_message(message.chat.id, "⚙️ **Admin Dashboard**", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_actions(call):
    if call.message.chat.id != ADMIN_ID: return
    action = call.data.split('_')[1]
    
    if action == "stats":
        stats = get_stats()
        text = f"📊 **Bot Statistics**\n\n👥 Total Users: `{stats['total_users']}`\n📧 Total Generated: `{stats['total_generated']}`\n🗑️ Total Deleted: `{stats['total_deleted']}`"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
    elif action == "users":
        try:
            users = db.reference('users').get() or {}
            with open("users.txt", "w") as f:
                for uid in users: f.write(f"{uid}\n")
            with open("users.txt", "rb") as f:
                bot.send_document(call.message.chat.id, f, caption="👥 User List")
        except: bot.answer_callback_query(call.id, "Error fetching users")
        
    elif action == "notice":
        msg = bot.send_message(call.message.chat.id, "📢 **নোটিশ লিখুন:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    users = db.reference('users').get() or {}
    sent = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 **Notice from Admin:**\n\n{message.text}", parse_mode="Markdown")
            sent += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ Notice sent to {sent} users.")

# --- Background Auto Checker ---
def fetch_mail_for_user(chat_id, user_data):
    active = user_data.get("active_mail")
    mails = user_data.get("mails", {})
    if not active or active.replace('.', ',') not in mails: return
    
    mail_info = mails[active.replace('.', ',')]
    token = mail_info.get("token")
    server = mail_info.get("server", "mail.gw")
    api_base = "https://api.mail.gw" if server == "mail.gw" else "https://api.mail.tm"
    
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        res = requests.get(f'{api_base}/messages', headers=headers).json()
        messages = res if isinstance(res, list) else res.get('hydra:member', [])
        seen_key = f"users/{chat_id}/mails/{active.replace('.', ',')}/seen"
        seen_msgs = db.reference(seen_key).get() or []
        
        for msg in messages:
            msg_id = msg['id']
            if msg_id not in seen_msgs:
                seen_msgs.append(msg_id)
                db.reference(seen_key).set(seen_msgs)
                
                full_msg = requests.get(f'{api_base}/messages/{msg_id}', headers=headers).json()
                text = full_msg.get('text', '') or full_msg.get('intro', '')
                subj = msg.get('subject', 'No Subject')
                sender = msg['from'].get('address', 'Unknown') if isinstance(msg.get('from'), dict) else msg.get('from', 'Unknown')
                
                otp = extract_otp(subj + " " + text)
                clean_txt = clean_mail_body(text)
                
                notification = f"🔔 **NEW MAIL RECEIVED!**\n\n👤 **From:** `{sender}`\n📌 **Subject:** {subj}\n\n"
                if otp: notification += f"🔑 **OTP / Code:**\n👉 `{otp}` 👈\n\n"
                notification += f"📄 **Message:**\n_{clean_txt}_"
                
                bot.send_message(chat_id, notification, parse_mode="Markdown")
    except: pass

def auto_check_inbox():
    while True:
        try:
            users = db.reference('users').get() or {}
            for chat_id, data in users.items():
                fetch_mail_for_user(chat_id, data)
        except: pass
        time.sleep(10)

# --- Flask & Run ---
app = Flask(__name__)
@app.route('/')
def index(): return "SaaS Premium Bot is Running!"

def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    Thread(target=auto_check_inbox, daemon=True).start()
    bot.polling(none_stop=True)
