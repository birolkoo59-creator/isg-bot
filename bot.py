import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID")

claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

SYSTEM_PROMPT = """Sen bir İş Sağlığı ve Güvenliği (İSG) danışmanlık firmasının resmi yapay zeka asistanısın.
Görevin müşterilerin İSG ile ilgili sorularını yanıtlamak, randevu almak ve iletişim formlarını doldurmalarına yardımcı olmak.

DAVRANIŞ KURALLARI:
- Her zaman resmi, nazik ve profesyonel bir dil kullan
- Yalnızca Türkçe yanıt ver
- İSG mevzuatı, yönetmelikleri ve teknik konularda bilgi ver
- Yanıtlarını net, anlaşılır ve kısa tut
- Eğer bir soruyu kesin olarak yanıtlayamazsan bunu açıkça belirt ve danışmana yönlendir
- Asla uydurma veya belirsiz bilgi verme
- Her yanıtın sonunda başka bir sorusu olup olmadığını sor

UZMANLIK ALANLARIN:
- 6331 Sayılı İş Sağlığı ve Güvenliği Kanunu
- Risk değerlendirmesi ve risk analizi
- İşyeri tehlike sınıfları (az tehlikeli, tehlikeli, çok tehlikeli)
- İSG uzmanı çalıştırma zorunlulukları ve süreler
- İşyeri hekimi gereksinimleri
- Acil durum planları ve tatbikatlar
- Kişisel koruyucu donanım (KKD) seçimi ve kullanımı
- İş kazası bildirimi ve meslek hastalıkları
- OSGB hizmetleri ve yasal yükümlülükler
- Çalışan eğitimleri ve sertifikasyon
- İSG iç yönetmelikleri ve prosedürler
- SGK mevzuatı ve iş kazası tazminatları

KESİN VE DOĞRU BİLGİLER (bu bilgileri değiştirme, birebir kullan):

6331 SAYILI KANUNA GÖRE İSG UZMANI VE İŞYERİ HEKİMİ ÇALIŞMA SÜRELERİ:
Zorunluluk eşiği: 1 ve daha fazla çalışanı olan TÜM işyerleri için geçerlidir.

| Tehlike Sınıfı   | İSG Uzmanı (dk/çalışan/ay) | İşyeri Hekimi (dk/çalışan/ay) |
|------------------|---------------------------|-------------------------------|
| Az Tehlikeli     | 10 dakika                 | 5 dakika                      |
| Tehlikeli        | 20 dakika                 | 10 dakika                     |
| Çok Tehlikeli    | 40 dakika                 | 15 dakika                     |

Örnek hesaplama: Tehlikeli sınıfta 50 çalışanı olan bir işyeri için:
- İSG Uzmanı: 50 x 20 = 1000 dakika/ay (≈ 16,6 saat/ay)
- İşyeri Hekimi: 50 x 10 = 500 dakika/ay (≈ 8,3 saat/ay)

YAPAMAYACAKLARIN:
- Kesin hukuki görüş vermek (avukatlara yönlendir)
- Kesin para cezası miktarı vermek (yönetmeliklere göre değişir, yönlendir)
- Kişisel tıbbi teşhis veya tedavi tavsiyesi vermek

EsKALASYON KURALI:
Eğer soruyu yanıtlayamazsan veya konunun uzman görüşü gerektirdiğini düşünüyorsan şu cümleyi kullan:
"Bu konuda size daha doğru ve güvenilir bilgi verebilmek için danışmanımızı devreye alıyorum."
"""


