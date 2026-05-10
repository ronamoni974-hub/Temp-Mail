import telebot
import requests
import random
import string
import os
from flask import Flask
from threading import Thread

# Render-এর Environment Variables থেকে টোকেন নেবে
# তুমি চাইলে এখানে সরাসরি "8068023821:AAEkhKKmiYcAFtv25WKr7v1hLlzMFYyQcHc" বসিয়ে টেস্ট করতে পারো
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(BOT_TOKEN)

# ইউজারদের ডেটা সেভ রাখার জন্য (বট রিস্টার্ট হলে ডেটা মুছে যাবে, চাইলে ডেটাবেস যুক্ত করতে পারো)
users_data = {}

def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "👋 Temp Mail Bot-এ স্বাগতম!\n\n✨ নতুন ইমেইল তৈরি করতে `/generate` চাপুন।\n📥 ইনবক্স চেক করতে `/inbox` চাপুন।", parse_mode="Markdown")

@bot.message_handler(commands=['generate'])
def generate_mail(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ ইমেইল তৈরি হচ্ছে, একটু অপেক্ষা করুন...")
    
    try:
        # ডোমেইন নেওয়া
        domain_res = requests.get('https://api.mail.gw/domains').json()
        domain = domain_res['hydra:member'][0]['domain']
        
        # ইউজারনেম ও পাসওয়ার্ড বানানো
        username = generate_random_string()
        email = f"{username}@{domain}"
        password = generate_random_string(10)
        
        # Mail.gw তে একাউন্ট তৈরি
        acc_data = {"address": email, "password": password}
        requests.post('https://api.mail.gw/accounts', json=acc_data)
        
        # টোকেন নেওয়া
        token_res = requests.post('https://api.mail.gw/token', json=acc_data).json()
        token = token_res['token']
        
        # ডেটা ডিকশনারিতে সেভ রাখা
        users_data[chat_id] = {"email": email, "password": password, "token": token}
        
        msg = f"✅ **আপনার নতুন ইমেইল তৈরি হয়েছে!**\n\n📧 **ইমেইল:** `{email}`\n🔑 **পাসওয়ার্ড:** `{password}`\n\nমেইল চেক করতে `/inbox` ব্যবহার করুন।"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(chat_id, "❌ কোনো একটা সমস্যা হয়েছে। আবার চেষ্টা করুন।")

@bot.message_handler(commands=['inbox'])
def check_inbox(message):
    chat_id = message.chat.id
    if chat_id not in users_data:
        bot.send_message(chat_id, "⚠️ আপনার কোনো ইমেইল নেই! আগে `/generate` দিয়ে ইমেইল তৈরি করুন।", parse_mode="Markdown")
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
                text = f"📩 **নতুন মেইল!**\n\n👤 **From:** `{sender}`\n📌 **Subject:** {subject}\n\nমেইলটি পড়তে নিচের কমান্ডটিতে ক্লিক করুন:\n`/read {msg_id}`"
                bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, "❌ ইনবক্স চেক করতে সমস্যা হচ্ছে।")

@bot.message_handler(commands=['read'])
def read_message(message):
    chat_id = message.chat.id
    parts = message.text.split()
    
    if len(parts) < 2:
        bot.send_message(chat_id, "⚠️ ভুল কমান্ড! সঠিক নিয়ম: `/read <message_id>`", parse_mode="Markdown")
        return
        
    msg_id = parts[1]
    
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

# --- Render Web Service-এর পোর্ট ইস্যু ফিক্স করার জন্য Flask ---
app = Flask(__name__)
@app.route('/')
def index():
    return "Bot is running perfectly!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.polling(none_stop=True)

