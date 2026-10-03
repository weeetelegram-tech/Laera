import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import asyncio

# --- 1. سيرفر ويب وهمي لإرضاء منصة Render ---
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running successfully!")

    def log_message(self, format, *args):
        return  # إخفاء سجلات الـ HTTP لعدم إغراق التيرمينال

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyServer)
    server.serve_forever()

# تشغيل السيرفر الوهمي في الخيط الخلفي (Thread)
threading.Thread(target=run_dummy_server, daemon=True).start()

# --- 2. كود البوت الأصلي ---
TOKEN = os.environ.get("TOKEN", "8886929977:AAE41PCPX6zlxZrrERIKtWz31pH4fmR07ys")
API_URL = "https://liranews.info/api/public/v1/price/usdsypd"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

active_users = set()
last_known_price = None
user_states = {}

def get_exchange_data():
    try:
        response = requests.get(API_URL, timeout=10)
        data = response.json()
        price_info = data.get("usdsypd", {})
        return {
            "value": price_info.get("value"),
            "sell": price_info.get("sell"),
            "buy": price_info.get("buy")
        }
    except Exception as e:
        logger.error(f"خطأ في جلب السعر: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_users.add(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💱 أسعار البيع والشراء الحالية", callback_data="get_prices")],
        [InlineKeyboardButton("💵 تحويل من دولار إلى ليرة سورية", callback_data="set_to_syp")],
        [InlineKeyboardButton("🇸🇾 تحويل من ليرة سورية إلى دولار", callback_data="set_to_usd")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "مرحباً بك في بوت أسعار الصرف والتحديثات الفورية.\n"
        "• يمكنك الضغط على الأسعار لمتابعتها.\n"
        "• أو اختر نوع التحويل ثم **اكتب الرقم والكمية مباشرة في الدردشة** لتحويلها بدقة!",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "get_prices":
        rates = get_exchange_data()
        if rates:
            text = (
                f"📊 **أسعار صرف الدولار مقابل الليرة:**\n\n"
                f"🔹 السعر الوسطي: **{rates['value']}**\n"
                f"🔴 سعر البيع: **{rates['sell']}**\n"
                f"🟢 سعر الشراء: **{rates['buy']}**"
            )
        else:
            text = "❌ تعذر جلب الأسعار حالياً، حاول لاحقاً."
            
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            
    elif data == "set_to_syp":
        user_states[user_id] = "to_syp"
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")]]
        await query.edit_message_text(
            "💵 لقد اخترت التحويل من **الدولار إلى الليرة السورية**.\n\n"
            "الآن أرسل لي الرقم أو الكمية بالدولار (مثال: `50` أو `100`):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "set_to_usd":
        user_states[user_id] = "to_usd"
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")]]
        await query.edit_message_text(
            "🇸🇾 لقد اخترت التحويل من **الليرة السورية إلى الدولار**.\n\n"
            "الآن أرسل لي المبلغ بالليرة السورية (مثال: `500000`):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "back_main":
        user_states.pop(user_id, None)
        keyboard = [
            [InlineKeyboardButton("💱 أسعار البيع والشراء الحالية", callback_data="get_prices")],
            [InlineKeyboardButton("💵 تحويل من دولار إلى ليرة سورية", callback_data="set_to_syp")],
            [InlineKeyboardButton("🇸🇾 تحويل من ليرة سورية إلى دولار", callback_data="set_to_usd")]
        ]
        await query.edit_message_text("اختر ما تحتاجه:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id not in user_states:
        await update.message.reply_text("الرجاء استخدام الأوامر أو الضغط على أزرار القائمة الرئيسية للبدء /start أولاً.")
        return
        
    try:
        clean_text = text.replace(",", "").replace(" ", "")
        amount = float(clean_text)
    except ValueError:
        await update.message.reply_text("❌ يرجى إرسال رقم صحيح فقط (مثال: 100 أو 50000).")
        return
        
    rates = get_exchange_data()
    if not rates or not rates.get("sell") or not rates.get("buy"):
        await update.message.reply_text("❌ تعذر جلب أسعار الصرف الحالية من الخادم.")
        return
        
    sell_price = rates["sell"]
    buy_price = rates["buy"]
    state = user_states[user_id]
    
    if state == "to_syp":
        res_sell = amount * sell_price
        res_buy = amount * buy_price
        await update.message.reply_text(
            f"💵 نتيجة تحويل **{amount:,.2f} $**:\n\n"
            f"🔴 على أساس سعر البيع ({sell_price}): **{res_sell:,.2f} ل.س**\n"
            f"🟢 على أساس سعر الشراء ({buy_price}): **{res_buy:,.2f} ل.س**",
            parse_mode="Markdown"
        )
    elif state == "to_usd":
        res_sell = amount / sell_price if sell_price > 0 else 0
        res_buy = amount / buy_price if buy_price > 0 else 0
        await update.message.reply_text(
            f"🇸🇾 نتيجة تحويل **{amount:,.2f} ل.س**:\n\n"
            f"🔴 على أساس سعر البيع: **{res_sell:,.2f} $**\n"
            f"🟢 على أساس سعر الشراء: **{res_buy:,.2f} $**",
            parse_mode="Markdown"
        )

async def check_price_changes(app: Application):
    global last_known_price
    while True:
        await asyncio.sleep(60)
        rates = get_exchange_data()
        if rates and rates.get("value"):
            current_price = rates["value"]
            if last_known_price is None:
                last_known_price = current_price
            elif current_price != last_known_price:
                diff = current_price - last_known_price
                direction = "📈 ارتفاع" if diff > 0 else "📉 انخفاض"
                
                message = (
                    f"⚠️ **تنبيه تغير سعر الصرف!**\n\n"
                    f"{direction} في السعر\n"
                    f"🔹 السعر الحالي: **{current_price}**\n"
                    f"🔴 البيع: {rates['sell']} | 🟢 الشراء: {rates['buy']}"
                )
                
                for user_id in active_users:
                    try:
                        await app.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"خطأ في إرسال الإشعار للمستخدم {user_id}: {e}")
                
                last_known_price = current_price

async def post_init(application: Application):
    asyncio.create_task(check_price_changes(application))

def main():
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
