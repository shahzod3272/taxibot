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
drivers_queues = {
    "QAXRAMON MFY>>DO'STLIK": [],
    "DO'STLIK>>QAXRAMON MFY": []
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


# --- ASOSIY MENYU (Yo'lovchi birinchi o'rinda) ---
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
        "👇 **Iltimos, o'zingizga kerakli tugmani tanlang:**\n\n"
        "👤 👉 Agar manzilga bormoqchi bo'lsangiz, **\"👤 YO'LOVCHI\"** tugmasini bosing va bir soniyada bo'sh haydovchiga ulang!\n\n"
        "🚗 👉 Agar mashinangiz bo'lib, navbatga turib ishlamoqchi bo'lsangiz, **\"🚗 HAYDOVCHI\"** tugmasini bosing!\n\n"
        "💡 Barcha qulayliklar va adolatli navbat tizimi sizning xizmatingizda.",
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
        await message.answer("⚠️ Noto'g'ri format!\nIshlatish: `/uzaytirish HAYDOVCHI_ID KUN_SONI`\nMisol: `/uzaytirish 1145699643 30`", parse_mode="Markdown")
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
            f"🎉 **Tabriklaymiz!** Admin sizning botdan foydalanish muddatingizni **{days} kunga** uzaytirirdi.\n📅 Amal qilish muddati: {date_str}",
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
            left_str = f"⏳ {left_days} kun qoldi ({paid_until.strftime('%d.%m.%Y')})" if left_days >= 0 else "⚠️ Muddati tugagan!"
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
#      TAKLIF VA SHIKOYATLAR (FEEDBACK)
# ==========================================

@router.message(F.text == "💬 Taklif va Shikoyatlar")
async def feedback_start(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Asosiy menyu")]],
        resize_keyboard=True,
    )
    await message.answer(
        "✍️ Bot bo'yicha takliflaringiz, shikoyatlaringiz yoki topgan kamchiliklaringizni yozib yuboring. Xabaringiz adminga yetkaziladi:",
        reply_markup=keyboard
    )
    await state.set_state(FeedbackState.waiting_for_feedback)


@router.message(FeedbackState.waiting_for_feedback, F.text == "🏠 Asosiy menyu")
async def feedback_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(FeedbackState.waiting_for_feedback)
async def feedback_get(message: Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("Asosiy menyu:", reply_markup=main_menu())

    user_text = message.text
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📩 **Yangi murojaat / shikoyat!**\n\n"
            f"👤 Kimdan: {user.full_name} ({user_info})\n"
            f"📝 Xabar:\n{user_text}"
        )
    except:
        pass

    await state.clear()
    await message.answer("✅ Xabaringiz adminga yuborildi! E'tiboringiz uchun rahmat.", reply_markup=main_menu())


# ==========================================
#              YO'LOVCHI QISMI
# ==========================================

@router.message(F.text == "👤 YO'LOVCHI")
async def passenger_start(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="QAXRAMON MFY>>DO'STLIK")],
            [KeyboardButton(text="DO'STLIK>>QAXRAMON MFY")],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Iltimos, kerakli yo'nalishni tanlang:", reply_markup=keyboard)
    await state.set_state(PassengerState.waiting_for_direction)


