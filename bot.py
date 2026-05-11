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
import html
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask
from threading import Thread
from mailtd import MailTD

# --- কনফিগারেশন ---
BOT_TOKEN = "8705131481:AAF8TnG9nx1U-BZz0nXYP_jxtSWNeSQPbYY"
bot = telebot.TeleBot(BOT_TOKEN)

# অ্যাডমিন ও ডেভেলপার সেপারেশন
ADMIN_ID = 5854417621 # <--- যিনি বট চালাবেন (আপনার ক্লায়েন্ট) তার ID
ADMIN_USERNAME = "CEO_HRIDOY" # <--- ক্লায়েন্টের ইউজারনেম (বিনা @ তে)
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
def get_api_headers(token=None):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    if token: headers['Authorization'] = f'Bearer {token}'
    return headers

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
    if not text: return "No content"
    text = str(text)
    # অপ্রয়োজনীয় লিংক [http...] বা রেগুলার লিংক রিমুভ করা
    text = re.sub(r'\[http[^\]]+\]', '', text)
    text = re.sub(r'http[s]?://\S+', '', text)
    
    text = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = " ".join(text.split()).replace('*', '').replace('_', '').replace('`', '')
    return text[:150] + "..." if len(text) > 150 else text

def get_user_data(user_id):
    try:
        user = db.reference(f'users/{user_id}').get()
        if isinstance(user, dict): return user
    except: pass
    return {"server": "mail.td", "mails": {}, "active_mail": "", "banned": False}

def update_user_data(user_id, data):
    try: db.reference(f'users/{user_id}').update(data)
    except: pass

def increment_stat(key):
    try:
        current = db.reference(f'stats/{key}').get() or 0
        db.reference(f'stats/{key}').set(current + 1)
    except: pass

def get_stats():
    try:
        data = db.reference('stats').get()
        if isinstance(data, dict): return data
    except: pass
    return {
        "total_users": 0, 
        "total_generated": 0, 
        "total_deleted": 0,
        "total_generated_mail_td": 0,
        "total_generated_mail_gw": 0
    }

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
    markup.add(KeyboardButton("✉️ Generate primium Mail"), KeyboardButton("📥 Inbox"))
    markup.add(KeyboardButton("🎛️ Dashboard"), KeyboardButton("👤 Profile"))
    markup.add(KeyboardButton("🌐 Server"), KeyboardButton("🔐 2FA Authenticator"))
    markup.add(KeyboardButton("🎧 Support"))
    if user_id in [ADMIN_ID, DEVELOPER_ID]:
        markup.add(KeyboardButton("⚙️ Admin Panel"))
    return markup

def back_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔙 Back to Main Menu"), KeyboardButton("❌ Cancel"))
    return markup

