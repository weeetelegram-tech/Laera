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

# --- 2. كود البوت مع LiraScope API وتقسيم الأزرار ---
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
        [InlineKeyboardButton("💱 أسعار العملات", callback_data="sec_currencies", style="success")],
        [InlineKeyboardButton("🟡 أسعار الذهب والمعادن", callback_data="sec_gold", style="success")],
        [InlineKeyboardButton("⛽ أسعار المحروقات", callback_data="sec_fuels", style="success")],
        [InlineKeyboardButton("🪙 العملات الرقمية", callback_data="sec_crypto", style="success")],
        [InlineKeyboardButton("💵 تحويل من دولار إلى ليرة سورية", callback_data="set_to_syp", style="primary")],
        [InlineKeyboardButton("🇸🇾 تحويل من ليرة سورية إلى دولار", callback_data="set_to_usd", style="danger")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "مرحباً بك في بوت أسعار الصرف والتحديثات الفورية (عبر LiraScope).\n"
        "• اختر القسم المطلوبة للاطلاع على أسعاره أو متابعتها.\n"
        "• أو اختر نوع التحويل ثم **اكتب الرقم والكمية مباشرة في الدردشة** لتحويلها بدقة!",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "sec_currencies":
        rates_data = get_exchange_data()
        text = "💱 **قسـم العملات:**\n\n"
        has_data = False
        if rates_data:
            if "marketRates" in rates_data and rates_data["marketRates"]:
                has_data = True
                text += "🔸 *أسعار السوق السوداء:*\n"
                for item in rates_data["marketRates"]:
                    text += f"• **{item.get('currency')}**: الوسطي ({item.get('mid')}) | بيع: {item.get('sell')} | شراء: {item.get('buy')}\n"
            if "cbsRates" in rates_data and rates_data["cbsRates"]:
                has_data = True
                text += "\n🔸 *أسعار المصرف المركزي:*\n"
                for item in rates_data["cbsRates"]:
                    text += f"• **{item.get('currency')}**: {item.get('mid')}\n"
        if not has_data:
            text += "❌ لا توجد بيانات عملات متاحة حالياً."
            
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main", style="danger")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "sec_gold":
        gold_data = get_gold_data()
        text = "🟡 **قسـم الذهب والمعادن:**\n\n"
        has_data = False
        if gold_data:
            # معالجة استجابة الذهب بناءً على توثيق API (سواء كانت قائمة أو كائن)
            g_list = gold_data.get("rates", gold_data) if isinstance(gold_data, dict) else gold_data
            if isinstance(g_list, list):
                has_data = True
                for g in g_list:
                    text += f"• **{g.get('currency', 'الذهب')}**: الوسطي: {g.get('mid', '-')} | بيع: {g.get('sell', '-')} | شراء: {g.get('buy', '-')}\n"
            elif isinstance(g_list, dict):
                has_data = True
                for g_key, g_val in g_list.items():
                    if isinstance(g_val, dict):
                        text += f"• **{g_key}**: الوسطي: {g_val.get('mid', '-')}\n"
        if not has_data:
            text += "❌ لا توجد بيانات ذهب أو معادن متاحة حالياً في الـ API."
            
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main", style="danger")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "sec_fuels":
        rates_data = get_exchange_data()
        text = "⛽ **قسـم المحروقات:**\n\n"
        has_fuels = False
        fuel_keywords = ["بنزين", "مازوت", "غاز", "fuel", "gasoline", "diesel"]
        
        all_items = []
        if rates_data:
            if "marketRates" in rates_data:
                all_items.extend(rates_data["marketRates"])
            if "cbsRates" in rates_data:
                all_items.extend(rates_data["cbsRates"])
                
        for item in all_items:
            curr_str = str(item.get("currency", "")).lower()
            if any(kw in curr_str for kw in fuel_keywords):
                has_fuels = True
                text += f"• **{item.get('currency')}**: الوسطي ({item.get('mid')}) | بيع: {item.get('sell')} | شراء: {item.get('buy')}\n"
                
        if not has_fuels:
            text += "❌ بيانات المحروقات غير متوفرة في الـ API الحالي حالياً."
            
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main", style="danger")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "sec_crypto":
        crypto_data = get_crypto_data()
        text = "🪙 **قسـم العملات الرقمية:**\n\n"
        has_data = False
        if crypto_data:
            c_list = crypto_data.get("rates", crypto_data) if isinstance(crypto_data, dict) else crypto_data
            if isinstance(c_list, list):
                has_data = True
                for c in c_list:
                    text += f"• **{c.get('currency', '')}**: السعر: {c.get('mid', c.get('buy', ''))}\n"
            elif isinstance(c_list, dict):
                has_data = True
                for c_key, c_val in c_list.items():
                    if isinstance(c_val, dict):
                        text += f"• **{c_key}**: {c_val.get('mid', '')}\n"
        if not has_data:
            text += "❌ لا توجد بيانات عملات رقمية متاحة حالياً."
            
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main", style="danger")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            
    elif data == "set_to_syp":
        user_states[user_id] = "to_syp"
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main", style="danger")]]
        await query.edit_message_text(
            "💵 لقد اخترت التحويل من **الدولار إلى الليرة السورية**.\n\n"
            "الآن أرسل لي الرقم أو الكمية بالدولار (مثال: `50` أو `100`):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "set_to_usd":
        user_states[user_id] = "to_usd"
        keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main", style="danger")]]
        await query.edit_message_text(
            "🇸🇾 لقد اخترت التحويل من **الليرة السورية إلى الدولار**.\n\n"
            "الآن أرسل لي المبلغ بالليرة السورية (مثال: `500000`):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "back_main":
        user_states.pop(user_id, None)
        keyboard = [
            [InlineKeyboardButton("💱 أسعار العملات", callback_data="sec_currencies", style="success")],
            [InlineKeyboardButton("🟡 أسعار الذهب والمعادن", callback_data="sec_gold", style="success")],
            [InlineKeyboardButton("⛽ أسعار المحروقات", callback_data="sec_fuels", style="success")],
            [InlineKeyboardButton("🪙 العملات الرقمية", callback_data="sec_crypto", style="success")],
            [InlineKeyboardButton("💵 تحويل من دولار إلى ليرة سورية", callback_data="set_to_syp", style="primary")],
            [InlineKeyboardButton("🇸🇾 تحويل من ليرة سورية إلى دولار", callback_data="set_to_usd", style="danger")]
        ]
        await query.edit_message_text("اختر ما تحتاجه من القائمة الرئيسية:", reply_markup=InlineKeyboardMarkup(keyboard))

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
    target_items = ["USD", "بنزين", "مازوت", "غاز"]
    
    while True:
        await asyncio.sleep(60)
        rates_data = get_exchange_data()
        if rates_data and "marketRates" in rates_data:
            for item in rates_data["marketRates"]:
                curr = item.get("currency")
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
