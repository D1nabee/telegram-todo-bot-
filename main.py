import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

TASKS_FILE = "tasks.json"
STATS_FILE = "stats.json"

# States
class TaskStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_deadline = State()
    waiting_for_reminder_time = State()

# Load/Save functions
def load_data(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

tasks = load_data(TASKS_FILE)
stats = load_data(STATS_FILE)

# Initialize user data
def init_user(user_id):
    uid = str(user_id)
    if uid not in tasks:
        tasks[uid] = {"active": [], "archive": []}
    if uid not in stats:
        stats[uid] = {
            "completed": 0,
            "streak": 0,
            "last_completed": None,
            "reminder_time": "09:00"
        }

# Keyboards
def main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ add task", callback_data="add_task"),
            InlineKeyboardButton(text="📋 list", callback_data="show_list")
        ],
        [
            InlineKeyboardButton(text="✅ complete", callback_data="complete_task"),
            InlineKeyboardButton(text="📊 stats", callback_data="show_stats")
        ],
        [
            InlineKeyboardButton(text="🗄 archive", callback_data="show_archive"),
            InlineKeyboardButton(text="⚙️ settings", callback_data="settings")
        ]
    ])
    return keyboard

def task_list_keyboard(user_id, action="complete"):
    uid = str(user_id)
    keyboard = []
    
    for i, task in enumerate(tasks[uid]["active"]):
        priority = "⭐ " if task.get("priority") else ""
        deadline = f" | {task['deadline']}" if task.get("deadline") else ""
        text = f"{priority}{task['text'][:30]}{deadline}"
        keyboard.append([InlineKeyboardButton(
            text=text,
            callback_data=f"{action}_{i}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="« back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def priority_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ high priority", callback_data="priority_high"),
            InlineKeyboardButton(text="normal", callback_data="priority_normal")
        ],
        [InlineKeyboardButton(text="« cancel", callback_data="back_to_main")]
    ])
    return keyboard

def deadline_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="today", callback_data="deadline_today"),
            InlineKeyboardButton(text="tomorrow", callback_data="deadline_tomorrow")
        ],
        [
            InlineKeyboardButton(text="in 3 days", callback_data="deadline_3days"),
            InlineKeyboardButton(text="no deadline", callback_data="deadline_none")
        ],
        [InlineKeyboardButton(text="« back", callback_data="back_to_main")]
    ])
    return keyboard

# Commands
@dp.message(Command("start"))
async def cmd_start(message: Message):
    init_user(message.from_user.id)
    
    await message.answer(
        f"*{message.from_user.first_name}.*\n\n"
        "execution doesn't forget. doesn't forgive incomplete.\n\n"
        "add. complete. or watch the list grow.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# Callback handlers
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "execution.",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "add_task")
async def add_task_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("send task:")
    await state.set_state(TaskStates.waiting_for_task)
    await callback.answer()

@dp.message(TaskStates.waiting_for_task)
async def receive_task(message: Message, state: FSMContext):
    await state.update_data(task_text=message.text.strip())
    await message.answer(
        "priority?",
        reply_markup=priority_keyboard()
    )

@dp.callback_query(F.data.startswith("priority_"))
async def set_priority(callback: CallbackQuery, state: FSMContext):
    priority = callback.data == "priority_high"
    await state.update_data(priority=priority)
    
    await callback.message.edit_text(
        "deadline?",
        reply_markup=deadline_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("deadline_"))
