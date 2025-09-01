from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackContext, JobQueue
from telegram.ext import MessageHandler, filters, CallbackQueryHandler
from telegram.error import Forbidden
import requests
import sqlite3
import re
from datetime import time, timezone, timedelta
from mistral_chat import ask_mistral
from config import TELEGRAM_TOKEN, CHAT_ID, NEWS_API_KEY
from translate import translate_text

MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"

# Veritabanı bağlantısı
conn = sqlite3.connect("user_settings.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    hour INTEGER,
    minute INTEGER,
    category TEXT
)
""")
conn.commit()

def summarize_news(title, description):
    if not description:
        return "Özet oluşturulamadı."

    prompt = f"""
    Summarize the following news in a short and fluent English paragraph, 
    without using any numbered or bullet points. Keep it clear and concise. 
    Do not repeat the description or the input text.
    Title: {title}
    Description: {description}
    Summary:
    """
    try:
        english_summary = ask_mistral(prompt)
        return translate_text(english_summary)  # Türkçeye çevir
    except Exception as e:
        return f"⚠️ Özetleme hatası: {e}"

def get_news(category="technology"):
    url = f'https://newsapi.org/v2/top-headlines?country=us&category={category}&apiKey={NEWS_API_KEY}'
    try:
        response = requests.get(url)
        articles = response.json().get("articles", [])[:5]
        return [{
            "title": translate_text(a.get("title")),
            "description": translate_text(a.get("description")),
            "summary": summarize_news(a.get("title"), a.get("description")),
            "url": a.get("url"),
            "image": a.get("urlToImage")
        } for a in articles if a.get("url")]
    except:
        return []

# özetlenmiş haberi resim ve bağlantı olarak gönderir.

async def send_article(bot, chat_id, article):
    caption = f"*{article['title']}*\n\n{article['summary']}\n[-> Habere Git]({article['url']})"
    try:
        await bot.send_photo(chat_id=chat_id, photo=article['image'], caption=caption, parse_mode="Markdown")
    except:
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")

# Komut: Başlangıç
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "👋 Merhaba! Ben haber asistanınızım.\n\n"
        "📰 /news [kategori] – Günlük haberleri listeler.\n"
        "💬 /chat – Yapay zeka sohbetidir, dilediğiniz soruyu sorabilirsiniz.\n"
        "⏰ /abone saat:dakika kategori– Abonelik başlatmayı sağlar.(Örn. 14:00 technology)\n"
        "📌 /abonelik – Mevcut aboneliğinizi gösterir\n"
        "❌ /abonelik_sil – Aboneliği iptal eder.\n\n"
        "Haber Başlıkları: \niş->business, \neğlence->entertainment, \ngenel->general, \nsağlık->health, \nbilim->science, \nspor->sports, \nteknoloji->technology, \npolitika->politics"
    )

async def chat(update: Update, context: CallbackContext):
    user_input = " ".join(context.args)
    
    prompt = f"""Aşağıdaki soruya şu kriterlerle Türkçe yanıt ver:
1. **Akademik Format**: Lisansüstü seviyede ancak anlaşılır dil
2. **Yapısal Bütünlük**: Giriş-Gelişme-Sonuç mantığı (max 4 cümle)
3. **Kaynak Gösterme**: Veriler için kaynak linki belirtilmeli
4. **Terminoloji**: Teknik terimler parantez içinde basitçe açıklansın
5. **Uzunluk**: 40-60 kelime aralığı

Soru: "{user_input.strip()}"