@router.message(PassengerState.waiting_for_direction, F.text == "🏠 Asosiy menyu")
async def back_to_main_passenger(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(PassengerState.waiting_for_direction)
async def passenger_chosen_direction(message: Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("Asosiy menyu:", reply_markup=main_menu())

    if message.text not in drivers_queues:
        await message.answer("Iltimos, tugmalardan birini tanlang!")
        return

    await state.update_data(direction=message.text)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3"), KeyboardButton(text="4")],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Yo'lovchilar sonini tanlang:", reply_markup=keyboard)
    await state.set_state(PassengerState.waiting_for_passengers)


@router.message(PassengerState.waiting_for_passengers)
async def passenger_chosen_count(message: Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("Asosiy menyu:", reply_markup=main_menu())

    if message.text not in ["1", "2", "3", "4"]:
        await message.answer("Iltimos, 1 dan 4 gacha bo'lgan raqamni tanlang!")
        return

    await state.update_data(passenger_count=int(message.text))

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Bog'lanish uchun telefon raqamingizni yuboring:", reply_markup=keyboard)
    await state.set_state(PassengerState.waiting_for_phone)


@router.message(PassengerState.waiting_for_phone, F.text == "🏠 Asosiy menyu")
async def back_from_phone(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(PassengerState.waiting_for_phone, F.contact)
async def passenger_got_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    direction = data["direction"]
    p_count = data["passenger_count"]
    phone = message.contact.phone_number
    passenger_id = message.from_user.id
    passenger_name = message.from_user.full_name

    await message.answer(
        "✅ Buyurtmangiz qabul qilindi! Haydovchi qidirilmoqda, iltimos kuting...",
        reply_markup=main_menu()
    )
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
#              HAYDOVCHI QISMI & TO'LOV MANTIQ
# ==========================================

@router.message(F.text == "🚗 HAYDOVCHI")
async def driver_entry(message: Message, state: FSMContext):
    driver_id = message.from_user.id

    if driver_id not in drivers_db:
        await message.answer(
            "🚗 Haydovchilar safiga xush kelibsiz!\nRo'yxatdan o'tish uchun **Avtomashina nomini** kiriting (masalan: *Cobalt*, *Nexia*):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(DriverRegState.waiting_for_car_name)
        return

    if drivers_db[driver_id]["status"] == "pending":
        await message.answer("⏳ Sizning ma'lumotlaringiz adminga yuborilgan. Admin tasdiqlashini kuting.")
        return

    if drivers_db[driver_id]["status"] == "rejected":
        await message.answer("❌ Afsuski, admin arizangizni rad etgan.")
        return

    paid_until = drivers_db[driver_id].get("paid_until")
    if paid_until and datetime.now() > paid_until:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🏠 Asosiy menyu")]],
            resize_keyboard=True,
        )
        await message.answer(
            "⚠️ **Sizning muddatli to'lovingiz tugadi!**\n\n"
            "Botdan foydalanishni davom ettirish uchun kuniga 1000 so'm to'lov qilishingiz kerak.\n\n"
            "💳 **Karta raqam:** `8600 1234 5678 9012` (Ism Familiya)\n"
            "To'lov qilgach, chekni (skrinshotni) adminga yuboring va u muddatni uzaytirib beradi.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="QAXRAMON MFY>>DO'STLIK")],
            [KeyboardButton(text="DO'STLIK>>QAXRAMON MFY")],
            [KeyboardButton(text="💰 Mening hisobim"), KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Qaysi yo'nalish bo'yicha navbatga turasiz yoki hisobingizni ko'rasizmi?", reply_markup=keyboard)
    await state.set_state(DriverState.waiting_for_direction)


@router.message(DriverRegState.waiting_for_car_name)
async def reg_car_name(message: Message, state: FSMContext):
    await state.update_data(car_name=message.text)
    await message.answer("Avtomashina raqamini kiriting (masalan: `AB123C`):", parse_mode="Markdown")
    await state.set_state(DriverRegState.waiting_for_car_number)


@router.message(DriverRegState.waiting_for_car_number)
async def reg_car_number(message: Message, state: FSMContext):
    await state.update_data(car_number=message.text)
    await message.answer("Ism va familiyangizni kiriting:")
    await state.set_state(DriverRegState.waiting_for_name)


@router.message(DriverRegState.waiting_for_name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
    )
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=keyboard)
    await state.set_state(DriverRegState.waiting_for_phone)


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
        "last_work_date": None
    }
    
    await state.clear()
    await message.answer(
        "✅ Ma'lumotlaringiz adminga yuborildi! Admin tasdiqlagach, 10 kunlik tekin muddat boshlanadi.",
        reply_markup=main_menu()
    )

    admin_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"✅ Tasdiqlash_{driver_id}"), KeyboardButton(text=f"❌ Rad etish_{driver_id}")]
        ],
        resize_keyboard=True,
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🚨 **Yangi haydovchi ro'yxatdan o'tdi!**\n\n"
            f"🆔 ID: `{driver_id}`\n"
            f"👤 Ism: {data['name']}\n"
            f"🚗 Mashina: {data['car_name']} ({data['car_number']})\n"
            f"📞 Tel: {message.contact.phone_number}",
            reply_markup=admin_keyboard,
            parse_mode="Markdown"
        )
    except:
        pass


