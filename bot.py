import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import requests
import random
import string
import os
import pyotp
from flask import Flask
from threading import Thread

# আপনার দেওয়া বটের টোকেন সরাসরি বসানো হয়েছে
BOT_TOKEN = "8068023821:AAEkhKKmiYcAFtv25WKr7v1hLlzMFYyQcHc"
bot = telebot.TeleBot(BOT_TOKEN)

# ইউজারদের ডেটা সেভ রাখার জন্য
users_data = {}

def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

# --- নিচের বাটন মেনু (Bottom Keyboard) ---
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_gen = KeyboardButton("✉️ Generate Mail")
    btn_inbox = KeyboardButton("📥 Inbox")
    btn_2fa = KeyboardButton("🔑 2FA Authenticator")
    markup.add(btn_gen, btn_inbox)
    markup.add(btn_2fa)
    return markup

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "👋 *Temp Mail & 2FA Bot*-এ স্বাগতম!\n\nনিচের বাটনগুলো ব্যবহার করে খুব সহজেই মেইল তৈরি, ইনবক্স চেক এবং 2FA কোড বের করতে পারবেন।", parse_mode="Markdown", reply_markup=main_menu())

# --- 2FA Authenticator এর কাজ ---
@bot.message_handler(func=lambda message: message.text == "🔑 2FA Authenticator")
def ask_2fa_secret(message):
    msg = bot.reply_to(message, "🔐 **আপনার 2FA Secret Key (Setup Key) দিন:**\n*(যেকোনো ওয়েবসাইটের 2FA চালু করার সময় যে সিক্রেট টেক্সট দেয়, সেটি এখানে পেস্ট করুন)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, generate_otp_code)

def generate_otp_code(message):
    secret = message.text.strip().replace(" ", "")
    try:
        totp = pyotp.TOTP(secret)
        otp_code = totp.now()
        bot.reply_to(message, f"✅ **আপনার 2FA OTP কোড:**\n\n`{otp_code}`\n\n*(কোডটির ওপর ক্লিক করলেই কপি হয়ে যাবে)*", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ **ভুল Secret Key!** দয়া করে সঠিক Key দিন।", parse_mode="Markdown")

# --- Temp Mail Generate করার কাজ ---
@bot.message_handler(func=lambda message: message.text == "✉️ Generate Mail" or message.text == "/generate")
def generate_mail(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ ইমেইল তৈরি হচ্ছে, একটু অপেক্ষা করুন...")
    
    try:
        domain_res = requests.get('https://api.mail.gw/domains').json()
        domain = domain_res['hydra:member'][0]['domain']
        
        username = generate_random_string()
        email = f"{username}@{domain}"
        password = generate_random_string(10)
        
        acc_data = {"address": email, "password": password}
        requests.post('https://api.mail.gw/accounts', json=acc_data)
        
        token_res = requests.post('https://api.mail.gw/token', json=acc_data).json()
        token = token_res['token']
        
        users_data[chat_id] = {"email": email, "password": password, "token": token}
        
        msg = f"✅ **আপনার নতুন ইমেইল তৈরি হয়েছে!**\n\n📧 **ইমেইল:** `{email}`\n🔑 **পাসওয়ার্ড:** `{password}`\n\nমেইল চেক করতে '📥 Inbox' বাটনে ক্লিক করুন।"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(chat_id, "❌ কোনো একটা সমস্যা হয়েছে। আবার চেষ্টা করুন।")

# --- Inbox চেক করার কাজ ---
@bot.message_handler(func=lambda message: message.text == "📥 Inbox" or message.text == "/inbox")
def check_inbox(message):
    chat_id = message.chat.id
    if chat_id not in users_data:
        bot.send_message(chat_id, "⚠️ আপনার কোনো ইমেইল নেই! আগে '✉️ Generate Mail' বাটনে ক্লিক করুন।")
        return
        
    token = users_data[chat_id]['token']
    headers = {'Authorization': f'Bearer {token}'}
    
    bot.send_message(chat_id, "🔄 ইনবক্স চেক করা হচ্ছে...")
    
    try:
        messages_res = requests.get('https://api.mail.gw/messages', headers=headers).json()
        messages = messages_res.get('hydra:member', [])
        
        if not messages:
            bot.send_message(chat_id, "📭 ইনবক্সে কোনো নতুন মেইল নেই।")
        else:
            for msg in messages:
                sender = msg['from']['address']
                subject = msg['subject']
                msg_id = msg['id']
                text = f"📩 **নতুন মেইল!**\n\n👤 **From:** `{sender}`\n📌 **Subject:** {subject}\n\nমেইলটি পড়তে নিচের কমান্ডটিতে ক্লিক করুন:\n`/read_{msg_id}`"
                bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, "❌ ইনবক্স চেক করতে সমস্যা হচ্ছে।")

# --- মেইল পড়ার কাজ ---
@bot.message_handler(func=lambda message: message.text.startswith('/read_'))
def read_message(message):
    chat_id = message.chat.id
    msg_id = message.text.split('_')[1]
    
    if chat_id not in users_data:
        bot.send_message(chat_id, "⚠️ আপনার একাউন্ট পাওয়া যায়নি।")
        return
        
    token = users_data[chat_id]['token']
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        msg_res = requests.get(f'https://api.mail.gw/messages/{msg_id}', headers=headers).json()
        content = msg_res.get('text', 'No text content available.')
        bot.send_message(chat_id, f"📄 **মেইলের বিষয়বস্তু:**\n\n{content}", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, "❌ মেইলটি পড়তে সমস্যা হচ্ছে।")

# --- Render Web Service-এর জন্য Flask ---
app = Flask(__name__)
@app.route('/')
def index():
    return "Bot is running perfectly on Render!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.polling(none_stop=True)