Analitik Yanıt:"""
    
    response = ask_mistral(prompt)
    await update.message.reply_text(response)

# Komut: Haber getir
async def news(update: Update, context: CallbackContext):
    valid_categories = ["business", "entertainment", "general", "health", "science", "sports", "technology", "politics"]
    category = context.args[0].lower() if context.args else "technology"
    if category not in valid_categories:
        await update.message.reply_text(f"⚠️ Geçersiz kategori! Geçerli kategoriler: {', '.join(valid_categories)}")
        return

    news_list = get_news(category)
    if not news_list:
        await update.message.reply_text("⚠️ Bugün bu kategoride haber bulunamadı!")
        return

    for article in news_list:
        await send_article(context.bot, update.message.chat_id, article)

# Komut: Abone ol
async def abone(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if len(context.args) != 2:
        await update.message.reply_text("⚠️ Lütfen şu formatta kullanın: /abone 08:30 technology")
        return

    time_input, category = context.args
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_input)

    valid_categories = ["business", "entertainment", "general", "health", "science", "sports", "technology", "politics"]

    if not match:
        await update.message.reply_text("⚠️ Saat formatı geçersiz. Örnek: 08:30")
        return
    if category not in valid_categories:
        await update.message.reply_text(f"⚠️ Geçersiz kategori. Kategoriler: {', '.join(valid_categories)}")
        return

    hour, minute = map(int, match.groups())
    cursor.execute("REPLACE INTO users (user_id, hour, minute, category) VALUES (?, ?, ?, ?)", (user_id, hour, minute, category))
    conn.commit()

    time_obj = time(hour=hour, minute=minute, tzinfo=timezone(timedelta(hours=3)))
    context.job_queue.run_daily(user_specific_news, time_obj, data=user_id, name=str(user_id))
    await update.message.reply_text(f"✅ {hour:02}:{minute:02} saatinde '{category}' kategorisinde haber gönderilecek.")

# Komut: Abonelik kontrol
async def abonelik(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    cursor.execute("SELECT hour, minute, category FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        hour, minute, category = row
        await update.message.reply_text(f"📌 Güncel aboneliğiniz:\nSaat: {hour:02}:{minute:02}\nKategori: {category}")
    else:
        await update.message.reply_text("🔍 Kayıtlı bir aboneliğiniz bulunmamaktadır.")

# Komut: Abonelik sil
async def abonelik_sil(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    await update.message.reply_text("🚫 Aboneliğiniz başarıyla silindi.")

    # Komut: Aboneleri Listele (admin için, isimli)
async def aboneler(update: Update, context: CallbackContext):
    admin_id = 1227397155 # Kendi Telegram kullanıcı ID’in
    user_id = update.message.from_user.id

    if user_id != admin_id:
        await update.message.reply_text("🚫 Bu komut sadece yöneticilere özeldir.")
        return

    cursor.execute("SELECT user_id, hour, minute, category FROM users")
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 Hiçbir kullanıcı abone değil.")
        return

    text = "📋 *Abone Olan Kullanıcılar:*\n\n"

    for uid, hour, minute, category in rows:
        try:
            # Kullanıcı bilgisi getir
            user = await context.bot.get_chat(uid)
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            username = f"@{user.username}" if user.username else ""
        except:
            name = "(kullanıcıya erişilemedi)"
            username = ""

        text += f"👤 `{uid}` – {name} {username}\n🕒 {hour:02}:{minute:02} – 🗂️ {category}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# Inline: Kategori seçimi
async def handle_category_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    category = query.data.replace("category_", "")
    await query.answer()
    cursor.execute("REPLACE INTO users (user_id, hour, minute, category) VALUES (?, ?, ?, ?)", (user_id, 0, 0, category))
    conn.commit()

    times = ["08:00", "09:00", "10:00", "12:00", "14:00","14:30","15:00","16:00","16:03","16:30", "18:00","20:00","23:00"]
    keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in times]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ *{category.capitalize()}* kategorisini seçtiniz.\nLütfen haber almak istediğiniz saati seçiniz:",
        parse_mode="Markdown", reply_markup=reply_markup
    )

# Inline: Saat seçimi
async def handle_time_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    time_data = query.data.replace("time_", "")
    hour, minute = map(int, time_data.split(":"))

    cursor.execute("SELECT category FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        await query.answer("Kategori seçimi bulunamadı, lütfen önce kategori seçin.")
        return
    category = row[0]
    cursor.execute("REPLACE INTO users (user_id, hour, minute, category) VALUES (?, ?, ?, ?)", (user_id, hour, minute, category))
    conn.commit()

    for job in context.job_queue.get_jobs_by_name(str(user_id)):
        job.schedule_removal()

    time_obj = time(hour=hour, minute=minute, tzinfo=timezone(timedelta(hours=3)))
    context.job_queue.run_daily(user_specific_news, time_obj, data=user_id, name=str(user_id))

    await query.answer()
    await query.edit_message_text(f"✅ Saat {hour:02}:{minute:02} olarak ayarlandı. {category} kategorisindeki haberler bu saatte gönderilecek.")

# Inline: Yeni kullanıcı karşılama
async def welcome_and_prompt_category(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    cursor.execute("SELECT category FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        return

    categories = [
        ["iş", "eğlence", "genel"],
        ["sağlık", "bilim", "spor", "teknoloji"]
    ]
    keyboard = [[InlineKeyboardButton(cat.capitalize(), callback_data=f"category_{cat}") for cat in row] for row in categories]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("👋 Hoşgeldiniz! Lütfen ilgilendiğiniz kategoriyi seçiniz:", reply_markup=reply_markup)

# Görev: Kullanıcıya özel haber gönder
async def user_specific_news(context: CallbackContext):
    user_id = context.job.data
    cursor.execute("SELECT category FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        return  # Kullanıcı veritabanından silinmiş olabilir

    category = row[0]
    news_list = get_news(category)

    if not news_list:
        try:
            await context.bot.send_message(chat_id=user_id, text="⚠️ Bugün bu kategoride haber bulunamadı.")
        except Forbidden:
            pass  # Bot, kullanıcıya artık mesaj gönderemiyor olabilir
        return

    for article in news_list:
        try:
            await send_article(context.bot, user_id, article)
        except Exception as e:
            print(f"Haber gönderim hatası: {e}")


# Ana uygulama
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handlers([
        CommandHandler("start", start),
        CommandHandler("news", news),
        CommandHandler("chat", chat),
        CommandHandler("abone", abone),
        CommandHandler("abonelik", abonelik),
        CommandHandler("abonelik_sil", abonelik_sil),
        CommandHandler("aboneler", aboneler),
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT, welcome_and_prompt_category),
        CallbackQueryHandler(handle_category_selection, pattern="^category_"),
        CallbackQueryHandler(handle_time_selection, pattern="^time_")
    ])

    application.run_polling()

if __name__ == '__main__':
    main()