def init_db():
    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            name TEXT,
            phone TEXT,
            preferred_date TEXT,
            topic TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            name TEXT,
            phone TEXT,
            message TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_message(chat_id, role, content):
    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_history(chat_id, limit=10):
    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM conversations WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
        (chat_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def save_appointment(chat_id, name, phone, preferred_date, topic):
    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO appointments (chat_id, name, phone, preferred_date, topic, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, name, phone, preferred_date, topic, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def save_contact(chat_id, name, phone, message):
    conn = sqlite3.connect("isg_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO contacts (chat_id, name, phone, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (chat_id, name, phone, message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def ask_claude(chat_id, user_message):
    history = get_history(chat_id)
    history.append({"role": "user", "content": user_message})
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=history
    )
    return response.content[0].text


def main_menu():
    keyboard = [
        [InlineKeyboardButton("❓ Soru Sor", callback_data="ask")],
        [InlineKeyboardButton("📅 Randevu Al", callback_data="appt_start")],
        [InlineKeyboardButton("👤 Danışmanla Görüş", callback_data="escalate")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def notify_owner(context, customer_chat_id, user_full_name, question):
    if not OWNER_CHAT_ID:
        return
    text = (
        f"⚠️ *YENİ DANIŞMAN TALEBİ*\n\n"
        f"*Müşteri:* {user_full_name}\n"
        f"*Chat ID:* `{customer_chat_id}`\n"
        f"*Soru / Konu:*\n{question}\n\n"
        f"Müşteriye yanıt vermek için Telegram'dan bu kişiye mesaj atabilirsiniz."
    )
    await context.bot.send_message(
        chat_id=int(OWNER_CHAT_ID),
        text=text,
        parse_mode="Markdown"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Merhaba! *İSG Danışmanlık Asistanına* hoş geldiniz.\n\n"
        "İş Sağlığı ve Güvenliği konularında size yardımcı olmaktan memnuniyet duyarım.\n\n"
        "Aşağıdaki menüden seçim yapabilir veya doğrudan sorunuzu yazabilirsiniz:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text
    state = context.user_data.get("state")

    # --- Randevu akışı ---
    if state == "appt_name":
        context.user_data["appt_name"] = user_message
        context.user_data["state"] = "appt_phone"
        await update.message.reply_text("Telefon numaranızı paylaşır mısınız?")
        return

    if state == "appt_phone":
        context.user_data["appt_phone"] = user_message
        context.user_data["state"] = "appt_date"
        await update.message.reply_text(
            "Randevu için tercih ettiğiniz tarih ve saati belirtin (örn: 15 Mayıs öğleden sonra):"
        )
        return

    if state == "appt_date":
        context.user_data["appt_date"] = user_message
        context.user_data["state"] = "appt_topic"
        await update.message.reply_text(
            "Görüşmek istediğiniz konu nedir? (Kısaca belirtin):"
        )
        return

    if state == "appt_topic":
        name = context.user_data.get("appt_name")
        phone = context.user_data.get("appt_phone")
        date = context.user_data.get("appt_date")
        topic = user_message
        save_appointment(chat_id, name, phone, date, topic)
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ *Randevu talebiniz alındı.*\n\n"
            f"Ad Soyad: {name}\n"
            f"Telefon: {phone}\n"
            f"Tarih: {date}\n"
            f"Konu: {topic}\n\n"
            f"Danışmanımız en kısa sürede sizi arayacaktır.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        await notify_owner(
            context, chat_id, name,
            f"RANDEVU TALEBİ\nTelefon: {phone}\nTarih: {date}\nKonu: {topic}"
        )
        return

    # --- İletişim formu akışı ---
    if state == "contact_name":
        context.user_data["contact_name"] = user_message
        context.user_data["state"] = "contact_phone"
        await update.message.reply_text("Telefon numaranızı paylaşır mısınız?")
        return

    if state == "contact_phone":
        context.user_data["contact_phone"] = user_message
        context.user_data["state"] = "contact_message"
        await update.message.reply_text("İletmek istediğiniz mesajı veya soruyu yazabilirsiniz:")
        return

    if state == "contact_message":
        name = context.user_data.get("contact_name")
        phone = context.user_data.get("contact_phone")
        message = user_message
        save_contact(chat_id, name, phone, message)
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ *Mesajınız iletildi.*\n\n"
            f"Ad Soyad: {name}\n"
            f"Telefon: {phone}\n\n"
            f"Danışmanımız en kısa sürede sizinle iletişime geçecektir.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        await notify_owner(
            context, chat_id, name,
            f"İLETİŞİM FORMU\nTelefon: {phone}\nMesaj: {message}"
        )
        return

    # --- Normal soru-cevap ---
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    save_message(chat_id, "user", user_message)

    try:
        response = ask_claude(chat_id, user_message)
    except Exception as e:
        logger.error(f"Claude error: {e}")
        response = "Şu an teknik bir sorun yaşıyoruz. Lütfen daha sonra tekrar deneyin veya danışmanımızla iletişime geçin."

    save_message(chat_id, "assistant", response)

    needs_escalation = "danışmanımızı devreye alıyorum" in response.lower()

    await update.message.reply_text(response, reply_markup=main_menu())

    if needs_escalation:
        full_name = update.effective_user.full_name
        await notify_owner(context, chat_id, full_name, user_message)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "ask":
        await query.message.reply_text(
            "Lütfen İSG ile ilgili sorunuzu yazın, size yardımcı olmaktan memnuniyet duyarım:"
        )

    elif data == "appt_start":
        context.user_data.clear()
        context.user_data["state"] = "appt_name"
        await query.message.reply_text(
            "Randevu talebinizi almaktan memnuniyet duyarız.\n\nLütfen adınızı ve soyadınızı yazın:"
        )

    elif data == "contact_start":
        context.user_data.clear()
        context.user_data["state"] = "contact_name"
        await query.message.reply_text(
            "İletişim formunu doldurmaya başlayalım.\n\nLütfen adınızı ve soyadınızı yazın:"
        )

    elif data == "escalate":
        chat_id = query.from_user.id
        full_name = query.from_user.full_name
        await query.message.reply_text(
            "Danışman talebiniz alındı. En kısa sürede sizinle iletişime geçilecektir.\n\n"
            "Lütfen bekleyiniz, teşekkür ederiz."
        )
        await notify_owner(context, chat_id, full_name, "Doğrudan danışman görüşme talebi")


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot başlatılıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()

