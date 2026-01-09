import asyncio
import json
import os
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

DATA_FILE = "execution_data.json"

# States
class TaskStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_time = State()
    waiting_for_deadline = State()

# Load/Save
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# Initialize user
def init_user(user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "recurring": [],      # daily tasks with time
            "one_time": [],       # today's tasks
            "long_term": [],      # goals with deadlines
            "history": {},        # completion history
            "stats": {
                "total_completed": 0,
                "best_streak": 0
            }
        }
        save_data(data)

# Keyboards
def main_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ add task", callback_data="add_task"),
            InlineKeyboardButton(text="📋 today", callback_data="show_today")
        ],
        [
            InlineKeyboardButton(text="🔄 recurring", callback_data="show_recurring"),
            InlineKeyboardButton(text="🎯 long-term", callback_data="show_longterm")
        ],
        [
            InlineKeyboardButton(text="📊 stats", callback_data="show_stats"),
            InlineKeyboardButton(text="📅 history", callback_data="show_history")
        ]
    ])
    return kb

def task_type_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 recurring (daily)", callback_data="type_recurring")],
        [InlineKeyboardButton(text="📌 one-time (today)", callback_data="type_onetime")],
        [InlineKeyboardButton(text="🎯 long-term (deadline)", callback_data="type_longterm")],
        [InlineKeyboardButton(text="« cancel", callback_data="back_to_main")]
    ])
    return kb

def time_hours_keyboard():
    buttons = []
    for hour in range(0, 24, 3):
        row = []
        for h in range(hour, min(hour + 3, 24)):
            row.append(InlineKeyboardButton(
                text=f"{h:02d}:xx",
                callback_data=f"hour_{h}"
            ))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="« cancel", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def time_minutes_keyboard(hour):
    buttons = []
    for minute in [0, 15, 30, 45]:
        buttons.append([InlineKeyboardButton(
            text=f"{hour:02d}:{minute:02d}",
            callback_data=f"time_{hour:02d}:{minute:02d}"
        )])
    buttons.append([InlineKeyboardButton(text="« back", callback_data="select_hour")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def task_action_keyboard(task_id, task_type):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ done", callback_data=f"complete_{task_type}_{task_id}"),
            InlineKeyboardButton(text="⏭ skip", callback_data=f"skip_{task_type}_{task_id}")
        ],
        [InlineKeyboardButton(text="🗑 delete", callback_data=f"delete_{task_type}_{task_id}")]
    ])
    return kb

def deadline_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 week", callback_data="deadline_7"),
            InlineKeyboardButton(text="2 weeks", callback_data="deadline_14")
        ],
        [
            InlineKeyboardButton(text="1 month", callback_data="deadline_30"),
            InlineKeyboardButton(text="3 months", callback_data="deadline_90")
        ],
        [InlineKeyboardButton(text="« cancel", callback_data="back_to_main")]
    ])
    return kb

# Commands
@dp.message(Command("start"))
async def cmd_start(message: Message):
    init_user(message.from_user.id)
    
    await message.answer(
        f"*{message.from_user.first_name}.*\n\n"
        "execution. habits. discipline. results.\n\n"
        "build your routine. track progress. no excuses.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# Main menu
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "execution.",
        reply_markup=main_keyboard()
    )
    await callback.answer()

# Add task flow
@dp.callback_query(F.data == "add_task")
async def add_task_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "task type?",
        reply_markup=task_type_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("type_"))
async def select_task_type(callback: CallbackQuery, state: FSMContext):
    task_type = callback.data.replace("type_", "")
    await state.update_data(task_type=task_type)
    
    await callback.message.edit_text("task name:")
    await state.set_state(TaskStates.waiting_for_name)
    await callback.answer()

@dp.message(TaskStates.waiting_for_name)
async def receive_task_name(message: Message, state: FSMContext):
    await state.update_data(task_name=message.text.strip())
    state_data = await state.get_data()
    task_type = state_data["task_type"]
    
    if task_type in ["recurring", "onetime"]:
        await message.answer("select time:", reply_markup=time_hours_keyboard())
    else:  # longterm
        await message.answer("deadline?", reply_markup=deadline_keyboard())
        await state.set_state(TaskStates.waiting_for_deadline)

