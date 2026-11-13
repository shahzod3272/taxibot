import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# TOKENni o'zingizning bot tokeningizga almashtiring
TOKEN = "9009245143:AAFUPCxK636Fn766dFxhezIlGugL1XnLzDE"

# Adminning Telegram ID raqami
ADMIN_ID = 1145699643

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# --- SQLITE BAZASINI YARATISH VA ULANISH ---
conn = sqlite3.connect("taksi_bot.db", check_same_thread=False)
cursor = conn.cursor()

# Haydovchilar jadvali
cursor.execute("""
CREATE TABLE IF NOT EXISTS drivers (
    driver_id INTEGER PRIMARY KEY,
    name TEXT,
    car TEXT,
    number TEXT,
    phone TEXT,
    status TEXT,
    paid_until TEXT,
    last_work_date TEXT,
    missed_counts TEXT,
    reject_counts TEXT
)
""")

# Yo'lovchilar jadvali (raqamini eslab qolish uchun)
cursor.execute("""
CREATE TABLE IF NOT EXISTS passengers (
    passenger_id INTEGER PRIMARY KEY,
    phone TEXT
)
""")
conn.commit()

try:
    cursor.execute("ALTER TABLE drivers ADD COLUMN reject_counts TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

# Tushunarli va belgilangan yo'nalishlar
DIR_1 = "🏡 11-SAVXOZ ➡️ DO'STLIK"
DIR_2 = "🏙 DO'STLIK ➡️ 11-SAVXOZ"

drivers_queues = {
    DIR_1: [],
    DIR_2: []
}
active_orders = {}       
pending_orders = {}      


# --- HOLATLAR (FSM) ---
class PassengerState(StatesGroup):
    waiting_for_direction = State()
    waiting_for_passengers = State()
    waiting_for_phone = State()


class DriverRegState(StatesGroup):
    waiting_for_car_name = State()
    waiting_for_car_number = State()
    waiting_for_name = State()
    waiting_for_phone = State()


class DriverState(StatesGroup):
    waiting_for_direction = State()


class FeedbackState(StatesGroup):
    waiting_for_feedback = State()


# --- ASOSIY MENYU ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 YO'LOVCHI"), KeyboardButton(text="🚗 HAYDOVCHI")],
            [KeyboardButton(text="💬 Taklif va Shikoyatlar")],
        ],
        resize_keyboard=True,
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Assalomu alaykum! **TAKSI11** tezkor taksi botiga xush kelibsiz. 🚗\n\n"
        "👇 **Iltimos, o'zingizga kerakli tugmani tanlang:**",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


# ==========================================
#              ADMIN BUYRUQLARI
# ==========================================

