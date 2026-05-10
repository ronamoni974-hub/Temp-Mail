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

# অ্যাডমিন ও ডেভেলপার সেপারেশন
ADMIN_ID = 123456789 # <--- যিনি বটটি চালাবেন (আপনার ক্লায়েন্ট) তার ID এখানে দিন
DEVELOPER_ID = 6670461311 # আপনার (Walid) সুপার-অ্যাডমিন ID
SUPPORT_LINK = "https://t.me/Ad_Walid" 

# --- Firebase সেটআপ ---
try:
    firebase_cert = json.loads(os.environ.get("FIREBASE_JSON", "{}"))
    database_url = os.environ.get("FIREBASE_DB_URL", "https://your-db.firebaseio.com")
    cred = credentials.Certificate(firebase_cert)
    firebase_admin.initialize_app(cred, {'databaseURL': database_url})
    print("Firebase Connected Successfully!")
except Exception as e:
    print("Firebase Setup Pending or Error:", e)

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

# --- Force Sub Check ---
def check_force_sub(user_id):
    try:
        channel = db.reference('settings/force_sub').get()
        if not channel: return True
        status = bot.get_chat_member(channel, user_id).status
        if status in ['member', 'administrator', 'creator']: return True
        return False
    except: return True 

# --- UI Menus ---
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("✨ Generate Premium Mail"), KeyboardButton("📥 Inbox"))
    markup.add(KeyboardButton("🎛️ Dashboard"), KeyboardButton("👤 Profile"))
    markup.add(KeyboardButton("🌐 Server"), KeyboardButton("🔐 2FA Authenticator"))
    markup.add(KeyboardButton("🎧 Support"))
    # অ্যাডমিন বা ডেভেলপার হলে প্যানেল শো করবে
    if user_id in [ADMIN_ID, DEVELOPER_ID]:
        markup.add(KeyboardButton("⚙️ Admin Panel"))
    return markup

def back_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔙 Back to Main Menu"))
    return markup

def admin_back_inline():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_home"))
    return markup

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    
    if user_data.get("banned"):
        bot.reply_to(message, "❌ আপনি এই বট থেকে ব্যানড হয়েছেন।")
        return
        
    db.reference(f'users/{user_id}/id').set(user_id) 
    
    if not check_force_sub(user_id):
        channel = db.reference('settings/force_sub').get()
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ Verify", callback_data="verify_sub"))
        bot.send_message(user_id, "⚠️ **বট ব্যবহার করতে আগে আমাদের চ্যানেলে জয়েন করুন!**\nজয়েন করার পর 'Verify' বাটনে ক্লিক করুন।", parse_mode="Markdown", reply_markup=markup)
        return

    increment_stat("total_users")
    bot.reply_to(message, "💎 *Premium Temp Mail & 2FA Bot*\n\nঅটোমেটিক ইনবক্স, প্রোফাইল, ড্যাশবোর্ড এবং মাল্টি-সার্ভার সিস্টেম চালু আছে।", parse_mode="Markdown", reply_markup=main_menu(user_id))

@bot.callback_query_handler(func=lambda call: call.data == "verify_sub")
def verify_sub_call(call):
    user_id = call.message.chat.id
    if check_force_sub(user_id):
        bot.delete_message(user_id, call.message.message_id)
        bot.send_message(user_id, "✅ **ভেরিফিকেশন সফল হয়েছে!**", parse_mode="Markdown", reply_markup=main_menu(user_id))
    else:
        bot.answer_callback_query(call.id, "❌ আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)

# --- Back Action ---
@bot.message_handler(func=lambda m: m.text == "🔙 Back to Main Menu" or m.text == "❌ Cancel")
def back_to_main(message):
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    bot.send_message(message.chat.id, "🔙 মেইন মেনুতে ফিরে এসেছেন।", reply_markup=main_menu(message.chat.id))

# --- Server Selection ---
@bot.message_handler(func=lambda m: m.text == "🌐 Server")
def server_menu(message):
    if not check_force_sub(message.chat.id): return start_message(message)
    user_id = message.chat.id
    current = get_user_data(user_id).get("server", "mail.gw")
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"{'✅' if current=='mail.gw' else ''} Mail.gw", callback_data="srv_mail.gw"),
               InlineKeyboardButton(f"{'✅' if current=='mail.td' else ''} Mail.td", callback_data="srv_mail.td"))
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
    if not check_force_sub(message.chat.id): return start_message(message)
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    total_generated = len(user_data.get("mails", {}))
    
    text = f"👤 **Your Profile**\n\n🆔 **User ID:** `{user_id}`\n🌐 **Server:** `{user_data.get('server', 'mail.gw')}`\n📧 **Total Generated:** `{total_generated}`\n🟢 **Active Mails:** `{total_generated}`"
    bot.send_message(user_id, text, parse_mode="Markdown")