def admin_back_inline():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_home"))
    return markup

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start_message(message):
    try:
        user_id = message.chat.id
        user_data = get_user_data(user_id)
        
        if user_data.get("banned"):
            bot.reply_to(message, "❌ **Account Banned!**\nআপনি এই বটটি আর ব্যবহার করতে পারবেন গ্যা।", parse_mode="Markdown")
            return
            
        # Save User Info for TXT List
        name = message.from_user.first_name or "Unknown"
        username = message.from_user.username or "N/A"
        db.reference(f'users/{user_id}/id').set(user_id) 
        db.reference(f'users/{user_id}/name').set(name) 
        db.reference(f'users/{user_id}/username').set(username) 
        
        if not check_force_sub(user_id):
            channel = db.reference('settings/force_sub').get()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 Join Our Channel", url=f"https://t.me/{channel.replace('@', '')}"))
            markup.add(InlineKeyboardButton("✅ Verify", callback_data="verify_sub"))
            bot.send_message(user_id, "⚠️ **সার্ভিসটি ব্যবহার করতে আমাদের চ্যানেলে যুক্ত হোন!**\nচ্যানেলে যুক্ত হওয়ার পর 'Verify' বাটনে ক্লিক করুন।", parse_mode="Markdown", reply_markup=markup)
            return

        increment_stat("total_users")
        
        welcome_text = "🎉 **Welcome to Temp Mail Bot!** 🎉\n\n"
        welcome_text += "সোশ্যাল মিডিয়া বা যেকোনো অ্যাকাউন্ট খোলার জন্য হাই-কোয়ালিটি এবং সিকিউর মেইল জেনারেট করুন এক ক্লিকে।\n\n"
        welcome_text += "🔹 **Fast Live Inbox & OTP Scanner**\n"
        welcome_text += "🔹 **Mail.td Integration**\n"
        welcome_text += "🔹 **Secure 2FA Authenticator**\n\n"
        welcome_text += "👇 *নিচের মেনু থেকে আপনার প্রয়োজনীয় সার্ভিসটি বেছে নিন:*"
        
        bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=main_menu(user_id))
    except Exception as e:
        print(f"Start Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "verify_sub")
def verify_sub_call(call):
    user_id = call.message.chat.id
    if check_force_sub(user_id):
        bot.delete_message(user_id, call.message.message_id)
        bot.send_message(user_id, "✅ **ভেরিফিকেশন সফল হয়েছে!**", parse_mode="Markdown", reply_markup=main_menu(user_id))
    else:
        bot.answer_callback_query(call.id, "❌ আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)

@bot.message_handler(func=lambda m: m.text in ["🔙 Back to Main Menu", "❌ Cancel"])
def back_to_main(message):
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    bot.send_message(message.chat.id, "🔙 **মেইন মেনুতে ফিরে এসেছেন।**", parse_mode="Markdown", reply_markup=main_menu(message.chat.id))

# --- Server Selection ---
@bot.message_handler(func=lambda m: m.text == "🌐 Server")
def server_menu(message):
    if not check_force_sub(message.chat.id): return start_message(message)
    user_id = message.chat.id
    current = get_user_data(user_id).get("server", "mail.td")
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"{'✅' if current=='mail.td' else '🌐'} Server Mail.td", callback_data="srv_mail.td"),
        InlineKeyboardButton(f"{'✅' if current=='mail.gw' else '🌐'} Server Mail.gw", callback_data="srv_mail.gw")
    )
    bot.send_message(user_id, f"🌐 **Current Active Server:** `{current}`\n\nযেকোনো সোশ্যাল মিডিয়া অ্যাকাউন্ট খুলতে হাই-কোয়ালিটি সার্ভার বেছে নিন:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('srv_'))
def change_server(call):
    new_server = call.data.split('_')[1]
    update_user_data(call.message.chat.id, {"server": new_server})
    bot.answer_callback_query(call.id, f"Server switched to {new_server}")
    bot.edit_message_text(f"✅ **Server Updated Successfully to:** `{new_server}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- Profile & Support ---
@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def profile(message):
    if not check_force_sub(message.chat.id): return start_message(message)
    user_id = message.chat.id
    user_data = get_user_data(user_id)
    total_generated = len(user_data.get("mails", {})) if isinstance(user_data.get("mails"), dict) else 0
    name = user_data.get("name", "User")
    
    text = f"👤 **User Profile**\n\n"
    text += f"📛 **Name:** {name}\n"
    text += f"🆔 **Account ID:** `{user_id}`\n"
    text += f"🌐 **Default Server:** `{user_data.get('server', 'mail.td')}`\n"
    text += f"📧 **Total Generated:** `{total_generated}` Mails\n"
    text += f"🟢 **Active Mails:** `{total_generated}`"
    bot.send_message(user_id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎧 Support")
def support(message):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("👨‍💻 Developer Walid", url=SUPPORT_LINK))
    markup.add(InlineKeyboardButton("💬 Contact Bot Admin Hridoy", url=f"https://t.me/{ADMIN_USERNAME}"))
    bot.send_message(message.chat.id, "🎧 **Support Center**\n\nবটের যেকোনো সমস্যার জন্য অ্যাডমিন CEO-HRIDOY ভাইয়ের সাথে যোগাযোগ করুন। টেকনিক্যাল সাপোর্টের জন্য ডেভেলপারের সাথে যোগাযোগ করতে পারেন।", parse_mode="Markdown", reply_markup=markup)

# ==========================================
# --- 2FA Authenticator (UPDATED SECTION) ---
# ==========================================

def get_2fa_inline_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Code again", callback_data="refresh_2fa"))
    return markup

def get_2fa_reply_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🆕 New"), KeyboardButton("❌ Cancel"))
    return markup

def show_active_2fa(chat_id, secret, edit_msg_id=None):
    try:
        totp = pyotp.TOTP(secret)
        otp_code = totp.now()
        
        text = f"🔐 **Your account OTP:**\n\n`{otp_code}`\n\n*(কোডটি কপি করতে ক্লিক করুন)*"
        
        if edit_msg_id:
            bot.edit_message_text(text, chat_id, edit_msg_id, parse_mode="Markdown", reply_markup=get_2fa_inline_markup())
        else:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_2fa_inline_markup())
            bot.send_message(chat_id, "নিচের মেনু থেকে অপশন নির্বাচন করুন:", reply_markup=get_2fa_reply_markup())
    except Exception:
        bot.send_message(chat_id, "❌ **ভুল Secret Key বা কোড জেনারেট করতে সমস্যা হয়েছে!**", reply_markup=main_menu(chat_id))
        db.reference(f'users/{chat_id}/2fa_secret').delete()

@bot.message_handler(func=lambda m: m.text == "🔐 2FA Authenticator")
def ask_2fa_secret(message):
    if not check_force_sub(message.chat.id): return start_message(message)
    user_data = get_user_data(message.chat.id)
    active_secret = user_data.get("2fa_secret")
    
    if active_secret:
        # যদি আগে থেকেই সিক্রেট সেভ থাকে, সরাসরি OTP দেখাবে
        show_active_2fa(message.chat.id, active_secret)
    else:
        # নতুন হলে সিক্রেট কোড চাইবে
        msg = bot.send_message(message.chat.id, "🛡️ **আপনার 2FA Setup/Secret Key দিন:**\n*(ক্যান্সেল করতে নিচে ❌ বাটনে ক্লিক করুন)*", parse_mode="Markdown", reply_markup=back_markup())
        bot.register_next_step_handler(msg, process_new_2fa_secret)

def process_new_2fa_secret(message):
    if message.text in ["🔙 Back to Main Menu", "❌ Cancel"]: return back_to_main(message)
    secret = message.text.strip().replace(" ", "")
    
    try:
        # চেক করে দেখছি কোড ঠিক আছে কিনা
        totp = pyotp.TOTP(secret)
        totp.now() 
        
        # ডাটাবেসে সেভ করা হচ্ছে যেন ব্যাক করলেও থাকে
        update_user_data(message.chat.id, {"2fa_secret": secret})
        show_active_2fa(message.chat.id, secret)
        
    except Exception:
        msg = bot.reply_to(message, "❌ **ভুল Secret Key!** দয়া করে সঠিক Key দিন:", reply_markup=back_markup())
        bot.register_next_step_handler(msg, process_new_2fa_secret)

@bot.callback_query_handler(func=lambda call: call.data == "refresh_2fa")
def refresh_2fa_callback(call):
    user_data = get_user_data(call.message.chat.id)
    secret = user_data.get("2fa_secret")
    if secret:
        show_active_2fa(call.message.chat.id, secret, edit_msg_id=call.message.message_id)
        bot.answer_callback_query(call.id, "✅ Code Updated!")
    else:
        bot.answer_callback_query(call.id, "❌ No active secret found! Please setup again.", show_alert=True)

@bot.message_handler(func=lambda m: m.text == "🆕 New")
def new_2fa_secret_handler(message):
    # ডাটাবেস থেকে পুরনো কোড মুছে নতুন করে চাইবে
    db.reference(f'users/{message.chat.id}/2fa_secret').delete()
    msg = bot.send_message(message.chat.id, "🛡️ **নতুন 2FA Setup/Secret Key দিন:**\n*(ক্যান্সেল করতে নিচে ❌ বাটনে ক্লিক করুন)*", parse_mode="Markdown", reply_markup=back_markup())
    bot.register_next_step_handler(msg, process_new_2fa_secret)


# --- Notification Builder ---
def build_and_send_notification(chat_id, sender, subj, text, html_content=""):
    try:
        otp = extract_otp(subj + " " + text + " " + str(html_content))
        content_to_clean = text if (text and len(text) > 15) else html_content
        if not content_to_clean: content_to_clean = text
        clean_txt = clean_mail_body(content_to_clean)
        
        main_notification = f"🔔 **NEW MAIL RECEIVED!**\n\n👤 **From:** `{sender}`\n📌 **Subject:** `{subj}`\n"
        
        if otp:
            # OTP কোডটি লাইনের সাথেই বসবে
            main_notification += f"\nYour Verification Code : `{otp}`\n\n"
            
        main_notification += f"📄 **Message:**\n_{clean_txt}_"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Refresh Inbox", callback_data="refresh_inbox"))
        
        bot.send_message(chat_id, main_notification, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(f"Notification Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'close_msg')
def close_msg_callback(call):
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data == 'refresh_inbox')
def refresh_inbox_callback(call):
    bot.answer_callback_query(call.id, "🔄 Checking for new mails...")
    check_inbox(call.message)

# --- Mail Generation ---
@bot.message_handler(func=lambda m: m.text == "✉️ Generate primium Mail")
def generate_mail(message):
    user_id = message.chat.id
    if not check_force_sub(user_id): return start_message(message)
    
    user_data = get_user_data(user_id)
    if user_data.get("banned"): return
    
    server = user_data.get("server", "mail.td")
    loading_msg = bot.send_message(user_id, "⏳ `[■■□□□□□□□□] 20%`\nConnecting to Secure API...", parse_mode="Markdown")
    
    success = False
    error_log = ""
    
    if server == "mail.td":
        keys = db.reference('settings/mail_td_keys').get() or []
        if not keys:
            bot.edit_message_text("❌ **কোনো mail পাওয়া যায়নি!**\nঅ্যাডমিন এর সাথে যোগাযোগ করুন।", user_id, loading_msg.message_id, parse_mode="Markdown")
            return
            
        for key in keys:
            try:
                bot.edit_message_text("⏳ `[■■■■■■□□□□] 60%`\nFetching Domain (Mail.td)...", user_id, loading_msg.message_id, parse_mode="Markdown")
                client = MailTD(key)
                domains = client.accounts.list_domains()
                domain = domains[0].domain if hasattr(domains[0], 'domain') else domains[0]
                
                email = f"{generate_random_string()}@{domain}"
                password = generate_random_string(12)
                account = client.accounts.create(email, password=password)
                
                bot.edit_message_text("⏳ `[■■■■■■■■■□] 90%`\nActivating Live Sync Inbox...", user_id, loading_msg.message_id, parse_mode="Markdown")
                
                mails = user_data.get("mails", {})
                if not isinstance(mails, dict): mails = {}
                mails[email.replace('.', ',')] = {"token": key, "account_id": account.id, "server": "mail.td"}
                update_user_data(user_id, {"mails": mails, "active_mail": email})
                
                # Update Stats
                increment_stat("total_generated")
                increment_stat("total_generated_mail_td")
                
                bot.delete_message(user_id, loading_msg.message_id)
                msg = f"🎉 **Mail Generated!**\n\n📧 **Your Address:**\n👉 `{email}` 👈\n\n🛰️ **Server:** `{server}` API\n🟢 **Status:** Live Sync Active\n_• Listening for incoming mails..._"
                bot.send_message(user_id, msg, parse_mode="Markdown")
                success = True
                break
            except Exception as e:
                error_log += f"\n• Key {key[:5]}... : {str(e)[:40]}"
                continue
    else: 
        try:
            bot.edit_message_text("⏳ `[■■■■■■□□□□] 60%`\nFetching Default Domain (Mail.gw)...", user_id, loading_msg.message_id, parse_mode="Markdown")
            headers = get_api_headers()
            domain_res = requests.get('https://api.mail.gw/domains', headers=headers, timeout=10).json()
            domain = domain_res['hydra:member'][0]['domain'] if 'hydra:member' in domain_res else domain_res[0]['domain']
            
            email = f"{generate_random_string()}@{domain}"
            password = generate_random_string(12)
            acc_data = {"address": email, "password": password}
            
            requests.post('https://api.mail.gw/accounts', json=acc_data, headers=headers, timeout=10)
            
            bot.edit_message_text("⏳ `[■■■■■■■■■□] 90%`\nActivating Live Sync Inbox...", user_id, loading_msg.message_id, parse_mode="Markdown")
            token_res = requests.post('https://api.mail.gw/token', json=acc_data, headers=headers, timeout=10).json()
            
            mails = user_data.get("mails", {})
            if not isinstance(mails, dict): mails = {}
            mails[email.replace('.', ',')] = {"token": token_res['token'], "server": "mail.gw"}
            update_user_data(user_id, {"mails": mails, "active_mail": email})
            
            # Update Stats
            increment_stat("total_generated")
            increment_stat("total_generated_mail_gw")
            
            bot.delete_message(user_id, loading_msg.message_id)
            msg = f"🎉 **Mail Generated!**\n\n📧 **Your Address:**\n👉 `{email}` 👈\n\n🛰️ **Server:** `{server}` API\n🟢 **Status:** Live Sync Active\n_• Listening for incoming mails..._"
            bot.send_message(user_id, msg, parse_mode="Markdown")
            success = True
        except Exception as e:
            error_log += f"\n• Mail.gw Error: {str(e)[:40]}"

    if not success:
        err_msg = f"❌ **সার্ভার সাময়িক ডাউন আছে!**\n\n🔍 **Error Log:**`{error_log}`\n\nদয়া করে অন্য সার্ভার ট্রাই করুন অথবা অ্যাডমিনকে জানান।"
        bot.edit_message_text(err_msg, user_id, loading_msg.message_id, parse_mode="Markdown")

# --- Manual Inbox ---
@bot.message_handler(func=lambda m: m.text == "📥 Inbox")
def check_inbox(message):
    user_id = message.chat.id
    if not check_force_sub(user_id): return start_message(message)
    
    user_data = get_user_data(user_id)
    active = user_data.get("active_mail")
    mails = user_data.get("mails", {})
    
    if not active or active.replace('.', ',') not in mails:
        bot.send_message(user_id, "⚠️ **আপনার কোনো অ্যাক্টিভ ইমেইল নেই!**\nআগে '✉️ Generate primium Mail' এ ক্লিক করুন।", parse_mode="Markdown")
        return

    loading_msg = bot.send_message(user_id, "🔄 **Scanning Live Inbox...**\n_Checking for latest OTPs..._", parse_mode="Markdown")
    
    mail_info = mails[active.replace('.', ',')]
    server = mail_info.get("server", "mail.gw")
    seen_key = f"users/{user_id}/mails/{active.replace('.', ',')}/seen"
    seen_msgs = db.reference(seen_key).get() or []
    new_mail_found = False
    
    try:
        if server == "mail.td":
            client = MailTD(mail_info.get("token"))
            account_id = mail_info.get("account_id")
            messages, _ = client.messages.list(account_id)
            
            for msg_preview in messages:
                msg_id = msg_preview.id
                if msg_id not in seen_msgs:
                    seen_msgs.append(msg_id)
                    db.reference(seen_key).set(seen_msgs)
                    new_mail_found = True
                    
                    full_msg = client.messages.get(account_id, msg_id)
                    subj = getattr(full_msg, 'subject', 'No Subject')
                    sender = getattr(full_msg, 'from_address', getattr(full_msg, 'sender', 'Unknown'))
                    text = getattr(full_msg, 'text_body', '')
                    html_body = getattr(full_msg, 'html_body', '')
                    build_and_send_notification(user_id, sender, subj, text, html_body)
                    
        else: # mail.gw
            headers = get_api_headers(mail_info.get("token"))
            res = requests.get('https://api.mail.gw/messages', headers=headers, timeout=10).json()
            messages = res if isinstance(res, list) else res.get('hydra:member', [])
            
            for msg in messages:
                msg_id = msg['id']
                if msg_id not in seen_msgs:
                    seen_msgs.append(msg_id)
                    db.reference(seen_key).set(seen_msgs)
                    new_mail_found = True
                    
                    full_msg = requests.get(f'https://api.mail.gw/messages/{msg_id}', headers=headers).json()
                    subj = msg.get('subject', 'No Subject')
                    sender = msg['from'].get('address', 'Unknown') if isinstance(msg.get('from'), dict) else msg.get('from', 'Unknown')
                    text = full_msg.get('text', '') or full_msg.get('intro', '')
                    html_body = full_msg.get('html', '') or full_msg.get('htmlBody', '')
                    build_and_send_notification(user_id, sender, subj, text, html_body)
                    
        if not new_mail_found:
            bot.edit_message_text("📭 **কোনো নতুন মেইল বা OTP আসেনি!**\n\n_দয়া করে ওয়েবসাইট থেকে কোডটি আবার Resend করুন অথবা কিছুক্ষণ অপেক্ষা করুন।_", user_id, loading_msg.message_id, parse_mode="Markdown")
        else:
            bot.delete_message(user_id, loading_msg.message_id)
            
    except Exception as e:
        bot.edit_message_text(f"❌ **Network Error!**\nDetails: `{str(e)[:50]}`", user_id, loading_msg.message_id, parse_mode="Markdown")

# --- Dashboard ---
@bot.message_handler(func=lambda m: m.text == "🎛️ Dashboard")
def dashboard(message):
    try:
        if not check_force_sub(message.chat.id): return start_message(message)
        user_id = message.chat.id
        user_data = get_user_data(user_id)
        mails = user_data.get("mails", {})
        active = user_data.get("active_mail", "")
        
        if not mails or not isinstance(mails, dict):
            bot.send_message(user_id, "⚠️ আপনার কোনো ইমেইল নেই!")
            return
            
        markup = InlineKeyboardMarkup(row_width=1)
        for mail_key in mails:
            real_mail = mail_key.replace(',', '.')
            btn_text = f"🟢 {real_mail}" if real_mail == active else f"⚪ {real_mail}"
            markup.add(InlineKeyboardButton(btn_text, callback_data=f"switch_{real_mail}"))
        markup.add(InlineKeyboardButton("🗑️ Delete Active Mail", callback_data="del_active"))
        bot.send_message(user_id, "🎛️ **Mail Dashboard**\nক্লিক করে মেইল সুইচ করুন:", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Error loading dashboard.")

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
               InlineKeyboardButton("📝 User List (TXT)", callback_data="admin_usertxt"))
    markup.add(InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
               InlineKeyboardButton("📢 Force Sub Channel", callback_data="admin_fsub"))
    markup.add(InlineKeyboardButton("🔑 Manage API Keys", callback_data="admin_tdkeys"),
               InlineKeyboardButton("✉️ Broadcast", callback_data="admin_notice"))
    return markup

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def admin_panel(message):
    if message.chat.id not in [ADMIN_ID, DEVELOPER_ID]: return
    bot.send_message(message.chat.id, "⚙️ **Admin Dashboard**", parse_mode="Markdown", reply_markup=get_admin_markup())

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_actions(call):
    if call.message.chat.id not in [ADMIN_ID, DEVELOPER_ID]: return
    action = call.data.split('_')[1]
    
    try:
        if action == "home":
            bot.edit_message_text("⚙️ **Admin Dashboard**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_admin_markup())
            bot.clear_step_handler_by_chat_id(call.message.chat.id)

        elif action == "stats":
            stats = get_stats()
            # Fetch actual user count from db to ensure accurate stats
            users = db.reference('users').get() or {}
            tu = len(users)
            tg = stats.get('total_generated', 0)
            td = stats.get('total_deleted', 0)
            tg_td = stats.get('total_generated_mail_td', 0)
            tg_gw = stats.get('total_generated_mail_gw', 0)
            
            text = f"📊 **Bot Statistics**\n\n👥 Total Users: `{tu}`\n📧 Total Generated: `{tg}`\n🗑️ Total Deleted: `{td}`\n\n🌐 **Server Stats:**\n🔹 Mail.td Generated: `{tg_td}`\n🔹 Mail.gw Generated: `{tg_gw}`"
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=admin_back_inline())
            
        elif action == "usertxt":
            bot.send_message(call.message.chat.id, "⏳ Generating User List...")
            users = db.reference('users').get() or {}
            txt_content = "=== BOT USER DATABASE ===\n\n"
            count = 0
            for uid, data in users.items():
                if not isinstance(data, dict): continue
                m_count = len(data.get('mails', {})) if isinstance(data.get('mails'), dict) else 0
                banned = "YES" if data.get('banned') else "NO"
                name = data.get('name', 'Unknown')
                uname = data.get('username', 'N/A')
                txt_content += f"ID: {uid} | Name: {name} | Username: @{uname} | Mails: {m_count} | Banned: {banned}\n"
                count += 1
                
            txt_content = f"Total Users: {count}\n" + txt_content
            with open("user_details.txt", "w", encoding="utf-8") as f:
                f.write(txt_content)
            with open("user_details.txt", "rb") as f:
                bot.send_document(call.message.chat.id, f, caption=f"📝 **Full User Details List ({count} Users)**", parse_mode="Markdown")

        elif action == "fsub":
            channel = db.reference('settings/force_sub').get() or "Not Set"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("➕ Set Channel", callback_data="fsub_set"), InlineKeyboardButton("🗑️ Remove", callback_data="fsub_remove"))
            markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
            bot.edit_message_text(f"📢 **Force Sub Channel**\nCurrent: `{channel}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

        elif action == "tdkeys":
            keys = db.reference('settings/mail_td_keys').get() or []
            text = "🔑 **Mail.td API Keys Management:**\n_(Delete one by one)_"
            markup = InlineKeyboardMarkup(row_width=1)
            for i, key in enumerate(keys):
                short_key = key[:10] + "..." if len(key)>10 else key
                markup.add(InlineKeyboardButton(f"🗑️ Delete: {short_key}", callback_data=f"delkey_{i}"))
            markup.add(InlineKeyboardButton("➕ Add New API Key", callback_data="tdkey_add"))
            markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

        elif action == "usermanage":
            msg = bot.send_message(call.message.chat.id, "👤 **User Manage**\nডিটেলস দেখতে ইউজারের ID দিন:", parse_mode="Markdown", reply_markup=back_markup())
            bot.register_next_step_handler(msg, process_user_manage)
            
        elif action == "notice":
            msg = bot.send_message(call.message.chat.id, "📢 **নোটিশ লিখুন:**", parse_mode="Markdown", reply_markup=back_markup())
            bot.register_next_step_handler(msg, send_broadcast)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Admin Error: {e}")

# Admin Sub-Actions
@bot.callback_query_handler(func=lambda call: call.data.startswith('fsub_') or call.data.startswith('tdkey_') or call.data.startswith('delkey_') or call.data.startswith('ban_') or call.data.startswith('unban_'))
def admin_sub_actions(call):
    if call.message.chat.id not in [ADMIN_ID, DEVELOPER_ID]: return
    
    try:
        if call.data == "fsub_remove":
            db.reference('settings/force_sub').delete()
            bot.answer_callback_query(call.id, "Channel removed!")
            bot.edit_message_text("⚙️ **Admin Dashboard**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_admin_markup())
            
        elif call.data == "fsub_set":
            msg = bot.send_message(call.message.chat.id, "চ্যানেলের ইউজারনেম দিন (যেমন: @MyChannel):", reply_markup=back_markup())
            bot.register_next_step_handler(msg, lambda m: db.reference('settings/force_sub').set(m.text) if m.text not in ["🔙 Back to Main Menu", "❌ Cancel"] else back_to_main(m))
            
        elif call.data.startswith("delkey_"):
            idx = int(call.data.split('_')[1])
            keys = db.reference('settings/mail_td_keys').get() or []
            if 0 <= idx < len(keys):
                del keys[idx]
                db.reference('settings/mail_td_keys').set(keys)
                bot.answer_callback_query(call.id, "API Key Deleted!")
                
                text = "🔑 **Mail.td API Keys Management:**\n_(Delete one by one)_"
                markup = InlineKeyboardMarkup(row_width=1)
                for i, key in enumerate(keys):
                    short_key = key[:10] + "..." if len(key)>10 else key
                    markup.add(InlineKeyboardButton(f"🗑️ Delete: {short_key}", callback_data=f"delkey_{i}"))
                markup.add(InlineKeyboardButton("➕ Add New API Key", callback_data="tdkey_add"))
                markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
                bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
                
        elif call.data == "tdkey_add":
            msg = bot.send_message(call.message.chat.id, "নতুন Mail.td API Key দিন (যেমন: td_102eb...):", reply_markup=back_markup())
            def save_key(m):
                if m.text in ["🔙 Back to Main Menu", "❌ Cancel"]: return back_to_main(m)
                keys = db.reference('settings/mail_td_keys').get() or []
                if m.text not in keys: keys.append(m.text)
                db.reference('settings/mail_td_keys').set(keys)
                bot.send_message(m.chat.id, "✅ API Key Added Successfully!", reply_markup=main_menu(m.chat.id))
            bot.register_next_step_handler(msg, save_key)
            
        elif call.data.startswith('ban_'):
            uid = call.data.split('_')[1]
            db.reference(f'users/{uid}/banned').set(True)
            bot.answer_callback_query(call.id, "User Banned!")
            
        elif call.data.startswith('unban_'):
            uid = call.data.split('_')[1]
            db.reference(f'users/{uid}/banned').set(False)
            bot.answer_callback_query(call.id, "User Unbanned!")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {e}")

def process_user_manage(message):
    if message.text in ["🔙 Back to Main Menu", "❌ Cancel"]: return back_to_main(message)
    target_id = message.text.strip()
    data = get_user_data(target_id)
    
    text = f"👤 **User Details:**\n🆔 ID: `{target_id}`\n🚫 Banned: `{data.get('banned', False)}`\n📧 Active Mails: `{len(data.get('mails', {})) if isinstance(data.get('mails'), dict) else 0}`"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{target_id}"), InlineKeyboardButton("✅ Unban", callback_data=f"unban_{target_id}"))
    markup.add(InlineKeyboardButton("🔙 Admin Home", callback_data="admin_home"))
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu(message.chat.id))
    bot.send_message(message.chat.id, "অ্যাকশন সিলেক্ট করুন:", reply_markup=markup)

def send_broadcast(message):
    if message.text in ["🔙 Back to Main Menu", "❌ Cancel"]: return back_to_main(message)
    users = db.reference('users').get() or {}
    sent = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 **Notice from Admin:**\n\n{message.text}", parse_mode="Markdown")
            sent += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ Notice sent to {sent} users.", reply_markup=main_menu(message.chat.id))

# --- High Performance Multi-Threaded Auto Checker ---
def fetch_mail_for_user(chat_id, user_data):
    try:
        active = user_data.get("active_mail")
        mails = user_data.get("mails", {})
        if not active or not isinstance(mails, dict) or active.replace('.', ',') not in mails: return
        
        mail_info = mails[active.replace('.', ',')]
        server = mail_info.get("server", "mail.gw")
        seen_key = f"users/{chat_id}/mails/{active.replace('.', ',')}/seen"
        seen_msgs = db.reference(seen_key).get() or []
        
        if server == "mail.td":
            client = MailTD(mail_info.get("token"))
            account_id = mail_info.get("account_id")
            messages, _ = client.messages.list(account_id)
            
            for msg_preview in messages:
                msg_id = msg_preview.id
                if msg_id not in seen_msgs:
                    seen_msgs.append(msg_id)
                    db.reference(seen_key).set(seen_msgs)
                    full_msg = client.messages.get(account_id, msg_id)
                    subj = getattr(full_msg, 'subject', 'No Subject')
                    sender = getattr(full_msg, 'from_address', getattr(full_msg, 'sender', 'Unknown'))
                    text = getattr(full_msg, 'text_body', '')
                    html_body = getattr(full_msg, 'html_body', '')
                    build_and_send_notification(chat_id, sender, subj, text, html_body)
        else:
            headers = get_api_headers(mail_info.get("token"))
            res = requests.get('https://api.mail.gw/messages', headers=headers, timeout=10).json()
            messages = res if isinstance(res, list) else res.get('hydra:member', [])
            
            for msg in messages:
                msg_id = msg['id']
                if msg_id not in seen_msgs:
                    seen_msgs.append(msg_id)
                    db.reference(seen_key).set(seen_msgs)
                    full_msg = requests.get(f'https://api.mail.gw/messages/{msg_id}', headers=headers, timeout=10).json()
                    subj = msg.get('subject', 'No Subject')
                    sender = msg['from'].get('address', 'Unknown') if isinstance(msg.get('from'), dict) else msg.get('from', 'Unknown')
                    text = full_msg.get('text', '') or full_msg.get('intro', '')
                    html_body = full_msg.get('html', '') or full_msg.get('htmlBody', '')
                    build_and_send_notification(chat_id, sender, subj, text, html_body)
    except: pass

def auto_check_inbox():
    while True:
        try:
            users = db.reference('users').get() or {}
            for chat_id, data in users.items():
                if isinstance(data, dict) and data.get("active_mail"):
                    Thread(target=fetch_mail_for_user, args=(chat_id, data)).start()
        except: pass
        time.sleep(10)

# --- Flask & Server Run ---
app = Flask(__name__)
@app.route('/')
def index(): return "SaaS Bot is Running & Stable!"

def run_flask(): 
    try: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    except: pass

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    Thread(target=auto_check_inbox, daemon=True).start()
    
    # Auto Polling Recovery System
    while True:
        try:
            print("Starting Bot Polling...")
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Bot Polling Crashed: {e}. Restarting in 3 seconds...")
            time.sleep(3)
