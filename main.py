import asyncio
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "8545660445:AAGFC04Nv1rbtflWwb01bXWGdZ4tzaVr4LI"

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

TASKS_FILE = "tasks.json"

# Состояния для добавления задачи
class TaskStates(StatesGroup):
    waiting_for_task = State()

# Загрузка задач
def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Сохранение задач
def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

tasks = load_tasks()

# Клавиатура с кнопками
def get_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ добавить"), KeyboardButton(text="📋 список")],
            [KeyboardButton(text="✅ выполнить"), KeyboardButton(text="🗑 очистить")]
        ],
        resize_keyboard=True
    )
    return keyboard

@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.answer(
        "to-do bot.\n\n"
        "используй кнопки ниже.",
        reply_markup=get_keyboard()
    )

# Кнопка "добавить"
@dp.message(F.text == "➕ добавить")
async def button_add(message: Message, state: FSMContext):
    await message.answer("напиши задачу:")
    await state.set_state(TaskStates.waiting_for_task)

# Получение текста задачи
@dp.message(TaskStates.waiting_for_task)
async def receive_task(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    task = message.text.strip()
    
    if user_id not in tasks:
        tasks[user_id] = []
    
    tasks[user_id].append(task)
    save_tasks(tasks)
    
    await message.answer(
        f"добавлено. всего задач: {len(tasks[user_id])}",
        reply_markup=get_keyboard()
    )
    await state.clear()

# Кнопка "список"
@dp.message(F.text == "📋 список")
async def button_list(message: Message):
    user_id = str(message.from_user.id)
    
    if user_id not in tasks or not tasks[user_id]:
        await message.answer("нет задач.")
        return
    
    result = "задачи:\n\n"
    for i, task in enumerate(tasks[user_id], 1):
        result += f"{i}. {task}\n"
    
    await message.answer(result)

# Кнопка "выполнить"
@dp.message(F.text == "✅ выполнить")
async def button_done(message: Message):
    user_id = str(message.from_user.id)
    
    if user_id not in tasks or not tasks[user_id]:
        await message.answer("нет задач.")
        return
    
    result = "какую задачу выполнил? напиши номер:\n\n"
    for i, task in enumerate(tasks[user_id], 1):
        result += f"{i}. {task}\n"
    
    await message.answer(result)

# Получение номера выполненной задачи
@dp.message(F.text.regexp(r'^\d+$'))
async def handle_done_number(message: Message):
    user_id = str(message.from_user.id)
    
    try:
        num = int(message.text) - 1
        
        if user_id not in tasks or not tasks[user_id]:
            await message.answer("нет задач.")
            return
        
        if 0 <= num < len(tasks[user_id]):
            removed = tasks[user_id].pop(num)
            save_tasks(tasks)
            await message.answer(f"выполнено: {removed}", reply_markup=get_keyboard())
        else:
            await message.answer("нет такой задачи.")
    except:
        pass

# Кнопка "очистить"
@dp.message(F.text == "🗑 очистить")
async def button_clear(message: Message):
    user_id = str(message.from_user.id)
    tasks[user_id] = []
    save_tasks(tasks)
    await message.answer("все удалено.")

async def main():
    print("бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())