# --- Support ---
@bot.message_handler(func=lambda m: m.text == "🎧 Support")
def support(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👨‍💻 Developer Walid", url=SUPPORT_LINK))
    bot.send_message(message.chat.id, "🎧 **Support Center**\n\nযেকোনো সমস্যার জন্য ডেভেলপারের সাথে যোগাযোগ করুন।", parse_mode="Markdown", reply_markup=markup)

# --- 2FA Authenticator ---
@bot.message_handler(func=lambda m: m.text == "🔐 2FA Authenticator")
def ask_2fa_secret(message):
    if not check_force_sub(message.chat.id): return start_message(message)
    msg = bot.send_message(message.chat.id, "🛡️ **আপনার 2FA Setup/Secret Key দিন:**", parse_mode="Markdown", reply_markup=back_markup())
    bot.register_next_step_handler(msg, generate_otp_code)

def generate_otp_code(message):
    if message.text == "🔙 Back to Main Menu" or message.text == "❌ Cancel":
        return back_to_main(message)
        
    secret = message.text.strip().replace(" ", "")
    try:
        totp = pyotp.TOTP(secret)
        otp_code = totp.now()
        text = f"✅ **2FA Authenticator Code:**\n\n👉 `{otp_code}` 👈\n*(কোডটি কপি করতে ক্লিক করুন)*"
        bot.reply_to(message, text, parse_mode="Markdown", reply_markup=main_menu(message.chat.id))
    except Exception:
        bot.reply_to(message, "❌ **ভুল Secret Key!**", reply_markup=main_menu(message.chat.id))

# --- Mail Generation ---
def get_api_headers(api_key=None):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/114.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    if api_key: headers['Authorization'] = f"Bearer {api_key}"
    return headers

@bot.message_handler(func=lambda m: m.text == "✨ Generate Premium Mail")
def generate_mail(message):
    user_id = message.chat.id
    if not check_force_sub(user_id): return start_message(message)
    
    user_data = get_user_data(user_id)
    if user_data.get("banned"): return
    
    server = user_data.get("server", "mail.gw")
    loading_msg = bot.send_message(user_id, "⏳ `[■■□□□□□□□□] 20%`\nConnecting to server...", parse_mode="Markdown")
    
    success = False
    # Mail.td এর জন্য ডেটাবেস থেকে API লিস্ট আনবে
    api_list = ["https://api.mail.gw"] if server == "mail.gw" else (db.reference('settings/mail_td_apis').get() or ["https://api.mail.td"])
    
    for api_base in api_list:
        try:
            bot.edit_message_text("⏳ `[■■■■■■□□□□] 60%`\nFetching Domain...", user_id, loading_msg.message_id, parse_mode="Markdown")
            headers = get_api_headers()
            
            domain_res = requests.get(f'{api_base}/domains', headers=headers).json()
            domain = domain_res['hydra:member'][0]['domain'] if 'hydra:member' in domain_res else domain_res[0]['domain']
            
            email = f"{generate_random_string()}@{domain}"
            password = generate_random_string(12)
            acc_data = {"address": email, "password": password}
            
            requests.post(f'{api_base}/accounts', json=acc_data, headers=headers)
            
            bot.edit_message_text("⏳ `[■■■■■■■■■□] 90%`\nActivating Live Inbox...", user_id, loading_msg.message_id, parse_mode="Markdown")
            token_res = requests.post(f'{api_base}/token', json=acc_data, headers=headers).json()
            token = token_res['token']
            
            mails = user_data.get("mails", {})
            mails[email.replace('.', ',')] = {"token": token, "server": server, "api_base": api_base}
            update_user_data(user_id, {"mails": mails, "active_mail": email})
            increment_stat("total_generated")
            
            bot.delete_message(user_id, loading_msg.message_id)
            msg = f"✨ **Premium Mail Generated!**\n\n👉 `{email}` 👈\n\n🟢 **Status:** Active & Listening..."
            bot.send_message(user_id, msg, parse_mode="Markdown")
            success = True
            break
        except Exception as e:
            continue
            
    if not success:
        bot.edit_message_text("❌ সব API ডাউন আছে! অ্যাডমিনকে আপডেট করতে বলুন।", user_id, loading_msg.message_id)

# --- Dashboard ---
@bot.message_handler(func=lambda m: m.text == "🎛️ Dashboard")
def dashboard(message):
    if not check_force_sub(message.chat.id): return start_message(message)
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
        bot.edit_message_text(f"✅ **Active Mail Switched:**\n👉 `{new_active}` 👈", user_id, call.message.message_id, parse_mode="Markdown")
    elif call.data == 'del_active':
        active = user_data.get("active_mail")
        mails = user_data.get("mails", {})
        if active and active.replace('.', ',') in mails:
            del mails[active.replace('.', ',')]
            new_active = list(mails.keys())[0].replace(',', '.') if mails else ""
            update_user_data(user_id, {"mails": mails, "active_mail": new_active})
            increment_stat("total_deleted")
            bot.edit_message_text("🗑️ **Active Mail Deleted!**", user_id, call.message.message_id, parse_mode="Markdown")

# --- ADMIN PANEL ---
def get_admin_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("👥 User Manage", callback_data="admin_usermanage"),
               InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"))
    markup.add(InlineKeyboardButton("📢 Force Sub Channel", callback_data="admin_fsub"),
               InlineKeyboardButton("🔗 Mail.td APIs", callback_data="admin_tdapis"))
    markup.add(InlineKeyboardButton("✉️ Broadcast Notice", callback_data="admin_notice"))
    return markup

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def admin_panel(message):
    if message.chat.id not in [ADMIN_ID, DEVELOPER_ID]: return
    bot.send_message(message.chat.id, "⚙️ **Admin Dashboard**", parse_mode="Markdown", reply_markup=get_admin_markup())

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_actions(call):
    if call.message.chat.id not in [ADMIN_ID, DEVELOPER_ID]: return
    action = call.data.split('_')[1]
    
    if action == "home":
        bot.edit_message_text("⚙️ **Admin Dashboard**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_admin_markup())
        bot.clear_step_handler_by_chat_id(call.message.chat.id)

    elif action == "stats":
        stats = get_stats()
        text = f"📊 **Bot Statistics**\n\n👥 Total Users: `{stats['total_users']}`\n📧 Total Generated: `{stats['total_generated']}`\n🗑️ Total Deleted: `{stats['total_deleted']}`"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=admin_back_inline())
        
    elif action == "fsub":
        channel = db.reference('settings/force_sub').get() or "Not Set"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Set Channel", callback_data="fsub_set"), InlineKeyboardButton("🗑️ Remove", callback_data="fsub_remove"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text(f"📢 **Force Sub Channel**\nCurrent: `{channel}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif action == "tdapis":
        apis = db.reference('settings/mail_td_apis').get() or ["https://api.mail.td"]
        text = "🔗 **Mail.td APIs (Fallback List):**\n" + "\n".join([f"• `{a}`" for a in apis])
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Add API", callback_data="tdapi_add"), InlineKeyboardButton("🗑️ Clear All", callback_data="tdapi_clear"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif action == "usermanage":
        msg = bot.send_message(call.message.chat.id, "👤 **User Manage**\nডিটেলস দেখতে ইউজারের ID দিন:", parse_mode="Markdown", reply_markup=back_markup())
        bot.register_next_step_handler(msg, process_user_manage)
        
    elif action == "notice":
        msg = bot.send_message(call.message.chat.id, "📢 **নোটিশ লিখুন:**", parse_mode="Markdown", reply_markup=back_markup())
        bot.register_next_step_handler(msg, send_broadcast)

# Admin Sub-Actions
@bot.callback_query_handler(func=lambda call: call.data.startswith('fsub_') or call.data.startswith('tdapi_') or call.data.startswith('ban_') or call.data.startswith('unban_'))
def admin_sub_actions(call):
    if call.message.chat.id not in [ADMIN_ID, DEVELOPER_ID]: return
    
    if call.data == "fsub_remove":
        db.reference('settings/force_sub').delete()
        bot.answer_callback_query(call.id, "Channel removed!")
        admin_actions(call)
        
    elif call.data == "fsub_set":
        msg = bot.send_message(call.message.chat.id, "চ্যানেলের ইউজারনেম দিন (যেমন: @MyChannel):", reply_markup=back_markup())
        bot.register_next_step_handler(msg, lambda m: db.reference('settings/force_sub').set(m.text) if m.text != "🔙 Back to Main Menu" else back_to_main(m))
        
    elif call.data == "tdapi_clear":
        db.reference('settings/mail_td_apis').set(["https://api.mail.td"])
        bot.answer_callback_query(call.id, "APIs Cleared!")
        admin_actions(call)
        
    elif call.data == "tdapi_add":
        msg = bot.send_message(call.message.chat.id, "নতুন Mail.td API Base URL দিন (যেমন: https://api.mail.td):", reply_markup=back_markup())
        def save_api(m):
            if m.text == "🔙 Back to Main Menu": return back_to_main(m)
            apis = db.reference('settings/mail_td_apis').get() or []
            apis.append(m.text)
            db.reference('settings/mail_td_apis').set(apis)
            bot.send_message(m.chat.id, "✅ Mail.td API Added!", reply_markup=main_menu(m.chat.id))
        bot.register_next_step_handler(msg, save_api)
        
    elif call.data.startswith('ban_'):
        uid = call.data.split('_')[1]
        db.reference(f'users/{uid}/banned').set(True)
        bot.answer_callback_query(call.id, "User Banned!")
        
    elif call.data.startswith('unban_'):
        uid = call.data.split('_')[1]
        db.reference(f'users/{uid}/banned').set(False)
        bot.answer_callback_query(call.id, "User Unbanned!")

def process_user_manage(message):
    if message.text == "🔙 Back to Main Menu": return back_to_main(message)
    target_id = message.text.strip()
    data = get_user_data(target_id)
    
    text = f"👤 **User Details:**\n🆔 ID: `{target_id}`\n🚫 Banned: `{data.get('banned', False)}`\n📧 Active Mails: `{len(data.get('mails', {}))}`"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{target_id}"), InlineKeyboardButton("✅ Unban", callback_data=f"unban_{target_id}"))
    markup.add(InlineKeyboardButton("🔙 Admin Home", callback_data="admin_home"))
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu(message.chat.id))
    bot.send_message(message.chat.id, "অ্যাকশন সিলেক্ট করুন:", reply_markup=markup)

def send_broadcast(message):
    if message.text == "🔙 Back to Main Menu": return back_to_main(message)
    users = db.reference('users').get() or {}
    sent = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 **Notice from Admin:**\n\n{message.text}", parse_mode="Markdown")
            sent += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ Notice sent to {sent} users.", reply_markup=main_menu(message.chat.id))

# --- Background Auto Checker ---
def fetch_mail_for_user(chat_id, user_data):
    active = user_data.get("active_mail")
    mails = user_data.get("mails", {})
    if not active or active.replace('.', ',') not in mails: return
    
    mail_info = mails[active.replace('.', ',')]
    token = mail_info.get("token")
    api_base = mail_info.get("api_base", "https://api.mail.gw" if mail_info.get("server") == "mail.gw" else "https://api.mail.td")
    
    headers = get_api_headers(token)
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
