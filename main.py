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

# --- 2. كود البوت مع LiraScope API الجديد ---
TOKEN = os.environ.get("TOKEN", "8886929977:AAHPBrqjqk9GtD0LzCEZtqp0y1fjvDndWG4")
API_BASE = "https://lirascope.syria-cloud.sy/api/v1"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

active_users = set()
last_known_prices = {}  # لتتبع أسعار العناصر المخصصة للتنبيه فقط
user_states = {}

def get_exchange_data():
    try:
        response = requests.get(f"{API_BASE}/rates/latest?lang=ar", timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"خطأ في جلب الأسعار: {e}")
        return None

def get_gold_data():
    try:
        response = requests.get(f"{API_BASE}/gold/latest?lang=ar", timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"خطأ في جلب الذهب: {e}")
        return None

def get_crypto_data():
    try:
        response = requests.get(f"{API_BASE}/crypto/latest?lang=ar", timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"خطأ في جلب العملات الرقمية: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_users.add(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💱 أسعار العملات والذهب الحالية", callback_data="get_prices", style="success")],
        [InlineKeyboardButton("💵 تحويل من دولار إلى ليرة سورية", callback_data="set_to_syp", style="primary")],
        [InlineKeyboardButton("🇸🇾 تحويل من ليرة سورية إلى دولار", callback_data="set_to_usd", style="danger")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "مرحباً بك في بوت أسعار الصرف والتحديثات الفورية (عبر LiraScope).\n"
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
        rates_data = get_exchange_data()
        gold_data = get_gold_data()
        crypto_data = get_crypto_data()
        
        text = "📊 **أسعار الصرف، العملات والذهب الحالية:**\n\n"
        
        # جلب أسعار السوق (Market Rates)
        if rates_data and "marketRates" in rates_data:
            text += "🌐 **أسعار السوق:**\n"
            for item in rates_data["marketRates"]:
                curr = item.get("currency")
                mid = item.get("mid")
                buy = item.get("buy")
                sell = item.get("sell")
                text += f"🔹 **{curr}**: الوسطي ({mid}) | 🔴 بيع: {sell} | 🟢 شراء: {buy}\n"
            text += "\n"
            
        # جلب أسعار المصرف المركزي (CBS Rates)
        if rates_data and "cbsRates" in rates_data and rates_data["cbsRates"]:
            text += "🏦 **أسعار المصرف المركزي:**\n"
            for item in rates_data["cbsRates"]:
                curr = item.get("currency")
                mid = item.get("mid")
                text += f"🔹 **{curr}**: {mid}\n"
            text += "\n"

        # جلب الذهب إن وجد
        if gold_data:
            text += "🟡 **أسعار الذهب:**\n"
            if isinstance(gold_data, list):
                for g in gold_data:
                    text += f"🔸 {g.get('currency', 'الذهب')}: السعر {g.get('mid', g.get('buy', ''))}\n"
            elif isinstance(gold_data, dict):
                for g_key, g_val in gold_data.items():
                    if isinstance(g_val, dict):
                        text += f"🔸 {g_key}: السعر {g_val.get('mid', g_val.get('buy', ''))}\n"
            text += "\n"

        # جلب العملات الرقمية إن وجدت
        if crypto_data:
            text += "🪙 **العملات الرقمية:**\n"
            if isinstance(crypto_data, list):
                for c in crypto_data:
                    text += f"🔹 {c.get('currency', '')}: {c.get('mid', '')}\n"
            elif isinstance(crypto_data, dict):
                for c_key, c_val in crypto_data.items():
                    if isinstance(c_val, dict):
                        text += f"🔹 {c_key}: {c_val.get('mid', '')}\n"
                        
        if not rates_data and not gold_data:
            text = "❌ تعذر جلب الأسعار حالياً، حاول لاحقاً."
            
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main", style="danger")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            
    elif data == "set_to_syp":
        user_states[user_id] = "to_syp"
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main", style="danger")]]
        await query.edit_message_text(
            "💵 لقد اخترت التحويل من **الدولار إلى الليرة السورية**.\n\n"
            "الآن أرسل لي الرقم أو الكمية بالدولار (مثال: `50` أو `100`):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "set_to_usd":
        user_states[user_id] = "to_usd"
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main", style="danger")]]
        await query.edit_message_text(
            "🇸🇾 لقد اخترت التحويل من **الليرة السورية إلى الدولار**.\n\n"
            "الآن أرسل لي المبلغ بالليرة السورية (مثال: `500000`):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "back_main":
        user_states.pop(user_id, None)
        keyboard = [
            [InlineKeyboardButton("💱 أسعار العملات والذهب الحالية", callback_data="get_prices", style="success")],
            [InlineKeyboardButton("💵 تحويل من دولار إلى ليرة سورية", callback_data="set_to_syp", style="primary")],
            [InlineKeyboardButton("🇸🇾 تحويل من ليرة سورية إلى دولار", callback_data="set_to_usd", style="danger")]
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
        
    rates_data = get_exchange_data()
    if not rates_data or "marketRates" not in rates_data:
        await update.message.reply_text("❌ تعذر جلب أسعار الصرف الحالية من الخادم.")
        return
        
    # استخراج سعر الدولار الأساسي للتحويل
    usd_rate = None
    for item in rates_data["marketRates"]:
        if item.get("currency") == "USD":
            usd_rate = item
            break
            
    if not usd_rate:
        await update.message.reply_text("❌ تعذر العثور على سعر صرف الدولار حالياً.")
        return
        
    sell_price = float(usd_rate.get("sell", 0))
    buy_price = float(usd_rate.get("buy", 0))
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
            f"🔴 على أساس سعر البيع ({sell_price}): **{res_sell:,.2f} $**\n"
            f"🟢 على أساس سعر الشراء ({buy_price}): **{res_buy:,.2f} $**",
            parse_mode="Markdown"
        )

async def check_price_changes(app: Application):
    global last_known_prices
    # العناصر المستهدفة فقط للإشعارات والتنبيهات
    target_items = ["USD", "بنزين", "مازوت", "غاز"]
    
    while True:
        await asyncio.sleep(60)
        rates_data = get_exchange_data()
        if rates_data and "marketRates" in rates_data:
            for item in rates_data["marketRates"]:
                curr = item.get("currency")
                # التحقق إذا كانت العنصر من ضمن القائمة المستهدفة (دولار أو مشتقات نفطية إن وجدت بالـ API)
                if curr in target_items or any(t in str(curr).lower() for t in target_items):
                    current_price = item.get("mid", item.get("value"))
                    if current_price is not None:
                        if curr not in last_known_prices:
                            last_known_prices[curr] = current_price
                        elif current_price != last_known_prices[curr]:
                            diff = current_price - last_known_prices[curr]
                            direction = "📈 ارتفاع" if diff > 0 else "📉 انخفاض"
                            
                            message = (
                                f"⚠️ **تنبيه تغير سعر {curr}!**\n\n"
                                f"{direction} في السعر\n"
                                f"🔹 السعر الحالي: **{current_price}**\n"
                                f"🔴 البيع: {item.get('sell')} | 🟢 الشراء: {item.get('buy')}"
                            )
                            
                            for user_id in active_users:
                                try:
                                    await app.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                                except Exception as e:
                                    logger.error(f"خطأ في إرسال الإشعار للمستخدم {user_id}: {e}")
                            
                            last_known_prices[curr] = current_price

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
