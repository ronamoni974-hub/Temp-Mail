import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import requests
import random
import string
import os
import pyotp
import time
import re
from flask import Flask
from threading import Thread

# আপনার বটের টোকেন
BOT_TOKEN = "8068023821:AAEkhKKmiYcAFtv25WKr7v1hLlzMFYyQcHc"
bot = telebot.TeleBot(BOT_TOKEN)

users_data = {}

# --- API Headers ---
API_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

# --- Helper Functions ---
def generate_random_string(length=10):
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for i in range(length))

def extract_otp(text):
    if not text:
        return None
    spaced_match = re.search(r'(?:[A-Za-z0-9]\s+){5,}[A-Za-z0-9]', text)
    if spaced_match:
        return spaced_match.group(0).replace(" ", "")
        
    digits = re.search(r'\b\d{4,8}\b', text)
    if digits:
        return digits.group(0)
        
    alnum = re.search(r'\b[A-Z0-9]{5,10}\b', text, re.IGNORECASE)
    if alnum:
        return alnum.group(0)
        
    return None

# --- UI Elements ---
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_gen = KeyboardButton("✨ Generate Premium Mail")
    btn_inbox = KeyboardButton("📥 Inbox")
    btn_2fa = KeyboardButton("🔐 2FA Authenticator")
    markup.add(btn_gen, btn_inbox)
    markup.add(btn_2fa)
    return markup

# --- Mail Fetching Logic ---
def fetch_and_send_mails(chat_id, data, is_manual=False):
    token = data.get('token')
    if not token:
        if is_manual:
            bot.send_message(chat_id, "⚠️ আপনার কোনো ইমেইল নেই! আগে '✨ Generate Premium Mail' এ ক্লিক করুন।")
        return

    headers = {
        'Authorization': f'Bearer {token}',
        'User-Agent': API_HEADERS['User-Agent'],
        'Accept': 'application/json'
    }
    seen_msgs = data.get('seen_msgs', set())
    
    try:
        res = requests.get('https://api.mail.gw/messages', headers=headers)
        if res.status_code != 200:
            return
            
        res_data = res.json()
        
        if isinstance(res_data, list):
            messages = res_data
        else:
            messages = res_data.get('hydra:member', [])
            
        new_mail_found = False
        
        for msg in messages:
            msg_id = msg['id']
            if msg_id not in seen_msgs:
                seen_msgs.add(msg_id)
                users_data[chat_id]['seen_msgs'] = seen_msgs
                new_mail_found = True
                
                full_msg_res = requests.get(f'https://api.mail.gw/messages/{msg_id}', headers=headers)
                if full_msg_res.status_code == 200:
                    full_msg = full_msg_res.json()
                    
                    # HTML বা Intro সাপোর্ট যুক্ত করা হলো
                    text_content = full_msg.get('text', '')
                    if not text_content:
                        text_content = full_msg.get('intro', '')
                        
                    subject = msg.get('subject', 'No Subject')
                    
                    if isinstance(msg.get('from'), dict):
                        sender = msg['from'].get('address', 'Unknown')
                    else:
                        sender = msg.get('from', 'Unknown')
                    
                    otp = extract_otp(subject + " " + text_content)
                    
                    notification = f"🔔 **NEW MAIL RECEIVED!** 🔔\n\n"
                    notification += f"👤 **From:** `{sender}`\n"
                    notification += f"📌 **Subject:** {subject}\n\n"
                    
                    if otp:
                        notification += f"🔑 **Scanned Code/OTP:**\n"
                        notification += f"👉 `{otp}` 👈\n\n"
                    
                    # ক্লিন মেসেজ বডি
                    clean_text = text_content[:300].replace('*', '').replace('_', '')
                    notification += f"📄 **Message:**\n_{clean_text}..._"
                    
                    bot.send_message(chat_id, notification, parse_mode="Markdown")
        
        if is_manual and not new_mail_found:
            bot.send_message(chat_id, "📭 ইনবক্সে কোনো নতুন মেইল নেই।")
            
    except Exception as e:
        if is_manual:
            bot.send_message(chat_id, "❌ ইনবক্স চেক করতে সমস্যা হচ্ছে। সার্ভার ব্যস্ত থাকতে পারে।")