@router.message(Command("kuni_oz"))
async def admin_low_balance_drivers(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT driver_id, name, car, number, phone, paid_until FROM drivers WHERE status = 'approved'")
    rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 Bazada tasdiqlangan haydovchilar yo'q.")
        return

    now = datetime.now()
    text = "⚠️ **Muddati tugashiga 1 kun yoki undan kam qolgan haydovchilar:**\n\n"
    found = False

    for row in rows:
        d_id, name, car, number, phone, paid_until_str = row
        if not paid_until_str:
            continue
        
        paid_until = datetime.fromisoformat(paid_until_str)
        remaining_time = paid_until - now
        
        if remaining_time <= timedelta(days=1):
            found = True
            left_hours = int(remaining_time.total_seconds() // 3600)
            if left_hours < 0:
                left_str = "⚠️ Muddati tugagan!"
            else:
                left_str = f"⏳ Qoldi: ~{left_hours} soat"

            p_clean = phone.strip()
            if not p_clean.startswith("+"):
                p_clean = "+" + p_clean

            text += (
                f"👤 **Ism:** {name}\n"
                f"🆔 ID: `{d_id}`\n"
                f"🚗 Mashina: {car} ({number})\n"
                f"📞 Tel: [{phone}](tel:{p_clean})\n"
                f"⏱ Holat: {left_str}\n"
                f"-----------------------------------\n"
            )

    if not found:
        await message.answer("✅ Hozirda 1 kuni qolgan haydovchilar yo'q. Hammaning vaqti yetarlicha.")
    else:
        await message.answer(text, parse_mode="Markdown")


@router.message(Command("uzaytirish"))
async def admin_extend_driver(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("⚠️ Noto'g'ri format!\nIshlatish: `/uzaytirish HAYDOVCHI_ID KUN_SONI`", parse_mode="Markdown")
        return

    try:
        driver_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await message.answer("❌ ID va kunlar faqat raqamlardan iborat bo'lishi kerak!")
        return

    cursor.execute("SELECT paid_until FROM drivers WHERE driver_id = ?", (driver_id,))
    row = cursor.fetchone()
    if not row:
        await message.answer("❌ Bu ID raqamdagi haydovchi bazadan topilmadi!")
        return

    current_paid_until_str = row[0]
    current_paid_until = datetime.fromisoformat(current_paid_until_str) if current_paid_until_str else None

    if current_paid_until and current_paid_until > datetime.now():
        new_paid_until = current_paid_until + timedelta(days=days)
    else:
        new_paid_until = datetime.now() + timedelta(days=days)

    new_paid_str = new_paid_until.isoformat()
    cursor.execute("UPDATE drivers SET paid_until = ? WHERE driver_id = ?", (new_paid_str, driver_id))
    conn.commit()

    date_str = new_paid_until.strftime("%d.%m.%Y %H:%M")
    await message.answer(f"✅ Haydovchi (ID: `{driver_id}`) uchun muddat **{days} kunga** uzaytirildi!\n📅 Yangi muddat: {date_str}", parse_mode="Markdown")

    try:
        await bot.send_message(
            driver_id,
            f"🎉 **Tabriklaymiz!** Muddatigiz **{days} kunga** uzaytirildi.\n📅 Amal qilish muddati: {date_str}",
            parse_mode="Markdown"
        )
    except:
        pass


@router.message(Command("hammaga"))
async def admin_extend_all_drivers(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("⚠️ Noto'g'ri format!\nIshlatish: `/hammaga KUN_SONI`", parse_mode="Markdown")
        return

    try:
        days = int(parts[1])
    except ValueError:
        await message.answer("❌ Kunlar soni faqat raqamlardan iborat bo'lishi kerak!")
        return

    cursor.execute("SELECT driver_id, paid_until FROM drivers WHERE status = 'approved'")
    rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 Bazada tasdiqlangan haydovchilar topilmadi.")
        return

    count = 0
    for row in rows:
        d_id, paid_until_str = row
        current_paid_until = datetime.fromisoformat(paid_until_str) if paid_until_str else None

        if current_paid_until and current_paid_until > datetime.now():
            new_paid_until = current_paid_until + timedelta(days=days)
        else:
            new_paid_until = datetime.now() + timedelta(days=days)

        new_paid_str = new_paid_until.isoformat()
        cursor.execute("UPDATE drivers SET paid_until = ? WHERE driver_id = ?", (new_paid_str, d_id))
        conn.commit()
        count += 1

        date_str = new_paid_until.strftime("%d.%m.%Y %H:%M")
        try:
            await bot.send_message(
                d_id,
                f"🎉 **Ajoyib yangilik!** Admin tomonidan barcha haydovchilarga **{days} kun** qo'shib berildi.\n📅 Yangi muddat: {date_str}",
                parse_mode="Markdown"
            )
        except:
            pass

    await message.answer(f"✅ Jami **{count} ta** tasdiqlangan haydovchiga **{days} kundan** muddat qo'shildi!", parse_mode="Markdown")


@router.message(Command("haydovchilar"))
async def admin_driver_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    cursor.execute("SELECT driver_id, name, car, number, phone, status, paid_until FROM drivers")
    rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 Hozircha bazada haydovchilar yo'q.")
        return
    
    text = "🚗 **Barcha haydovchilar ro'yxati va holati:**\n\n"
    for row in rows:
        d_id, name, car, number, phone, status, paid_until_str = row
        paid_until = datetime.fromisoformat(paid_until_str) if paid_until_str else None
        
        if paid_until:
            left_days = (paid_until - datetime.now()).days
            left_str = f"⏳ {left_days} kun qoldi" if left_days >= 0 else "⚠️ Muddati tugagan!"
        else:
            left_str = "Hali faollashmagan"
            
        p_clean = phone.strip() if phone else ""
        if p_clean and not p_clean.startswith("+"):
            p_clean = "+" + p_clean

        text += (
            f"👤 **Ism:** {name}\n"
            f"🆔 ID: `{d_id}`\n"
            f"🚗 Mashina: {car} ({number})\n"
            f"📞 Tel: [{phone}](tel:{p_clean})\n"
            f"📊 Holati: {status} | Muddat: {left_str}\n"
            f"-----------------------------------\n"
        )
    await message.answer(text, parse_mode="Markdown")


# ==========================================
#      TAKLIF VA SHIKOYATLAR
# ==========================================

@router.message(F.text == "💬 Taklif va Shikoyatlar")
async def feedback_start(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Asosiy menyu")]],
        resize_keyboard=True,
    )
    await message.answer("✍️ Taklif yoki shikoyatingizni yozib yuboring:", reply_markup=keyboard)
    await state.set_state(FeedbackState.waiting_for_feedback)


@router.message(FeedbackState.waiting_for_feedback, F.text == "🏠 Asosiy menyu")
async def feedback_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(FeedbackState.waiting_for_feedback)
async def feedback_get(message: Message, state: FSMContext):
    user_text = message.text
    user = message.from_user
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📩 **Yangi murojaat!**\n👤 Kimdan: {user.full_name}\n📝 Xabar:\n{user_text}"
        )
    except:
        pass
    await state.clear()
    await message.answer("✅ Xabaringiz adminga yuborildi!", reply_markup=main_menu())


# ==========================================
#              YO'LOVCHI QISMI
# ==========================================

@router.message(F.text == "👤 YO'LOVCHI")
async def passenger_start(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=DIR_1)],
            [KeyboardButton(text=DIR_2)],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("📍 Iltimos, o'zingizga kerakli yo'nalishni tanlang:", reply_markup=keyboard)
    await state.set_state(PassengerState.waiting_for_direction)


@router.message(PassengerState.waiting_for_direction, F.text == "🏠 Asosiy menyu")
async def back_to_main_passenger(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(PassengerState.waiting_for_direction)
async def passenger_chosen_direction(message: Message, state: FSMContext):
    if message.text not in drivers_queues:
        await message.answer("⚠️ Iltimos, tugmalardan birini tanlang!")
        return
    await state.update_data(direction=message.text)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 1 ta odam"),
                KeyboardButton(text="👥 2 ta odam")
            ],
            [
                KeyboardButton(text="👨‍👩‍👦 3 ta odam"),
                KeyboardButton(text="👨‍👩‍👧‍👦 4 ta odam")
            ],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "👥 **Yo'lovchilar sonini tanlang:**\n\n"
        "⚠️ <i>ESLATMA: ANIQ ODAM SONINI BELGILANG!</i> ............ ⬇️", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )
    await state.set_state(PassengerState.waiting_for_passengers)


@router.message(PassengerState.waiting_for_passengers)
async def passenger_chosen_count(message: Message, state: FSMContext):
    text = message.text
    count_map = {
        "👤 1 ta odam": 1,
        "👥 2 ta odam": 2,
        "👨‍👩‍👦 3 ta odam": 3,
        "👨‍👩‍👧‍👦 4 ta odam": 4
    }

    if text not in count_map:
        await message.answer("⚠️ Iltimos, pastdagi tugmalardan birini tanlang va **ANIQ ODAM SONINI BELGILANG** ⬇️", parse_mode="Markdown")
        return

    await state.update_data(passenger_count=count_map[text])
    data = await state.get_data()
    direction = data["direction"]
    p_count = data["passenger_count"]

    # Tasdiqlash uchun Inline tugmalar (Taksi chaqirish o'ng tomonga qo'yildi)
    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_order"),
                InlineKeyboardButton(text="✅ TAKSI CHAQIRISH", callback_data="confirm_order")
            ]
        ]
    )

    await message.answer(
        f"📋 **Sizning ma'lumotlaringiz:**\n\n"
        f"📍 Yo'nalish: <b>{direction}</b>\n"
        f"👥 Odam soni: <b>{p_count} ta</b>\n\n"
        f"Buyurtmani haydovchilarga yuborishni tasdiqlaysizmi?",
        reply_markup=confirm_keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "cancel_order")
