import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# BOT TOKEN
TOKEN = "9009245143:AAFUPCxK636Fn766dFxhezIlGugL1XnLzDE"
bot = Bot(token=TOKEN)
dp = Dispatcher()

# MA'LUMOTLAR OMBORI
drivers_db = {}
queues = {"D-Q": [], "Q-D": []}
active_orders = {}

# RO'YXATDAN O'TISH BOSQICHLARI
class DriverReg(StatesGroup):
    car_name = State()
    car_plate = State()
    name = State()
    phone = State()

class ClientOrder(StatesGroup):
    direction = State()
    seats = State()
    phone = State()

# --- START ---
@dp.message(CommandStart())
async def welcome(message: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Haydovchi"), KeyboardButton(text="👤 Yo'lovchi")]
        ],
        resize_keyboard=True
    )
    await message.answer("Assalomu alaykum! Rolingizni tanlang:", reply_markup=kb)

# ================= HAYDOVCHI QISMI =================

@dp.message(F.text == "🚖 Haydovchi")
async def dr_start(message: Message, state: FSMContext):
    cid = message.chat.id
    if cid in drivers_db:
        await show_menu(message)
    else:
        await message.answer("Siz birinchi marta kirdingiz. Iltimos ro'yxatdan o'ting.\n\nAvtomashina nomini kiriting:")
        await state.set_state(DriverReg.car_name)

@dp.message(DriverReg.car_name)
async def dr_car(message: Message, state: FSMContext):
    await state.update_data(c_name=message.text)
    await message.answer("Avto raqamni kiriting (Masalan: AB123C):")
    await state.set_state(DriverReg.car_plate)

@dp.message(DriverReg.car_plate)
async def dr_plate(message: Message, state: FSMContext):
    await state.update_data(c_plate=str(message.text).upper())
    await message.answer("Ismingizni kiriting:")
    await state.set_state(DriverReg.name)

@dp.message(DriverReg.name)
async def dr_name(message: Message, state: FSMContext):
    await state.update_data(d_name=message.text)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=kb)
    await state.set_state(DriverReg.phone)

@dp.message(DriverReg.phone, F.contact)
async def dr_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    cid = message.chat.id
    drivers_db[cid] = {
        "car": data['c_name'],
        "plate": data['c_plate'],
        "name": data['d_name'],
        "phone": message.contact.phone_number,
        "capacity": 4
    }
    await message.answer("🎉 Ro'yxatdan muvaffaqiyatli o'tdingiz!")
    await state.clear()
    await show_menu(message)

async def show_menu(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 DO'STLIKDAN-QAHRAMONGA")],
            [KeyboardButton(text="📍 QAXRAMONDAN-DO'STLIKGA")],
            [KeyboardButton(text="⬅️ Bosh menyu")]
        ],
        resize_keyboard=True
    )
    await message.answer("Qaysi yo'nalish bo'yicha navbatga turasiz?", reply_markup=kb)

@dp.message(F.text.in_({"📍 DO'STLIKDAN-QAHRAMONGA", "📍 QAXRAMONDAN-DO'STLIKGA"}))
async def dr_queue(message: Message):
    cid = message.chat.id
    if cid not in drivers_db:
        await message.answer("Avval ro'yxatdan o'ting!")
        return
    
    code = "D-Q" if "DO'STLIKDAN" in message.text else "Q-D"
    
    if cid in queues["D-Q"]: queues["D-Q"].remove(cid)
    if cid in queues["Q-D"]: queues["Q-D"].remove(cid)
    
    queues[code].append(cid)
    drivers_db[cid]["capacity"] = 4
    
    pos = queues[code].index(cid) + 1
    await message.answer(f"✅ Navbatga turdingiz!\nSizning navbatingiz: {pos}-o'rin.")

# ================= YO'LOVCHI QISMI =================

@dp.message(F.text == "👤 Yo'lovchi")
async def cl_start(message: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚕 DO'STLIK -> QAHRAMON")],
            [KeyboardButton(text="🚕 QAHRAMON -> DO'STLIK")],
            [KeyboardButton(text="⬅️ Bosh menyu")]
        ],
        resize_keyboard=True
    )
    await message.answer("Qaysi yo'nalishda ketasiz?", reply_markup=kb)

