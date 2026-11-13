import asyncio
import logging
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

# Ma'lumotlar bazasi
drivers_db = {}          # Haydovchilar ma'lumotlari

# YAngi tushunarli va belgilangan yo'nalishlar
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

    if driver_id not in drivers_db:
        await message.answer("❌ Bu ID raqamdagi haydovchi bazadan topilmadi!")
        return

    current_paid_until = drivers_db[driver_id].get("paid_until")
    if current_paid_until and current_paid_until > datetime.now():
        new_paid_until = current_paid_until + timedelta(days=days)
    else:
        new_paid_until = datetime.now() + timedelta(days=days)

    drivers_db[driver_id]["paid_until"] = new_paid_until
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


@router.message(Command("haydovchilar"))
async def admin_driver_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not drivers_db:
        await message.answer("📭 Hozircha bazada haydovchilar yo'q.")
        return
    
    text = "🚗 **Barcha haydovchilar ro'yxati va holati:**\n\n"
    for d_id, data in drivers_db.items():
        status = data.get("status", "noma'lum")
        paid_until = data.get("paid_until")
        
        if paid_until:
            left_days = (paid_until - datetime.now()).days
            left_str = f"⏳ {left_days} kun qoldi" if left_days >= 0 else "⚠️ Muddati tugagan!"
        else:
            left_str = "Hali faollashmagan"
            
        text += (
            f"👤 **Ism:** {data['name']}\n"
            f"🆔 ID: `{d_id}`\n"
            f"🚗 Mashina: {data['car']} ({data['number']})\n"
            f"📞 Tel: {data['phone']}\n"
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
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3"), KeyboardButton(text="4")],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("👥 Yo'lovchilar sonini tanlang:", reply_markup=keyboard)
    await state.set_state(PassengerState.waiting_for_passengers)


@router.message(PassengerState.waiting_for_passengers)
async def passenger_chosen_count(message: Message, state: FSMContext):
    if message.text not in ["1", "2", "3", "4"]:
        await message.answer("⚠️ Iltimos, 1 dan 4 gacha bo'lgan raqamni tanlang!")
        return
    await state.update_data(passenger_count=int(message.text))

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("📞 Bog'lanish uchun pastdagi **'📞 Telefon raqamni yuborish'** tugmasini bosing:", reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(PassengerState.waiting_for_phone)


@router.message(PassengerState.waiting_for_phone, F.text == "🏠 Asosiy menyu")
async def back_from_phone(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(PassengerState.waiting_for_phone, ~F.contact)
async def passenger_wrong_phone(message: Message):
    await message.answer(
        "⚠️ **Iltimos, raqamni qo'lda yozmang!**\n"
        "Faqat pastdagi **'📞 Telefon raqamni yuborish'** tugmasini bosing.",
        parse_mode="Markdown"
    )


@router.message(PassengerState.waiting_for_phone, F.contact)
async def passenger_got_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    direction = data["direction"]
    p_count = data["passenger_count"]
    phone = message.contact.phone_number
    passenger_id = message.from_user.id
    passenger_name = message.from_user.full_name

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

    if driver_id not in drivers_db:
        await message.answer(
            "🚗 Haydovchilar safiga xush kelibsiz!\nAvtomashina nomini kiriting (masalan: *Cobalt*):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(DriverRegState.waiting_for_car_name)
        return

    if drivers_db[driver_id]["status"] == "rejected":
        await message.answer(
            "❌ Afsuski, oldingi arizangiz rad etilgan edi.\n"
            "Lekin ma'lumotlaringizni to'g'rilab, **qaytadan ro'yxatdan o'tishingiz mumkin**.\n\n"
            "Iltimos, yangi **Avtomashina nomini** kiriting (masalan: *Cobalt*):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(DriverRegState.waiting_for_car_name)
        return

    if drivers_db[driver_id]["status"] == "pending":
        await message.answer("⏳ Arizangiz ko'rib chiqilmoqda.")
        return

    paid_until = drivers_db[driver_id].get("paid_until")
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
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
    )
    await message.answer("📞 Telefon raqamingizni yuborish uchun pastdagi tugmani bosing:", reply_markup=keyboard)
    await state.set_state(DriverRegState.waiting_for_phone)


@router.message(DriverRegState.waiting_for_phone, ~F.contact)
async def driver_wrong_phone(message: Message):
    await message.answer(
        "⚠️ **Iltimos, raqamni qo'lda yozmang!**\n"
        "Faqat pastdagi **'📞 Telefon raqamni yuborish'** tugmasini bosing.",
        parse_mode="Markdown"
    )


@router.message(DriverRegState.waiting_for_phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    driver_id = message.from_user.id
    
    drivers_db[driver_id] = {
        "name": data["name"],
        "car": data["car_name"],
        "number": data["car_number"],
        "phone": message.contact.phone_number,
        "status": "pending",
        "paid_until": None,
        "last_work_date": None,
        "missed_counts": {}
    }
    
    await state.clear()
    await message.answer("✅ Ma'lumotlar adminga yuborildi!", reply_markup=main_menu())

    admin_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"✅ Tasdiqlash_{driver_id}"), KeyboardButton(text=f"❌ Rad etish_{driver_id}")]],
        resize_keyboard=True,
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🚨 Yangi haydovchi:\n🆔 ID: `{driver_id}`\n👤 Ism: {data['name']}\n🚗 {data['car_name']} ({data['car_number']})",
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
    if driver_id in drivers_db:
        drivers_db[driver_id]["status"] = "approved"
        drivers_db[driver_id]["paid_until"] = datetime.now() + timedelta(days=10)
        await message.edit_text("✅ Haydovchi tasdiqlandi va 10 kun berildi!")
        try:
            await bot.send_message(driver_id, "🎉 Tabriklaymiz! 10 kunlik muddat berildi.")
        except:
            pass


@router.message(F.text.startswith("❌ Rad etish_"))
async def admin_reject_driver(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    driver_id = int(message.text.split("_")[1])
    if driver_id in drivers_db:
        drivers_db[driver_id]["status"] = "rejected"
        await message.edit_text("❌ Haydovchi rad etildi.")
        try:
            await bot.send_message(driver_id, "❌ Arizangiz rad etildi.")
        except:
            pass


@router.message(DriverState.waiting_for_direction, F.text == "💰 Mening hisobim")
async def driver_check_balance(message: Message):
    driver_id = message.from_user.id
    data = drivers_db.get(driver_id, {})
    paid_until = data.get("paid_until")
    if not paid_until:
        await message.answer("❌ Faol muddatingiz yo'q.")
        return
    left_days = (paid_until - datetime.now()).days
    await message.answer(f"💰 Qolgan muddat: **{left_days} kun**", parse_mode="Markdown")


@router.message(DriverState.waiting_for_direction)
async def driver_chosen_direction(message: Message, state: FSMContext):
    if message.text not in drivers_queues:
        await message.answer("⚠️ Iltimos, tugmadan tanlang!")
        return

    driver_id = message.from_user.id
    direction = message.text
    driver_data = drivers_db[driver_id]

    today_date = datetime.now().date()
    if driver_data.get("last_work_date") != today_date:
        driver_data["paid_until"] -= timedelta(days=1)
        driver_data["last_work_date"] = today_date

    if driver_data["paid_until"] < datetime.now():
        await message.answer("⚠️ Hisobingizdagi kun tugagan!")
        return

    if not any(d["id"] == driver_id for d in drivers_queues[direction]):
        drivers_queues[direction].append({
            "id": driver_id,
            "name": driver_data["name"],
            "seats": 4
        })

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
#      FIFO, 8 MARTALIK QOIDALAR VA INLINE
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
                d_db = drivers_db.get(driver_id, {})
                if "missed_counts" not in d_db:
                    d_db["missed_counts"] = {}
                
                current_missed = d_db["missed_counts"].get(direction, 0) + 1
                d_db["missed_counts"][direction] = current_missed

                driver_obj = drivers_queues[direction].pop(0)

                if current_missed < 8:
                    drivers_queues[direction].insert(1, driver_obj)
                    await bot.send_message(driver_id, f"⚠️ E'tiborsiz qoldirganingiz uchun navbatda 1 taga pastga surildingiz ({current_missed}/8).")
                else:
                    drivers_queues[direction].append(driver_obj)
                    d_db["missed_counts"][direction] = 0
                    await bot.send_message(driver_id, "⚠️ 8 marta javob bermaganingiz uchun ushbu yo'nalishdagi navbatning **oxiriga** tushirildingiz!", parse_mode="Markdown")

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

        if driver_id in drivers_db:
            if "missed_counts" in drivers_db[driver_id]:
                drivers_db[driver_id]["missed_counts"][direction] = 0

        p_phone = order_info.get("phone", "")
        p_name = order_info.get("passenger_name", "Yo'lovchi")
        p_count = order_info.get("count", 1)
        
        p_phone_link = f"tel:+{p_phone}" if not p_phone.startswith("+") else f"tel:{p_phone}"

        for dir_name in drivers_queues:
            for d in drivers_queues[dir_name]:
                if d["id"] == driver_id:
                    d["seats"] -= p_count
                    drivers_queues[dir_name].remove(d)
                    
                    if d["seats"] > 0:
                        drivers_queues[dir_name].append(d)
                        await callback.message.edit_text(
                            f"✅ **Buyurtma olindi!**\n👤 Yo'lovchi: {p_name}\n📞 Telefon: [{p_phone}]({p_phone_link})\n💺 Bo'sh joy: {d['seats']} ta",
                            parse_mode="Markdown"
                        )
                    else:
                        await callback.message.edit_text("✅ **Mashina to'ldi! Navbatdan chiqarildingiz.**", parse_mode="Markdown")
                    break

        d_info = drivers_db.get(driver_id, {})
        d_phone = d_info.get('phone', '')
        d_phone_link = f"tel:+{d_phone}" if not d_phone.startswith("+") else f"tel:{d_phone}"
        
        try:
            await bot.send_message(
                passenger_id,
                f"🎉 **Haydovchi topildi!**\n🚗 {d_info.get('car')} ({d_info.get('number')})\n👤 {d_info.get('name')}\n📞 Telefon: [{d_phone}]({d_phone_link})",
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
                d_db = drivers_db.get(driver_id, {})
                if "missed_counts" not in d_db:
                    d_db["missed_counts"] = {}
                
                current_missed = d_db["missed_counts"].get(direction, 0) + 1
                d_db["missed_counts"][direction] = current_missed

                driver_obj = drivers_queues[direction].pop(0)

                if current_missed < 8:
                    drivers_queues[direction].insert(1, driver_obj)
                    await bot.send_message(driver_id, f"⚠️ Rad etganingiz uchun navbatda 1 taga pastga surildingiz ({current_missed}/8).")
                else:
                    drivers_queues[direction].append(driver_obj)
                    d_db["missed_counts"][direction] = 0
                    await bot.send_message(driver_id, "⚠️ 8 marta rad etganingiz uchun ushbu yo'nalishdagi navbatning **oxiriga** tushirildingiz!", parse_mode="Markdown")

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
    """Har kuni tonggi soat 05:00 da barcha yo'nalishdagi navbatlarni tozalash"""
    while True:
        now = datetime.now()
        target_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
        
        if now >= target_time:
            target_time += timedelta(days=1)
            
        wait_seconds = (target_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        for direction in drivers_queues:
            drivers_queues[direction].clear()
            
        for d_id in drivers_db:
            drivers_db[d_id]["missed_counts"] = {}
            
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