async def cancel_order_inline(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.")
    await callback.message.answer("Asosiy menyu:", reply_markup=main_menu())
    await callback.answer("Bekor qilindi")


@router.callback_query(F.data == "confirm_order")
async def confirm_order_inline(callback: CallbackQuery, state: FSMContext):
    passenger_id = callback.from_user.id
    passenger_name = callback.from_user.full_name

    cursor.execute("SELECT phone FROM passengers WHERE passenger_id = ?", (passenger_id,))
    row = cursor.fetchone()

    if row and row[0]:
        phone = row[0]
        data = await state.get_data()
        direction = data.get("direction", DIR_1)
        p_count = data.get("passenger_count", 1)

        await callback.message.edit_text("✅ Buyurtmangiz tasdiqlandi va haydovchiga yuborildi! 🚗")
        await state.clear()

        order_info = {
            "passenger_id": passenger_id,
            "passenger_name": passenger_name,
            "phone": phone,
            "count": p_count,
            "direction": direction
        }
        pending_orders[passenger_id] = order_info
        await send_order_to_next_driver(direction, order_info)
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🏠 Asosiy menyu")]],
            resize_keyboard=True,
        )
        await callback.message.edit_text("📞 **Telefon raqamingizni kiriting** (masalan: `+998901234567`):", parse_mode="Markdown")
        await state.set_state(PassengerState.waiting_for_phone)

    await callback.answer("Buyurtma qabul qilindi!")