# --- Auto Inbox Checker ---
def auto_check_inbox():
    while True:
        for chat_id, data in list(users_data.items()):
            fetch_and_send_mails(chat_id, data, is_manual=False)
        time.sleep(10) # রেট লিমিট এড়াতে টাইম বাড়ানো হলো

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "💎 *Premium Temp Mail & 2FA Bot*\n\nঅটোমেটিক ইনবক্স এবং স্মার্ট OTP স্ক্যানার সিস্টেম চালু আছে। নিচের বাটন থেকে সার্ভিস সিলেক্ট করুন।", parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🔐 2FA Authenticator")
def ask_2fa_secret(message):
    msg = bot.reply_to(message, "🛡️ **আপনার 2FA Setup/Secret Key দিন:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, generate_otp_code)

def generate_otp_code(message):
    secret = message.text.strip().replace(" ", "")
    try:
        totp = pyotp.TOTP(secret)
        otp_code = totp.now()
        
        text = f"✅ **2FA Authenticator Code:**\n\n"
        text += f"👉 `{otp_code}` 👈"
        
        bot.reply_to(message, text, parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ **ভুল Secret Key!**")

@bot.message_handler(func=lambda message: message.text == "✨ Generate Premium Mail" or message.text == "/generate")
def generate_mail(message):
    chat_id = message.chat.id
    
    loading_msg = bot.send_message(chat_id, "⏳ `[■■□□□□□□□□] 20%`\nConnecting to server...", parse_mode="Markdown")
    
    try:
        domain_res = requests.get('https://api.mail.gw/domains', headers=API_HEADERS)
        if domain_res.status_code != 200:
            bot.edit_message_text(f"❌ API Error (Domain): {domain_res.status_code}", chat_id, loading_msg.message_id)
            return
            
        domain_data = domain_res.json()
        
        if isinstance(domain_data, list) and len(domain_data) > 0:
            domain = domain_data[0].get('domain', 'mail.gw')
        elif isinstance(domain_data, dict) and 'hydra:member' in domain_data and len(domain_data['hydra:member']) > 0:
            domain = domain_data['hydra:member'][0].get('domain', 'mail.gw')
        else:
            domain = 'mail.gw' 
            
        bot.edit_message_text("⏳ `[■■■■■■□□□□] 60%`\nGenerating domain address...", chat_id, loading_msg.message_id, parse_mode="Markdown")
        
        username = generate_random_string(10)
        email = f"{username}@{domain}"
        password = generate_random_string(12)
        acc_data = {"address": email, "password": password}
        
        acc_res = requests.post('https://api.mail.gw/accounts', json=acc_data, headers=API_HEADERS)
        if acc_res.status_code not in [200, 201]:
            bot.edit_message_text(f"❌ Registration Error! Try again.", chat_id, loading_msg.message_id)
            return

        bot.edit_message_text("⏳ `[■■■■■■■■■□] 90%`\nActivating Live Inbox...", chat_id, loading_msg.message_id, parse_mode="Markdown")
        
        token_res = requests.post('https://api.mail.gw/token', json=acc_data, headers=API_HEADERS)
        if token_res.status_code not in [200, 201]:
            bot.edit_message_text(f"❌ Token Error! Try again.", chat_id, loading_msg.message_id)
            return
            
        token_data = token_res.json()
        token = token_data.get('token')
        
        users_data[chat_id] = {
            "email": email, 
            "token": token, 
            "seen_msgs": set()
        }
        
        bot.delete_message(chat_id, loading_msg.message_id)
        
        final_msg = f"✨ **Premium Mail Generated Successfully!** ✨\n\n"
        final_msg += f"👉 `{email}` 👈\n\n"
        final_msg += f"🟢 **Live Status: Active & Listening...**\n"
        final_msg += f"_(যেকোনো মেইল বা OTP আসলে এখানে অটোমেটিক শো করবে।)_"
        
        bot.send_message(chat_id, final_msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.edit_message_text(f"❌ Server Error! Detail: {str(e)}", chat_id, loading_msg.message_id)

@bot.message_handler(func=lambda message: message.text == "📥 Inbox" or message.text == "/inbox")
def check_inbox(message):
    chat_id = message.chat.id
    if chat_id not in users_data:
        bot.send_message(chat_id, "⚠️ আপনার কোনো ইমেইল নেই! আগে '✨ Generate Premium Mail' এ ক্লিক করুন।")
        return
        
    bot.send_message(chat_id, "🔄 ইনবক্স চেক করা হচ্ছে...")
    fetch_and_send_mails(chat_id, users_data[chat_id], is_manual=True)

# --- Render Web Service-এর জন্য Flask ---
app = Flask(__name__)
@app.route('/')
def index():
    return "Premium Bot is Live & Listening!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def start_threads():
    Thread(target=run_flask, daemon=True).start()
    Thread(target=auto_check_inbox, daemon=True).start()

if __name__ == "__main__":
    start_threads()
    bot.polling(none_stop=True)