@dp.callback_query(F.data == "select_hour")
async def select_hour_again(callback: CallbackQuery):
    await callback.message.edit_text("select time:", reply_markup=time_hours_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("hour_"))
async def select_hour(callback: CallbackQuery):
    hour = int(callback.data.replace("hour_", ""))
    await callback.message.edit_text(
        f"select minutes for {hour:02d}:xx",
        reply_markup=time_minutes_keyboard(hour)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("time_"))
async def receive_time(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.replace("time_", "")
    state_data = await state.get_data()
    
    user_id = str(callback.from_user.id)
    task_type = state_data["task_type"]
    task_name = state_data["task_name"]
    
    new_task = {
        "name": task_name,
        "time": time_str,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed_today": False
    }
    
    if task_type == "recurring":
        data[user_id]["recurring"].append(new_task)
        msg = f"recurring task added.\n`{task_name}` at `{time_str}` daily."
    else:  # onetime
        data[user_id]["one_time"].append(new_task)
        msg = f"task added for today.\n`{task_name}` at `{time_str}`."
    
    save_data(data)
    
    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data.startswith("deadline_"))
async def receive_deadline(callback: CallbackQuery, state: FSMContext):
    days = int(callback.data.replace("deadline_", ""))
    deadline = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    
    state_data = await state.get_data()
    user_id = str(callback.from_user.id)
    task_name = state_data["task_name"]
    
    new_task = {
        "name": task_name,
        "deadline": deadline,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed": False
    }
    
    data[user_id]["long_term"].append(new_task)
    save_data(data)
    
    await callback.message.edit_text(
        f"long-term goal added.\n`{task_name}`\ndeadline: `{deadline}`",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await state.clear()
    await callback.answer()

# Show tasks
@dp.callback_query(F.data == "show_today")
async def show_today(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    init_user(callback.from_user.id)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Combine recurring and one-time tasks for today
    all_tasks = []
    
    for i, task in enumerate(data[user_id]["recurring"]):
        all_tasks.append((task["time"], "recurring", i, task))
    
    for i, task in enumerate(data[user_id]["one_time"]):
        all_tasks.append((task["time"], "onetime", i, task))
    
    all_tasks.sort(key=lambda x: x[0])  # sort by time
    
    if not all_tasks:
        await callback.message.edit_text(
            "no tasks for today.\nadd some.",
            reply_markup=main_keyboard()
        )
        await callback.answer()
        return
    
    msg = "*today's schedule:*\n\n"
    
    for time, task_type, idx, task in all_tasks:
        status = "✅" if task.get("completed_today") else "⏸"
        msg += f"`{time}` {status} {task['name']}\n"
    
    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "show_recurring")
async def show_recurring(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if not data[user_id]["recurring"]:
        await callback.message.edit_text(
            "no recurring tasks.\nadd daily habits.",
            reply_markup=main_keyboard()
        )
        await callback.answer()
        return
    
    msg = "*recurring tasks:*\n\n"
    
    for i, task in enumerate(data[user_id]["recurring"]):
        msg += f"{i+1}. `{task['time']}` — {task['name']}\n"
    
    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "show_longterm")
async def show_longterm(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if not data[user_id]["long_term"]:
        await callback.message.edit_text(
            "no long-term goals.\nset some.",
            reply_markup=main_keyboard()
        )
        await callback.answer()
        return
    
    msg = "*long-term goals:*\n\n"
    
    for i, task in enumerate(data[user_id]["long_term"]):
        status = "✅" if task.get("completed") else "⏳"
        days_left = (datetime.strptime(task["deadline"], "%Y-%m-%d") - datetime.now()).days
        msg += f"{status} {task['name']}\n   `deadline: {task['deadline']}` ({days_left} days)\n\n"
    
    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

# Complete/Skip tasks
@dp.callback_query(F.data.startswith("complete_"))
async def complete_task(callback: CallbackQuery):
    parts = callback.data.split("_")
    task_type = parts[1]
    task_id = int(parts[2])
    user_id = str(callback.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if task_type == "recurring":
        task = data[user_id]["recurring"][task_id]
        task["completed_today"] = True
        
        # Save to history
        if today not in data[user_id]["history"]:
            data[user_id]["history"][today] = {}
        data[user_id]["history"][today][task["name"]] = "done"
        
    elif task_type == "onetime":
        task = data[user_id]["one_time"].pop(task_id)
        
        if today not in data[user_id]["history"]:
            data[user_id]["history"][today] = {}
        data[user_id]["history"][today][task["name"]] = "done"
        
    elif task_type == "longterm":
        data[user_id]["long_term"][task_id]["completed"] = True
    
    data[user_id]["stats"]["total_completed"] += 1
    save_data(data)
    
    await callback.message.edit_text(
        "done.\nnext.",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("skip_"))
async def skip_task(callback: CallbackQuery):
    parts = callback.data.split("_")
    task_type = parts[1]
    task_id = int(parts[2])
    user_id = str(callback.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if task_type == "recurring":
        task = data[user_id]["recurring"][task_id]
        
        if today not in data[user_id]["history"]:
            data[user_id]["history"][today] = {}
        data[user_id]["history"][today][task["name"]] = "skipped"
        
    elif task_type == "onetime":
        data[user_id]["one_time"].pop(task_id)
    
    save_data(data)
    
    await callback.message.edit_text(
        "skipped.",
        reply_markup=main_keyboard()
    )
    await callback.answer()

# Stats
@dp.callback_query(F.data == "show_stats")
async def show_stats(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    total = data[user_id]["stats"]["total_completed"]
    
    # Calculate today's completion
    today = datetime.now().strftime("%Y-%m-%d")
    today_tasks = data[user_id]["recurring"] + data[user_id]["one_time"]
    completed_today = sum(1 for t in today_tasks if t.get("completed_today"))
    total_today = len(today_tasks)
    
    completion_rate = (completed_today / total_today * 100) if total_today > 0 else 0
    
    msg = (
        f"*statistics:*\n\n"
        f"✅ total completed: `{total}`\n"
        f"📋 today: `{completed_today}/{total_today}` ({completion_rate:.0f}%)\n"
        f"🔄 recurring habits: `{len(data[user_id]['recurring'])}`\n"
        f"🎯 long-term goals: `{len(data[user_id]['long_term'])}`"
    )
    
    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "show_history")
async def show_history(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if not data[user_id]["history"]:
        await callback.message.edit_text(
            "no history yet.\nstart completing tasks.",
            reply_markup=main_keyboard()
        )
        await callback.answer()
        return
    
    msg = "*history (last 7 days):*\n\n"
    
    # Get last 7 days
    for i in range(7):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        
        if date in data[user_id]["history"]:
            day_data = data[user_id]["history"][date]
            done_count = sum(1 for v in day_data.values() if v == "done")
            skip_count = sum(1 for v in day_data.values() if v == "skipped")
            
            msg += f"`{date}`: ✅ {done_count} | ⏭ {skip_count}\n"
        else:
            msg += f"`{date}`: —\n"
    
    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

# Reminder system
async def send_reminders():
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        
        for user_id, user_data in data.items():
            # Check recurring tasks
            for i, task in enumerate(user_data["recurring"]):
                if task["time"] == current_time and not task.get("completed_today"):
                    try:
                        await bot.send_message(
                            user_id,
                            f"*time.*\n\n{task['name']}",
                            parse_mode="Markdown",
                            reply_markup=task_action_keyboard(i, "recurring")
                        )
                    except:
                        pass
            
            # Check one-time tasks
            for i, task in enumerate(user_data["one_time"]):
                if task["time"] == current_time:
                    try:
                        await bot.send_message(
                            user_id,
                            f"*reminder.*\n\n{task['name']}",
                            parse_mode="Markdown",
                            reply_markup=task_action_keyboard(i, "onetime")
                        )
                    except:
                        pass
        
        # Reset "completed_today" at midnight
        if current_time == "00:00":
            for user_id in data:
                for task in data[user_id]["recurring"]:
                    task["completed_today"] = False
            save_data(data)
        
        await asyncio.sleep(60)  # check every minute

# Main
async def main():
    print("execution v3.0 online.")
    
    # Start reminder system
    asyncio.create_task(send_reminders())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