@router.message(PassengerState.waiting_for_phone, F.text == "🏠 Asosiy menyu")
async def back_from_phone(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(PassengerState.waiting_for_phone)
async def passenger_got_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or len(phone) < 9:
        await message.answer("⚠️ Noto'g'ri format! Iltimos, raqamni to'g'ri kiriting (masalan: `+998901234567`):", parse_mode="Markdown")
        return

    passenger_id = message.from_user.id
    passenger_name = message.from_user.full_name

    cursor.execute("INSERT OR REPLACE INTO passengers (passenger_id, phone) VALUES (?, ?)", (passenger_id, phone))
    conn.commit()

    data = await state.get_data()
    direction = data.get("direction", DIR_1)
    p_count = data.get("passenger_count", 1)

    await message.answer("✅ Buyurtmangiz qabul qilindi! Haydovchi qidirilmoqda...", reply_markup=main_menu())
    await state.clear()

    order_info = {
        "passenger_id": passenger_id,
        "passenger_name": passenger_name,
        "phone": phone,
        "count": p_count,
        "direction": direction
    }
    pending_orders[passenger_id] = order_info
    await send_order_to_next_driver(direction, order_info)


# ==========================================
#              HAYDOVCHI QISMI
# ==========================================

@router.message(F.text == "🚗 HAYDOVCHI")
async def driver_entry(message: Message, state: FSMContext):
    driver_id = message.from_user.id

    cursor.execute("SELECT status, paid_until FROM drivers WHERE driver_id = ?", (driver_id,))
    row = cursor.fetchone()

    if not row:
        await message.answer(
            "🚗 Haydovchilar safiga xush kelibsiz!\nAvtomashina nomini kiriting (masalan: *Cobalt*):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(DriverRegState.waiting_for_car_name)
        return

    status, paid_until_str = row

    if status == "rejected":
        await message.answer(
            "❌ Afsuski, oldingi arizangiz rad etilgan edi.\n"
            "Lekin ma'lumotlaringizni to'g'rilab, **qaytadan ro'yxatdan o'tishingiz mumkin**.\n\n"
            "Iltimos, yangi **Avtomashina nomini** kiriting (masalan: *Cobalt*):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(DriverRegState.waiting_for_car_name)
        return

    if status == "pending":
        await message.answer("⏳ Arizangiz ko'rib chiqilmoqda.")
        return

    paid_until = datetime.fromisoformat(paid_until_str) if paid_until_str else None
    if paid_until and datetime.now() > paid_until:
        await message.answer("⚠️ To'lov muddatingiz tugagan! Adminga murojaat qiling.", reply_markup=main_menu())
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=DIR_1)],
            [KeyboardButton(text=DIR_2)],
            [KeyboardButton(text="💰 Mening hisobim"), KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("📍 Ishlamoqchi bo'lgan yo'nalishni tanlang:", reply_markup=keyboard)
    await state.set_state(DriverState.waiting_for_direction)


@router.message(DriverRegState.waiting_for_car_name)
async def reg_car_name(message: Message, state: FSMContext):
    await state.update_data(car_name=message.text)
    await message.answer("🚗 Avto raqamini kiriting (masalan: `01A777AA`):", parse_mode="Markdown")
    await state.set_state(DriverRegState.waiting_for_car_number)


@router.message(DriverRegState.waiting_for_car_number)
async def reg_car_number(message: Message, state: FSMContext):
    await state.update_data(car_number=message.text)
    await message.answer("👤 Ism va familiyangizni kiriting:")
    await state.set_state(DriverRegState.waiting_for_name)


@router.message(DriverRegState.waiting_for_name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📞 Telefon raqamingizni kiriting (masalan: `+998901234567`):", parse_mode="Markdown")
    await state.set_state(DriverRegState.waiting_for_phone)


@router.message(DriverRegState.waiting_for_phone)
async def reg_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or len(phone) < 9:
        await message.answer("⚠️ Noto'g'ri format! Iltimos, raqamni to'g'ri kiriting (masalan: `+998901234567`):", parse_mode="Markdown")
        return

    data = await state.get_data()
    driver_id = message.from_user.id
    
    cursor.execute("""
    INSERT OR REPLACE INTO drivers (driver_id, name, car, number, phone, status, paid_until, last_work_date, missed_counts, reject_counts)
    VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, '{}', '{}')
    """, (driver_id, data["name"], data["car_name"], data["car_number"], phone))
    conn.commit()
    
    await state.clear()
    await message.answer("✅ Ma'lumotlar adminga yuborildi!", reply_markup=main_menu())

    admin_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"✅ Tasdiqlash_{driver_id}"), KeyboardButton(text=f"❌ Rad etish_{driver_id}")]],
        resize_keyboard=True,
    )
    
    p_clean = phone.strip()
    if not p_clean.startswith("+"):
        p_clean = "+" + p_clean

    try:
        await bot.send_message(
            ADMIN_ID,
            f"🚨 **Yangi haydovchi arizasi:**\n"
            f"🆔 ID: `{driver_id}`\n"
            f"👤 Ism: {data['name']}\n"
            f"🚗 Mashina: {data['car_name']} ({data['car_number']})\n"
            f"📞 Telefon: [{phone}](tel:{p_clean})",
            reply_markup=admin_keyboard,
            parse_mode="Markdown"
        )
    except:
        pass