async def set_deadline(callback: CallbackQuery, state: FSMContext):
    deadline_type = callback.data.replace("deadline_", "")
    
    deadline = None
    if deadline_type == "today":
        deadline = datetime.now().strftime("%Y-%m-%d")
    elif deadline_type == "tomorrow":
        deadline = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif deadline_type == "3days":
        deadline = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    
    data = await state.get_data()
    user_id = str(callback.from_user.id)
    
    task = {
        "text": data["task_text"],
        "priority": data.get("priority", False),
        "deadline": deadline,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    tasks[user_id]["active"].append(task)
    save_data(TASKS_FILE, tasks)
    
    responses = [
        f"noted. total: {len(tasks[user_id]['active'])}",
        f"added. queue: {len(tasks[user_id]['active'])}",
        f"recorded. {len(tasks[user_id]['active'])} pending."
    ]
    
    await callback.message.edit_text(
        random.choice(responses),
        reply_markup=main_keyboard()
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "show_list")
async def show_list(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    init_user(callback.from_user.id)
    
    if not tasks[user_id]["active"]:
        await callback.message.edit_text(
            "clean.\nfor now.",
            reply_markup=main_keyboard()
        )
        await callback.answer()
        return
    
    result = "*tasks:*\n\n"
    for i, task in enumerate(tasks[user_id]["active"], 1):
        priority = "⭐ " if task.get("priority") else ""
        deadline = f" `[{task['deadline']}]`" if task.get("deadline") else ""
        result += f"{i}. {priority}{task['text']}{deadline}\n"
    
    await callback.message.edit_text(
        result,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "complete_task")
async def complete_task_start(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if not tasks[user_id]["active"]:
        await callback.message.edit_text(
            "no tasks to complete.",
            reply_markup=main_keyboard()
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "which task?",
        reply_markup=task_list_keyboard(callback.from_user.id, "do")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("do_"))
async def complete_task(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    task_index = int(callback.data.split("_")[1])
    
    completed_task = tasks[user_id]["active"].pop(task_index)
    completed_task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    tasks[user_id]["archive"].append(completed_task)
    
    # Update stats
    stats[user_id]["completed"] += 1
    today = datetime.now().strftime("%Y-%m-%d")
    
    if stats[user_id]["last_completed"] == today:
        pass  # same day
    elif stats[user_id]["last_completed"] == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"):
        stats[user_id]["streak"] += 1  # consecutive day
    else:
        stats[user_id]["streak"] = 1  # reset streak
    
    stats[user_id]["last_completed"] = today
    
    save_data(TASKS_FILE, tasks)
    save_data(STATS_FILE, stats)
    
    await callback.message.edit_text(
        f"'{completed_task['text']}' — closed.\n"
        f"remaining: {len(tasks[user_id]['active'])}",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "show_stats")
async def show_stats(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    init_user(callback.from_user.id)
    
    user_stats = stats[user_id]
    active_count = len(tasks[user_id]["active"])
    
    result = (
        f"*statistics:*\n\n"
        f"📋 active tasks: `{active_count}`\n"
        f"✅ completed: `{user_stats['completed']}`\n"
        f"🔥 streak: `{user_stats['streak']}` days\n"
        f"📅 last completed: `{user_stats['last_completed'] or 'never'}`"
    )
    
    await callback.message.edit_text(
        result,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "show_archive")
async def show_archive(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if not tasks[user_id]["archive"]:
        await callback.message.edit_text(
            "archive empty.",
            reply_markup=main_keyboard()
        )
        await callback.answer()
        return
    
    result = "*archive:*\n\n"
    for task in tasks[user_id]["archive"][-10:]:  # last 10
        result += f"✓ {task['text']}\n  `{task.get('completed_at', 'unknown')}`\n\n"
    
    await callback.message.edit_text(
        result,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    reminder_time = stats[user_id].get("reminder_time", "09:00")
    
    await callback.message.edit_text(
        f"*settings:*\n\n"
        f"daily reminder: `{reminder_time}`\n\n"
        f"send /setreminder HH:MM to change\n"
        f"example: /setreminder 09:00",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.message(Command("setreminder"))
async def set_reminder(message: Message):
    try:
        time_str = message.text.split()[1]
        datetime.strptime(time_str, "%H:%M")  # validate format
        
        user_id = str(message.from_user.id)
        stats[user_id]["reminder_time"] = time_str
        save_data(STATS_FILE, stats)
        
        await message.answer(f"reminder set to {time_str}")
    except:
        await message.answer("invalid format. use: /setreminder HH:MM")

# Daily reminder task
async def send_daily_reminders():
    while True:
        now = datetime.now()
        
        for user_id, user_stats in stats.items():
            reminder_time = user_stats.get("reminder_time", "09:00")
            hour, minute = map(int, reminder_time.split(":"))
            
            if now.hour == hour and now.minute == minute:
                if user_id in tasks and tasks[user_id]["active"]:
                    count = len(tasks[user_id]["active"])
                    priority_count = sum(1 for t in tasks[user_id]["active"] if t.get("priority"))
                    
                    msg = f"morning.\n\n{count} tasks pending."
                    if priority_count:
                        msg += f"\n{priority_count} high priority."
                    msg += "\n\nmove."
                    
                    try:
                        await bot.send_message(
                            user_id,
                            msg,
                            reply_markup=main_keyboard()
                        )
                    except:
                        pass  # user blocked bot
        
        await asyncio.sleep(60)  # check every minute

# Main
async def main():
    print("execution online.")
    
    # Start reminder task
    asyncio.create_task(send_daily_reminders())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
