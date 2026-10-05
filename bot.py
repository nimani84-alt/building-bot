import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

# -------------------------------------------------------------
# ۱. تنظیم توکن ربات تلگرام
# -------------------------------------------------------------
BOT_TOKEN = "توکن_ربات_را_اینجا_قرار_دهید"

# وضعیت‌های گفتگو (Conversation States)
UNIT_NUM, UNIT_AREA, UNIT_OCC = range(3)
EXP_TITLE, EXP_AMOUNT, EXP_METHOD = range(3, 6)
PAY_UNIT, PAY_AMOUNT = range(6, 8)

# -------------------------------------------------------------
# ۲. راه‌اندازی پایگاه‌داده داخلی (SQLite)
# -------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("building.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, num TEXT, area REAL, occ INTEGER, paid REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expenses 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, amount REAL, method TEXT)''')
    conn.commit()
    conn.close()

# منوی اصلی شیشه‌ای
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ تعریف واحد جدید", callback_data="add_unit"),
         InlineKeyboardButton("🧾 ثبت فاکتور هزینه", callback_data="add_expense")],
        [InlineKeyboardButton("💳 ثبت واریزی شارژ", callback_data="add_payment"),
         InlineKeyboardButton("📋 لیست واحدها و مانده", callback_data="list_units")],
        [InlineKeyboardButton("📊 گزارش مالی ساختمان", callback_data="report_all")]
    ]
    return InlineKeyboardMarkup(keyboard)

# تابع کمکی برای تبدیل اعداد به فارسی
def to_persian(number):
    if number is None:
        return "۰"
    en_str = f"{int(round(number)):,}"
    translation = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹،")
    return en_str.translate(translation)

# محاسبات سهم و تسهیم
def get_calculations():
    conn = sqlite3.connect("building.db")
    c = conn.cursor()
    c.execute("SELECT id, num, area, occ, paid FROM units")
    units = c.fetchall()
    c.execute("SELECT title, amount, method FROM expenses")
    expenses = c.fetchall()
    conn.close()

    total_exp = sum(e[1] for e in expenses)
    total_area = sum(u[2] for u in units) or 1
    total_occ = sum(u[3] for u in units) or 1
    unit_count = len(units) or 1

    unit_results = []
    for u in units:
        u_id, u_num, u_area, u_occ, u_paid = u
        share = 0
        for exp in expenses:
            _, e_amt, e_meth = exp
            if e_meth == 'area':
                share += (e_amt / total_area) * u_area
            elif e_meth == 'occ':
                share += (e_amt / total_occ) * u_occ
            else:
                share += e_amt / unit_count
        bal = round(share) - u_paid
        unit_results.append({
            "id": u_id, "num": u_num, "area": u_area, "occ": u_occ,
            "share": round(share), "paid": u_paid, "bal": bal
        })

    return unit_results, total_exp

# -------------------------------------------------------------
# ۳. هندلرهای عمومی
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    text = "🏢 **سامانه مدیریت شارژ ساختمان**\n\nجهت مدیریت امور مالی ساختمان، یکی از گزینه‌های زیر را انتخاب نمایید:"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")

# -------------------------------------------------------------
# ۴. فرآیند تعریف واحد جدید
# -------------------------------------------------------------
async def add_unit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🔹 شماره واحد را وارد فرمایید (مثال: ۱۰۱):")
    return UNIT_NUM

async def add_unit_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['u_num'] = update.message.text.strip()
    await update.message.reply_text("🔹 متراژ واحد را به عدد وارد فرمایید (مثال: ۸۵):")
    return UNIT_AREA

async def add_unit_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['u_area'] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً متراژ را به صورت عدد لاتین وارد کنید (مثال: 85):")
        return UNIT_AREA
    await update.message.reply_text("🔹 تعداد ساکنین واحد را وارد فرمایید (مثال: ۳):")
    return UNIT_OCC