@router.message(F.text.startswith("✅ Tasdiqlash_"))
async def admin_approve_driver(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    driver_id = int(message.text.split("_")[1])
    
    paid_date = (datetime.now() + timedelta(days=10)).isoformat()
    cursor.execute("UPDATE drivers SET status = 'approved', paid_until = ? WHERE driver_id = ?", (paid_date, driver_id))
    conn.commit()

    await message.edit_text("✅ Haydovchi tasdiqlandi va 10 kun berildi!")
    try:
        await bot.send_message(driver_id, "🎉 Tabriklaymiz! Arizangiz tasdiqlandi va 10 kunlik muddat berildi.")
    except:
        pass


@router.message(F.text.startswith("❌ Rad etish_"))
async def admin_reject_driver(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    driver_id = int(message.text.split("_")[1])
    
    cursor.execute("UPDATE drivers SET status = 'rejected' WHERE driver_id = ?", (driver_id,))
    conn.commit()

    await message.edit_text("❌ Haydovchi rad etildi.")
    try:
        await bot.send_message(driver_id, "❌ Afsuski, arizangiz rad etildi.")
    except:
        pass


@router.message(DriverState.waiting_for_direction, F.text == "💰 Mening hisobim")
async def driver_check_balance(message: Message):
    driver_id = message.from_user.id
    cursor.execute("SELECT paid_until FROM drivers WHERE driver_id = ?", (driver_id,))
    row = cursor.fetchone()
    
    if not row or not row[0]:
        await message.answer("❌ Faol muddatingiz yo'q.")
        return
        
    paid_until = datetime.fromisoformat(row[0])
    left_days = (paid_until - datetime.now()).days
    await message.answer(f"💰 Qolgan muddat: **{left_days} kun**", parse_mode="Markdown")


@router.message(DriverState.waiting_for_direction)
async def driver_chosen_direction(message: Message, state: FSMContext):
    if message.text not in drivers_queues:
        await message.answer("⚠️ Iltimos, tugmadan tanlang!")
        return

    driver_id = message.from_user.id
    direction = message.text

    cursor.execute("SELECT name, paid_until, last_work_date FROM drivers WHERE driver_id = ?", (driver_id,))
    row = cursor.fetchone()
    if not row:
        await message.answer("⚠️ Xatolik yuz berdi.")
        return

    name, paid_until_str, last_work_date_str = row
    paid_until = datetime.fromisoformat(paid_until_str) if paid_until_str else None
    today_date_str = str(datetime.now().date())

    if not paid_until or paid_until < datetime.now():
        await message.answer("⚠️ Hisobingizdagi kun tugagan!")
        return

    if last_work_date_str != today_date_str:
        paid_until -= timedelta(days=1)
        paid_until_str = paid_until.isoformat()
        cursor.execute("UPDATE drivers SET paid_until = ?, last_work_date = ? WHERE driver_id = ?", (paid_until_str, today_date_str, driver_id))
        conn.commit()

    if not any(d["id"] == driver_id for d in drivers_queues[direction]):
        drivers_queues[direction].append({
            "id": driver_id,
            "name": name,
            "seats": 4
        })

    cursor.execute("SELECT missed_counts, reject_counts FROM drivers WHERE driver_id = ?", (driver_id,))
    m_row = cursor.fetchone()
    if m_row:
        missed_dict = json.loads(m_row[0]) if m_row[0] else {}
        reject_dict = json.loads(m_row[1]) if m_row[1] else {}
        missed_dict[direction] = 0
        reject_dict[direction] = 0
        cursor.execute("UPDATE drivers SET missed_counts = ?, reject_counts = ? WHERE driver_id = ?", (json.dumps(missed_dict), json.dumps(reject_dict), driver_id))
        conn.commit()

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Navbatdan chiqish"), KeyboardButton(text="📋 Navbat ro'yxati")]],
        resize_keyboard=True,
    )
    await message.answer(f"✅ **{direction}** bo'yicha navbatga qo'shildingiz!", reply_markup=keyboard, parse_mode="Markdown")
    await state.clear()


@router.message(F.text == "❌ Navbatdan chiqish")
async def driver_leave_queue(message: Message):
    driver_id = message.from_user.id
    for direction in drivers_queues:
        for d in drivers_queues[direction]:
            if d["id"] == driver_id:
                drivers_queues[direction].remove(d)
    await message.answer("✅ Siz navbatdan chiqarildingiz.", reply_markup=main_menu())


@router.message(F.text == "📋 Navbat ro'yxati")
async def show_queue_list(message: Message):
    driver_id = message.from_user.id
    my_direction = None
    for direction in drivers_queues:
        if any(d["id"] == driver_id for d in drivers_queues[direction]):
            my_direction = direction
            break

    if not my_direction:
        await message.answer("⚠️ Siz hozirda hech qanday navbatda emassiz!")
        return

    queue_text = f"📋 **{my_direction}** navbati:\n\n"
    for idx, driver in enumerate(drivers_queues[my_direction], 1):
        queue_text += f"{idx}. {driver['name']} (Bo'sh joy: {driver['seats']} ta)\n"
    await message.answer(queue_text, parse_mode="Markdown")


@router.message(F.text == "🏠 Asosiy menyu")
async def back_to_main_menu_general(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


# ==========================================
#          FIFO VA QOIDALAR
# ==========================================

async def send_order_to_next_driver(direction, order_data):
    if not drivers_queues[direction]:
        try:
            await bot.send_message(order_data["passenger_id"], "😔 Hozirda bu yo'nalishda bo'sh haydovchilar topilmadi.")
        except:
            pass
        return

    current_driver = drivers_queues[direction][0]
    driver_id = current_driver["id"]

    if current_driver["seats"] < order_data["count"]:
        drivers_queues[direction].pop(0)
        drivers_queues[direction].append(current_driver)
        await send_order_to_next_driver(direction, order_data)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_{order_data['passenger_id']}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{order_data['passenger_id']}")
            ]
        ]
    )

    text = (
        f"🔔🚨 **DIQQAT! YANGI BUYURTMA!** 🚨🔔\n\n"
        f"📍 Yo'nalish: <b>{direction}</b>\n"
        f"👥 Yo'lovchilar soni: <b>{order_data['count']} ta</b>\n"
        f"💺 Bo'sh joyingiz: <b>{current_driver['seats']} ta</b>\n\n"
        f"⏱ <i>12 soniya ichida qaror qabul qiling!</i>"
    )

    sent_msg = await bot.send_message(driver_id, text, reply_markup=keyboard, parse_mode="HTML")

    async def timeout_task():
        await asyncio.sleep(12)
        if order_data["passenger_id"] in active_orders:
            active_orders[order_data["passenger_id"]].cancel()
            del active_orders[order_data["passenger_id"]]
            
            try:
                await bot.edit_message_text(
                    chat_id=driver_id,
                    message_id=sent_msg.message_id,
                    text=f"{text}\n\n❌ **Vaqt tugadi! Siz buyurtmaga javob bermadingiz.**",
                    reply_markup=None,
                    parse_mode="Markdown"
                )
            except:
                pass
            
            if drivers_queues[direction] and drivers_queues[direction][0]["id"] == driver_id:
                cursor.execute("SELECT missed_counts FROM drivers WHERE driver_id = ?", (driver_id,))
                row = cursor.fetchone()
                missed_dict = json.loads(row[0]) if row and row[0] else {}
                
                current_missed = missed_dict.get(direction, 0) + 1
                missed_dict[direction] = current_missed
                
                cursor.execute("UPDATE drivers SET missed_counts = ? WHERE driver_id = ?", (json.dumps(missed_dict), driver_id))
                conn.commit()

                driver_obj = drivers_queues[direction].pop(0)

                if current_missed >= 5:
                    insert_pos = min(1, len(drivers_queues[direction]))
                    drivers_queues[direction].insert(insert_pos, driver_obj)
                    missed_dict[direction] = 0
                    cursor.execute("UPDATE drivers SET missed_counts = ? WHERE driver_id = ?", (json.dumps(missed_dict), driver_id))
                    conn.commit()
                    await bot.send_message(driver_id, "⚠️ 5 marta ketma-ket zakazni o'tkazib yuborganingiz uchun navbatda 1 taga pastga surildingiz.")
                else:
                    drivers_queues[direction].append(driver_obj)
                    await bot.send_message(driver_id, f"⚠️ Vaqt tugadi ({current_missed}/5). Zakaz o'tkazib yuborildi.")

            await send_order_to_next_driver(direction, order_data)

    active_orders[order_data["passenger_id"]] = asyncio.create_task(timeout_task())


