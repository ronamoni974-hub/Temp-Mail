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

# ইউজারদের ডেটা
users_data = {}

# --- Helper Functions ---
def generate_random_string(length=10):
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for i in range(length))

def extract_otp(text):
    """স্মার্ট OTP স্ক্যানার (৬-৮ ডিজিট বা স্পেস দেওয়া লেটার)"""
    # স্পেস দেওয়া লেটার/নাম্বার (যেমন: A H d Y s j H Z)
    spaced_match = re.search(r'(?:[A-Za-z0-9]\s+){5,}[A-Za-z0-9]', text)
    if spaced_match:
        return spaced_match.group(0).replace(" ", "")
        
    # ৬ থেকে ৮ ডিজিটের সাধারণ OTP
    digits = re.search(r'\b\d{4,8}\b', text)
    if digits:
        return digits.group(0)
        
    # ৬-৮ ক্যারেক্টারের আলফানিউমেরিক কোড
    alnum = re.search(r'\b[A-Z0-9]{5,10}\b', text, re.IGNORECASE)
    if alnum:
        return alnum.group(0)
        
    return None

# --- UI Elements ---
BOX_TOP = "╔══════════════════════════╗"
BOX_BOT = "╚══════════════════════════╝"

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_gen = KeyboardButton("✨ Generate Premium Mail")
    btn_inbox = KeyboardButton("📥 Inbox")
    btn_2fa = KeyboardButton("🔐 2FA Authenticator")
    markup.add(btn_gen, btn_inbox)
    markup.add(btn_2fa)
    return markup

# --- Mail Fetching Logic (Used by both Auto & Manual) ---
def fetch_and_send_mails(chat_id, data, is_manual=False):
    token = data.get('token')
    if not token:
        if is_manual:
            bot.send_message(chat_id, "⚠️ আপনার কোনো ইমেইল নেই! আগে '✨ Generate Premium Mail' এ ক্লিক করুন।")
        return

    headers = {'Authorization': f'Bearer {token}'}
    seen_msgs = data.get('seen_msgs', set())
    
    try:
        res = requests.get('[https://api.mail.gw/messages](https://api.mail.gw/messages)', headers=headers).json()
        messages = res.get('hydra:member', [])
        
        new_mail_found = False
        
        for msg in messages:
            msg_id = msg['id']
            if msg_id not in seen_msgs:
                seen_msgs.add(msg_id)
                users_data[chat_id]['seen_msgs'] = seen_msgs
                new_mail_found = True
                
                # মেইলের বিস্তারিত আনা
                full_msg = requests.get(f'[https://api.mail.gw/messages/](https://api.mail.gw/messages/){msg_id}', headers=headers).json()
                text_content = full_msg.get('text', '')
                subject = msg.get('subject', 'No Subject')
                sender = msg['from']['address']
                
                # OTP স্ক্যান
                otp = extract_otp(subject + " " + text_content)
                
                notification = f"🔔 **NEW MAIL RECEIVED!** 🔔\n\n"
                notification += f"👤 **From:** `{sender}`\n"
                notification += f"📌 **Subject:** {subject}\n\n"
                
                if otp:
                    notification += f"🔑 **Scanned OTP/Code:**\n"
                    notification += f"{BOX_TOP}\n"
                    notification += f"👉 `{otp}` 👈\n"
                    notification += f"{BOX_BOT}\n\n"
                
                notification += f"📄 **Message:**\n_{text_content[:300]}..._"
                bot.send_message(chat_id, notification, parse_mode="Markdown")
        
        if is_manual and not new_mail_found:
            bot.send_message(chat_id, "📭 ইনবক্সে কোনো নতুন মেইল নেই। অটোমেটিক চেকার চালু আছে।")
            
    except Exception as e:
        if is_manual:
            bot.send_message(chat_id, "❌ ইনবক্স চেক করতে সমস্যা হচ্ছে।")

# --- Auto Inbox Checker (Background Thread) ---
def auto_check_inbox():
    while True:
        for chat_id, data in list(users_data.items()):
            fetch_and_send_mails(chat_id, data, is_manual=False)
        time.sleep(5) # প্রতি ৫ সেকেন্ড পর পর চেক করবে

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "💎 *Premium Temp Mail & 2FA Bot*\n\nঅটোমেটিক ইনবক্স এবং স্মার্ট OTP স্ক্যানার সিস্টেম চালু আছে। ইনবক্স বাটনটিও আবার যুক্ত করা হয়েছে।", parse_mode="Markdown", reply_markup=main_menu())

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
        text += f"{BOX_TOP}\n"
        text += f"👉 `{otp_code}` 👈\n"
        text += f"{BOX_BOT}\n\n"
        text += f"*(ক্লিক করলেই কপি হয়ে যাবে)*"
        
        bot.reply_to(message, text, parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ **ভুল Secret Key!**")

@bot.message_handler(func=lambda message: message.text == "✨ Generate Premium Mail" or message.text == "/generate")
def generate_mail(message):
    chat_id = message.chat.id
    
    loading_msg = bot.send_message(chat_id, "⏳ `[■■□□□□□□□□] 20%`\nConnecting to server...", parse_mode="Markdown")
    
    try:
        domain_res = requests.get('[https://api.mail.gw/domains](https://api.mail.gw/domains)').json()
        domain = domain_res['hydra:member'][0]['domain']
        
        bot.edit_message_text("⏳ `[■■■■■■□□□□] 60%`\nGenerating domain address...", chat_id, loading_msg.message_id, parse_mode="Markdown")
        
        username = generate_random_string(10)
        email = f"{username}@{domain}"
        password = generate_random_string(12)
        
        acc_data = {"address": email, "password": password}
        requests.post('[https://api.mail.gw/accounts](https://api.mail.gw/accounts)', json=acc_data)
        
        bot.edit_message_text("⏳ `[■■■■■■■■■□] 90%`\nActivating Live Inbox...", chat_id, loading_msg.message_id, parse_mode="Markdown")
        
        token_res = requests.post('[https://api.mail.gw/token](https://api.mail.gw/token)', json=acc_data).json()
        token = token_res['token']
        
        users_data[chat_id] = {
            "email": email, 
            "token": token, 
            "seen_msgs": set()
        }
        
        bot.delete_message(chat_id, loading_msg.message_id)
        
        # Clean Premium Box
        final_msg = f"✨ **Premium Mail Generated Successfully!** ✨\n\n"
        final_msg += f"{BOX_TOP}\n"
        final_msg += f"👉 `{email}` 👈\n"
        final_msg += f"{BOX_BOT}\n\n"
        final_msg += f"🟢 **Live Status: Active & Listening...**\n"
        final_msg += f"*(যেকোনো মেইল বা OTP আসলে এখানে অটোমেটিক শো করবে। প্রয়োজনে Inbox বাটনে ক্লিক করতে পারেন!)*"
        
        bot.send_message(chat_id, final_msg, parse_mode="Markdown")
        
    except Exception:
        bot.edit_message_text("❌ Server Error! Please try again.", chat_id, loading_msg.message_id)

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