@dp.message(F.text.in_({"🚕 DO'STLIK -> QAHRAMON", "🚕 QAHRAMON -> DO'STLIK"}))
async def cl_dir(message: Message, state: FSMContext):
    code = "D-Q" if "DO'STLIK" in message.text else "Q-D"
    await state.update_data(dir_code=code)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2")],
            [KeyboardButton(text="3"), KeyboardButton(text="4")]
        ],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Odam sonini tanlang:", reply_markup=kb)
    await state.set_state(ClientOrder.seats)

@dp.message(ClientOrder.seats, F.text.in_({"1", "2", "3", "4"}))
async def cl_seats(message: Message, state: FSMContext):
    await state.update_data(seat_count=int(message.text))
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=kb)
    await state.set_state(ClientOrder.phone)

@dp.message(ClientOrder.phone, F.contact)
async def cl_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    code = data['dir_code']
    seats = data['seat_count']
    p_phone = message.contact.phone_number
    pid = message.chat.id
    p_name = message.from_user.full_name
    
    await message.answer("🔍 Birinchi navbatdagi haydovchi qidirilmoqda...", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Bosh menyu")]], resize_keyboard=True))
    
    if not queues[code]:
        await message.answer("Bu yo'nalishda navbatda haydovchi yo'q.")
        await state.clear()
        return
        
    did = queues[code][0]
    d_info = drivers_db[did]
    
    if d_info["capacity"] < seats:
        await message.answer("Birinchi haydovchida joy yetarli emas. Navbat kutishingizni so'raymiz.")
        await state.clear()
        return

    kb_dr = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Qabul", callback_data=f"y_{pid}_{seats}_{code}"),
            InlineKeyboardButton(text="❌ Rad", callback_data=f"n_{pid}")
        ]]
    )
    
    try:
        txt = f"🔔 Yangi buyurtma!\n👤 Yo'lovchi: {p_name}\n👥 Odam soni: {seats} ta\n📞 Tel: {p_phone}"
        await bot.send_message(chat_id=did, text=txt, reply_markup=kb_dr)
        active_orders[pid] = {"phone": p_phone, "name": p_name}
        await message.answer("⏳ So'rov birinchi haydovchiga yuborildi...")
    except:
        await message.answer("Haydovchiga bog'lanishda xato bo'ldi.")
    await state.clear()

# ================= CALLBACKS =================

@dp.callback_query(F.data.startswith("y_"))
async def accept_order(callback: CallbackQuery):
    _, p_id, seats_str, code = callback.data.split("_")
    pid = int(p_id)
    seats = int(seats_str)
    did = callback.message.chat.id
    
    d_info = drivers_db[did]
    p_info = active_orders.get(pid, {"name": "Yo'lovchi", "phone": "--"})
    
    d_info["capacity"] -= seats
    
    await callback.message.edit_text(
        text=f"✅ Buyurtma qabul qilindi!\n👤 Yo'lovchi: {p_info['name']}\n📞 Tel: {p_info['phone']}\n🪑 Bo'sh joyingiz qoldi: {d_info['capacity']}"
    )
    
    try:
        p_txt = f"🚀 Haydovchi qabul qildi!\n👨‍✈️: {d_info['name']}\n🚖: {d_info['car']}\n🔢: {d_info['plate']}\n📞: {d_info['phone']}"
        await bot.send_message(chat_id=pid, text=p_txt)
    except:
        pass

    if d_info["capacity"] <= 0:
        queues[code].pop(0)
        await bot.send_message(chat_id=did, text="🫗 Mashinangiz to'ldi va navbatdan chiqdingiz.")
    await callback.answer()

@dp.callback_query(F.data.startswith("n_"))
async def reject_order(callback: CallbackQuery):
    pid = int(callback.data.split("_")[1])
    await callback.message.edit_text(text="❌ Buyurtmani rad etdingiz.")
    try:
        await bot.send_message(chat_id=pid, text="😔 Haydovchi buyurtmangizni rad etdi.")
    except:
        pass
    await callback.answer()

@dp.message(F.text == "⬅️ Bosh menyu")
async def menu_back(message: Message, state: FSMContext):
    await state.clear()
    await welcome(message, state)

async def main():
    print("Mantiqiy Taksi boti xatoliklarsiz ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