@router.callback_query(F.data.startswith("accept_"))
async def accept_order_inline(callback: CallbackQuery):
    try:
        passenger_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        return

    driver_id = callback.from_user.id

    if passenger_id in active_orders:
        active_orders[passenger_id].cancel()
        del active_orders[passenger_id]

        order_info = pending_orders.get(passenger_id, {})
        direction = order_info.get("direction", "")

        cursor.execute("SELECT missed_counts, reject_counts, car, number, name, phone FROM drivers WHERE driver_id = ?", (driver_id,))
        row = cursor.fetchone()
        if row:
            missed_dict = json.loads(row[0]) if row[0] else {}
            reject_dict = json.loads(row[1]) if row[1] else {}
            missed_dict[direction] = 0
            reject_dict[direction] = 0
            cursor.execute("UPDATE drivers SET missed_counts = ?, reject_counts = ? WHERE driver_id = ?", (json.dumps(missed_dict), json.dumps(reject_dict), driver_id))
            conn.commit()
            d_car, d_num, d_name, d_phone = row[2], row[3], row[4], row[5]
        else:
            d_car, d_num, d_name, d_phone = "", "", "", ""

        p_phone = order_info.get("phone", "")
        p_name = order_info.get("passenger_name", "Yo'lovchi")
        p_count = order_info.get("count", 1)
        
        p_phone_clean = p_phone.strip()
        if not p_phone_clean.startswith("+"):
            p_phone_clean = "+" + p_phone_clean

        for dir_name in drivers_queues:
            for d in drivers_queues[dir_name]:
                if d["id"] == driver_id:
                    d["seats"] -= p_count
                    drivers_queues[dir_name].remove(d)
                    
                    if d["seats"] > 0:
                        drivers_queues[dir_name].append(d)
                        await callback.message.edit_text(
                            f"✅ **Buyurtma olindi!**\n👤 Yo'lovchi: {p_name}\n📞 Telefon: [{p_phone}](tel:{p_phone_clean})\n💺 Bo'sh joy: {d['seats']} ta",
                            parse_mode="Markdown"
                        )
                    else:
                        await callback.message.edit_text("✅ **Mashina to'ldi! Navbatdan chiqarildingiz.**", parse_mode="Markdown")
                    break

        d_phone_clean = d_phone.strip() if d_phone else ""
        if d_phone_clean and not d_phone_clean.startswith("+"):
            d_phone_clean = "+" + d_phone_clean
        
        try:
            await bot.send_message(
                passenger_id,
                f"🎉 **Haydovchi topildi!**\n🚗 {d_car} ({d_num})\n👤 {d_name}\n📞 Telefon: [{d_phone}](tel:{d_phone_clean})",
                parse_mode="Markdown"
            )
        except:
            pass
        await callback.answer("Buyurtma muvaffaqiyatli qabul qilindi!")
    else:
        await callback.message.edit_text("⚠️ Bu buyurtma vaqti o'tib ketgan yoki boshqa haydovchi tomonidan olingan.")
        await callback.answer("Xatolik!", show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
async def reject_order_inline(callback: CallbackQuery):
    try:
        passenger_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        return

    driver_id = callback.from_user.id

    if passenger_id in active_orders:
        active_orders[passenger_id].cancel()
        del active_orders[passenger_id]

        await callback.message.edit_text("❌ **Buyurtmani rad etdingiz.**", parse_mode="Markdown")

        order_info = pending_orders.get(passenger_id, {})
        direction = order_info.get("direction", "")

        for dir_name in drivers_queues:
            if dir_name == direction and drivers_queues[dir_name] and drivers_queues[dir_name][0]["id"] == driver_id:
                cursor.execute("SELECT reject_counts FROM drivers WHERE driver_id = ?", (driver_id,))
                row = cursor.fetchone()
                reject_dict = json.loads(row[0]) if row and row[0] else {}
                
                current_reject = reject_dict.get(direction, 0) + 1
                reject_dict[direction] = current_reject
                
                cursor.execute("UPDATE drivers SET reject_counts = ? WHERE driver_id = ?", (json.dumps(reject_dict), driver_id))
                conn.commit()

                driver_obj = drivers_queues[direction].pop(0)

                if current_reject >= 5:
                    reject_dict[direction] = 0
                    cursor.execute("UPDATE drivers SET reject_counts = ? WHERE driver_id = ?", (json.dumps(reject_dict), driver_id))
                    conn.commit()

                    await bot.send_message(
                        driver_id, 
                        "❌ 5 marta ketma-ket rad etganingiz uchun ushbu yo'nalishdagi **navbatdan chiqarildingiz**!", 
                        parse_mode="Markdown",
                        reply_markup=main_menu()
                    )
                else:
                    drivers_queues[direction].append(driver_obj)
                    await bot.send_message(
                        driver_id, 
                        f"⚠️ Buyurtmani rad etdingiz ({current_reject}/5). Navbatning oxiriga tushirildingiz.",
                        parse_mode="Markdown"
                    )

                if passenger_id in pending_orders:
                    await send_order_to_next_driver(direction, pending_orders[passenger_id])
                break
        await callback.answer("Buyurtma rad etildi.")
    else:
        await callback.message.edit_text("⚠️ Bu buyurtma allaqachon yakunlangan.")
        await callback.answer("Xatolik!", show_alert=True)


# ==========================================
#   HAR KUNI SOAT 05:00 DA NAVBATLARNI TOZALASH
# ==========================================
async def daily_queue_reset():
    while True:
        now = datetime.now()
        target_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
        
        if now >= target_time:
            target_time += timedelta(days=1)
            
        wait_seconds = (target_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        for direction in drivers_queues:
            drivers_queues[direction].clear()
            
        cursor.execute("UPDATE drivers SET missed_counts = '{}', reject_counts = '{}'")
        conn.commit()
            
        print("🔄 Avtomatik tarzda barcha navbatlar soat 05:00 da qayta tozalandi!")


# Botni ishga tushirish
async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    
    asyncio.create_task(daily_queue_reset())
    
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())