@router.message(F.text.startswith("✅ Tasdiqlash_"))
async def admin_approve_driver(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        driver_id = int(message.text.split("_")[1])
    except (IndexError, ValueError):
        return

    if driver_id in drivers_db:
        drivers_db[driver_id]["status"] = "approved"
        drivers_db[driver_id]["paid_until"] = datetime.now() + timedelta(days=10)
        
        try:
            await message.edit_text(
                f"{message.text}\n\n"
                f"✅ **HOLAT: Tasdiqlandi va 10 kunlik muddat berildi!**",
                parse_mode="Markdown"
            )
        except:
            await message.answer(f"Haydovchi (ID: {driver_id}) tasdiqlandi! ✅")

        try:
            await bot.send_message(driver_id, "🎉 Tabriklaymiz! Admin arizangizni tasdiqladi. Sizga **10 kunlik tekin sinov muddati** berildi. '🚗 HAYDOVCHI' tugmasini bosib ishni boshlashingiz mumkin.")
        except:
            pass


@router.message(F.text.startswith("❌ Rad etish_"))
async def admin_reject_driver(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        driver_id = int(message.text.split("_")[1])
    except (IndexError, ValueError):
        return

    if driver_id in drivers_db:
        drivers_db[driver_id]["status"] = "rejected"
        
        try:
            await message.edit_text(
                f"{message.text}\n\n"
                f"❌ **HOLAT: Rad etildi!**",
                parse_mode="Markdown"
            )
        except:
            await message.answer(f"Haydovchi (ID: {driver_id}) rad etildi. ❌")

        try:
            await bot.send_message(driver_id, "❌ Afsuski, admin arizangizni rad etdi.")
        except:
            pass


@router.message(DriverState.waiting_for_direction, F.text == "💰 Mening hisobim")
async def driver_check_balance(message: Message):
    driver_id = message.from_user.id
    data = drivers_db.get(driver_id, {})
    paid_until = data.get("paid_until")

    if not paid_until:
        await message.answer("❌ Hozircha faol muddatingiz yo'q.")
        return

    left_days = (paid_until - datetime.now()).days
    date_str = paid_until.strftime("%d.%m.%Y %H:%M")

    if left_days >= 0:
        await message.answer(
            f"💰 **Sizning hisobingiz:**\n\n"
            f"⏳ Qolgan muddat: **{left_days} kun**\n"
            f"📅 Tugash vaqti: {date_str}\n\n"
            f"💡 *Eslatma: Faqat ishlagan (navbatga turgan) kunlaringiz hisobdan 1 kundan yechiladi. Dam olgan kunlaringiz uchun pul olinmaydi!*",
            parse_mode="Markdown"
        )
    else:
        await message.answer("⚠️ Muddatingiz tugagan! Iltimos, to'lov qilib adminga chek yuboring.")


@router.message(DriverState.waiting_for_direction)
async def driver_chosen_direction(message: Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("Asosiy menyu:", reply_markup=main_menu())

    if message.text not in drivers_queues:
        await message.answer("Iltimos, tugmalardan birini tanlang!")
        return

    driver_id = message.from_user.id
    direction = message.text

    today_date = datetime.now().date()
    driver_data = drivers_db[driver_id]
    last_work = driver_data.get("last_work_date")

    if last_work != today_date:
        paid_until = driver_data.get("paid_until")
        if paid_until:
            driver_data["paid_until"] = paid_until - timedelta(days=1)
            driver_data["last_work_date"] = today_date

    if driver_data["paid_until"] < datetime.now():
        await message.answer("⚠️ Navbatga turganingizda hisobingizdagi kun tugab qoldi! Iltimos, to'lovni amalga oshiring.")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Navbatdan chiqish"), KeyboardButton(text="📋 Navbat ro'yxati")],
        ],
        resize_keyboard=True,
    )

    if not any(d["id"] == driver_id for d in drivers_queues[direction]):
        drivers_queues[direction].append({
            "id": driver_id,
            "name": driver_data["name"],
            "seats": 4
        })

    left_days = (driver_data["paid_until"] - datetime.now()).days
    await message.answer(
        f"✅ Siz **{direction}** yo'nalishi bo'yicha navbatga qo'shildingiz!\n"
        f"💰 Bugungi ish kuni hisoblandi. Qolgan muddat: **{left_days} kun**\n\n"
        f"📌 *Hozir navbatdasiz. Buyurtma kelishini kuting yoki navbatni kuzating.*", 
        reply_markup=keyboard, 
        parse_mode="Markdown"
    )
    await state.clear()


@router.message(F.text == "🏠 Asosiy menyu")
async def back_to_main_menu_general(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@router.message(F.text == "❌ Navbatdan chiqish")
async def driver_leave_queue(message: Message):
    driver_id = message.from_user.id
    removed = False
    for direction in drivers_queues:
        for d in drivers_queues[direction]:
            if d["id"] == driver_id:
                drivers_queues[direction].remove(d)
                removed = True

    if removed:
        await message.answer("Siz navbatdan chiqarildingiz.", reply_markup=main_menu())
    else:
        await message.answer("Siz hozirda hech qanday navbatda emassiz.", reply_markup=main_menu())


@router.message(F.text == "📋 Navbat ro'yxati")
async def show_queue_list(message: Message):
    driver_id = message.from_user.id
    my_direction = None
    for direction in drivers_queues:
        if any(d["id"] == driver_id for d in drivers_queues[direction]):
            my_direction = direction
            break

    if not my_direction:
        await message.answer("Siz hozirda hech qanday yo'nalish navbatida emassiz!")
        return

    queue_text = f"📋 **{my_direction}** yo'nalishi bo'yicha navbat:\n\n"
    queue = drivers_queues[my_direction]
    
    if not queue:
        queue_text += "Hozircha navbatda haydovchilar yo'q."
    else:
        for idx, driver in enumerate(queue, 1):
            status_text = f" (Birinchi 🚗 - Bo'sh joy: {driver['seats']} ta)" if idx == 1 else f" (Bo'sh joy: {driver['seats']} ta)"
            queue_text += f"{idx}. {driver['name']}{status_text}\n"

    await message.answer(queue_text, parse_mode="Markdown")


# ==========================================
#      FIFO & TAYMER & JOY TEKSHIRISH MANTIQ
# ==========================================

async def send_order_to_next_driver(direction, order_data):
    if not drivers_queues[direction]:
        try:
            await bot.send_message(order_data["passenger_id"], "😔 Afsuski, hozirda bo'sh haydovchilar topilmadi.")
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

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"✅ Qabul qilish_{order_data['passenger_id']}")],
            [KeyboardButton(text=f"❌ Rad etish_{order_data['passenger_id']}")],
        ],
        resize_keyboard=True,
    )

    text = (
        f"🚨 **Yangi buyurtma!**\n\n"
        f"📍 Yo'nalish: {direction}\n"
        f"👥 Yo'lovchilar soni: {order_data['count']} ta\n"
        f"💺 Sizning bo'sh joyingiz: {current_driver['seats']} ta\n\n"
        f"⏱ *10 soniya ichida qabul qilmasangiz, buyurtma keyingi haydovchiga o'tadi!*"
    )

    sent_msg = await bot.send_message(driver_id, text, reply_markup=keyboard, parse_mode="Markdown")

    async def timeout_task():
        await asyncio.sleep(10)
        if order_data["passenger_id"] in active_orders:
            del active_orders[order_data["passenger_id"]]
            try:
                await bot.edit_message_text(
                    chat_id=driver_id,
                    message_id=sent_msg.message_id,
                    text="❌ Vaqt tugadi! Buyurtma boshqa haydovchiga o'tkazildi."
                )
            except:
                pass
            
            if drivers_queues[direction] and drivers_queues[direction][0]["id"] == driver_id:
                d = drivers_queues[direction].pop(0)
                drivers_queues[direction].append(d)

            await send_order_to_next_driver(direction, order_data)

    active_orders[order_data["passenger_id"]] = asyncio.create_task(timeout_task())