async def add_unit_occ(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        occ = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً تعداد نفرات را به عدد لاتین وارد کنید (مثال: 3):")
        return UNIT_OCC

    conn = sqlite3.connect("building.db")
    c = conn.cursor()
    c.execute("INSERT INTO units (num, area, occ) VALUES (?, ?, ?)",
              (context.user_data['u_num'], context.user_data['u_area'], occ))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ واحد {context.user_data['u_num']} با موفقیت ذخیره شد.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# -------------------------------------------------------------
# ۵. فرآیند ثبت فاکتور هزینه
# -------------------------------------------------------------
async def add_exp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🔹 شرح فاکتور را وارد فرمایید (مثال: قبوض موتورخانه، نظافت مشاعات):")
    return EXP_TITLE

async def add_exp_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['e_title'] = update.message.text.strip()
    await update.message.reply_text("🔹 مبلغ کل هزینه را به ریال وارد نمایید (مثال: ۲۵۰۰۰۰۰۰):")
    return EXP_AMOUNT

async def add_exp_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw_val = update.message.text.strip().replace(",", "")
        context.user_data['e_amount'] = float(raw_val)
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً مبلغ را به عدد صحیح وارد فرمایید:")
        return EXP_AMOUNT

    kb = [
        [InlineKeyboardButton("تقسیم مساوی بین همه واحدها", callback_data="exp_equal")],
        [InlineKeyboardButton("تسهیم بر اساس متراژ واحدها", callback_data="exp_area")],
        [InlineKeyboardButton("تسهیم بر اساس تعداد نفرات", callback_data="exp_occ")]
    ]
    await update.message.reply_text("نحوه تقسیم این هزینه را تعیین فرمایید:", reply_markup=InlineKeyboardMarkup(kb))
    return EXP_METHOD

async def add_exp_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("exp_", "")

    conn = sqlite3.connect("building.db")
    c = conn.cursor()
    c.execute("INSERT INTO expenses (title, amount, method) VALUES (?, ?, ?)",
              (context.user_data['e_title'], context.user_data['e_amount'], method))
    conn.commit()
    conn.close()

    await query.message.reply_text(
        f"✅ هزینه «{context.user_data['e_title']}» به مبلغ {to_persian(context.user_data['e_amount'])} ریال ثبت شد.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# -------------------------------------------------------------
# ۶. فرآیند ثبت واریزی شارژ
# -------------------------------------------------------------
async def add_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = sqlite3.connect("building.db")
    c = conn.cursor()
    c.execute("SELECT id, num FROM units")
    units = c.fetchall()
    conn.close()

    if not units:
        await query.message.reply_text("ابتدا باید حداقل یک واحد تعریف نمایید.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    kb = [[InlineKeyboardButton(f"واحد {u[1]}", callback_data=f"payunit_{u[0]}")] for u in units]
    await query.message.reply_text("واحد واریزکننده را انتخاب نمایید:", reply_markup=InlineKeyboardMarkup(kb))
    return PAY_UNIT

async def pay_unit_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    unit_id = int(query.data.replace("payunit_", ""))
    context.user_data['pay_unit_id'] = unit_id

    conn = sqlite3.connect("building.db")
    c = conn.cursor()
    c.execute("SELECT num FROM units WHERE id = ?", (unit_id,))
    u_num = c.fetchone()[0]
    conn.close()

    context.user_data['pay_unit_num'] = u_num
    await query.message.reply_text(f"مبلغ واریز شده توسط واحد {u_num} را به ریال وارد نمایید:")
    return PAY_AMOUNT

async def pay_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw_val = update.message.text.strip().replace(",", "")
        amount = float(raw_val)
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً مبلغ را عددی وارد فرمایید:")
        return PAY_AMOUNT

    unit_id = context.user_data['pay_unit_id']
    conn = sqlite3.connect("building.db")
    c = conn.cursor()
    c.execute("UPDATE units SET paid = paid + ? WHERE id = ?", (amount, unit_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ مبلغ {to_persian(amount)} ریال واریزی برای واحد {context.user_data['pay_unit_num']} ثبت شد.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# -------------------------------------------------------------
# ۷. گزارش لیست واحدها و وضعیت تسویه
# -------------------------------------------------------------
async def list_units(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    units, _ = get_calculations()

    if not units:
        await query.message.reply_text("هیچ واحدی ثبت نشده است.", reply_markup=main_menu_keyboard())
        return

    msg = "🏢 **صورت‌حساب تفکیکی واحدها:**\n────────────────\n"
    for u in units:
        status = f"🔴 بدهی: {to_persian(u['bal'])} ریال" if u['bal'] > 0 else "🟢 تسویه شد"
        msg += f"🚪 **واحد {u['num']}** ({to_persian(u['area'])} متر | {to_persian(u['occ'])} نفر)\n"
        msg += f"▫️ سهم هزینه: {to_persian(u['share'])} ریال\n"
        msg += f"▫️ کل واریزی: {to_persian(u['paid'])} ریال\n"
        msg += f"▫️ وضعیت: {status}\n────────────────\n"

    kb = [[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_menu")]]
    await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# -------------------------------------------------------------
# ۸. گزارش جامع و تراز مالی کل ساختمان
# -------------------------------------------------------------
async def report_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    units, total_exp = get_calculations()
    total_paid = sum(u['paid'] for u in units)
    total_bal = max(0, total_exp - total_paid)

    msg = "📊 **گزارش جامع تراز مالی ساختمان**\n────────────────\n"
    msg += f"▫️ کل هزینه‌های دوره: {to_persian(total_exp)} ریال\n"
    msg += f"▫️ کل مبالغ دریافتی: {to_persian(total_paid)} ریال\n"
    msg += f"▫️ مانده کل مطالبات ساختمان: {to_persian(total_bal)} ریال\n"
    msg += f"▫️ تعداد کل واحدهای ثبت‌شده: {to_persian(len(units))}\n────────────────"

    kb = [[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_menu")]]
    await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# لغو جریان گفتگو
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات متوقف گردید.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# -------------------------------------------------------------
# ۹. تابع اصلی اجرای ربات
# -------------------------------------------------------------
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    unit_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_unit_start, pattern="^add_unit$")],
        states={
            UNIT_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_unit_num)],
            UNIT_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_unit_area)],
            UNIT_OCC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_unit_occ)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    )

    exp_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_exp_start, pattern="^add_expense$")],
        states={
            EXP_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_exp_title)],
            EXP_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_exp_amount)],
            EXP_METHOD: [CallbackQueryHandler(add_exp_method, pattern="^exp_")]
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    )

    pay_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_payment_start, pattern="^add_payment$")],
        states={
            PAY_UNIT: [CallbackQueryHandler(pay_unit_chosen, pattern="^payunit_")],
            PAY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_amount_received)]
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(unit_handler)
    app.add_handler(exp_handler)
    app.add_handler(pay_handler)
    app.add_handler(CallbackQueryHandler(list_units, pattern="^list_units$"))
    app.add_handler(CallbackQueryHandler(report_all, pattern="^report_all$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^back_menu$"))

    print("ربات فعال شد...")
    app.run_polling()

if __name__ == '__main__':
    main()