@router.message(F.text.startswith("✅ Qabul qilish_"))
async def accept_order(message: Message):
    try:
        passenger_id = int(message.text.split("_")[1])
    except (IndexError, ValueError):
        return

    driver_id = message.from_user.id

    if passenger_id in active_orders:
        active_orders[passenger_id].cancel()
        del active_orders[passenger_id]

        order_info = pending_orders.get(passenger_id, {})
        p_phone = order_info.get("phone", "")
        p_name = order_info.get("passenger_name", "Yo'lovchi")
        p_count = order_info.get("count", 1)
        p_phone_link = f"tel:{p_phone}"

        for direction in drivers_queues:
            for d in drivers_queues[direction]:
                if d["id"] == driver_id:
                    d["seats"] -= p_count
                    
                    if d["seats"] <= 0:
                        drivers_queues[direction].remove(d)
                        await message.answer(
                            f"✅ **Buyurtmani qabul qildingiz!**\n\n"
                            f"👤 Yo'lovchi: {p_name}\n"
                            f"📞 Telefon: [{p_phone}]({p_phone_link})\n"
                            f"👥 Soni: {p_count} ta\n\n"
                            f"🚗 **Mashinangiz to'ldi! Siz navbatdan chiqarildingiz.**",
                            reply_markup=main_menu(),
                            parse_mode="Markdown"
                        )
                    else:
                        drivers_queues[direction].remove(d)
                        drivers_queues[direction].append(d)
                        await message.answer(
                            f"✅ **Buyurtmani qabul qildingiz!**\n\n"
                            f"👤 Yo'lovchi: {p_name}\n"
                            f"📞 Telefon: [{p_phone}]({p_phone_link})\n"
                            f"👥 Soni: {p_count} ta\n"
                            f"💺 Qolgan bo'sh joy: {d['seats']} ta",
                            reply_markup=main_menu(),
                            parse_mode="Markdown"
                        )
                    break

        d_info = drivers_db.get(driver_id, {})
        d_car = d_info.get("car", "Noma'lum")
        d_num = d_info.get("number", "Noma'lum")
        d_name = d_info.get("name", "Haydovchi")
        d_phone = d_info.get("phone", "Noma'lum")
        d_phone_link = f"tel:{d_phone}"

        try:
            await bot.send_message(
                passenger_id,
                f"🎉 **Haydovchi buyurtmangizni qabul qildi!**\n\n"
                f"🚗 Mashina: {d_car} ({d_num})\n"
                f"👤 Haydovchi: {d_name}\n"
                f"📞 Telefon: [{d_phone}]({d_phone_link})\n\n"
                f"⏳ **Haydovchi siz bilan bog'lanadi, kutib turing...**",
                parse_mode="Markdown"
            )
        except:
            pass

    else:
        await message.answer("Bu buyurtma vaqti o'tib ketgan yoki allaqachon olingan.", reply_markup=main_menu())


@router.message(F.text.startswith("❌ Rad etish_"))
async def reject_order(message: Message):
    try:
        passenger_id = int(message.text.split("_")[1])
    except (IndexError, ValueError):
        return

    driver_id = message.from_user.id

    if passenger_id in active_orders:
        active_orders[passenger_id].cancel()
        del active_orders[passenger_id]

        await message.answer("❌ Buyurtmani rad etdingiz.", reply_markup=main_menu())

        for direction in drivers_queues:
            if drivers_queues[direction] and drivers_queues[direction][0]["id"] == driver_id:
                d = drivers_queues[direction].pop(0)
                drivers_queues[direction].append(d)
                
                if passenger_id in pending_orders:
                    await send_order_to_next_driver(pending_orders[passenger_id]["direction"], pending_orders[passenger_id])
                break
    else:
        await message.answer("Bu buyurtma allaqachon yakunlangan.", reply_markup=main_menu())


# Botni ishga tushirish
async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
