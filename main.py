import asyncio
import json
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# =======================
# Bot setup
# =======================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DATA_FILE = "execution_data.json"

# =======================
# States
# =======================


class TaskStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_time = State()
    waiting_for_deadline = State()
    editing_name = State()
    editing_time = State()
    editing_deadline = State()


# =======================
# Load / Save
# =======================


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

# Track reminders sent
reminders_sent = {}

# =======================
# Utils
# =======================


def init_user(user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "recurring": [],
            "one_time": [],
            "long_term": [],
            "history": {},
            "stats": {
                "total_completed": 0,
                "best_streak": 0,
                "current_streak": 0,
            },
            "settings": {
                "evening_report_time": "22:00",
                "reminder_repeat": True,
            },
        }
        save_data(data)


def validate_time(time_str):
    pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    return re.match(pattern, time_str) is not None


def get_day_completion(user_id, date):
    uid = str(user_id)

    if date not in data[uid]["history"]:
        return 0

    day_data = data[uid]["history"][date]
    total = len(day_data)

    if total == 0:
        return 0

    completed = sum(1 for v in day_data.values() if v == "done")
    return int((completed / total) * 100)


def get_completion_emoji(rate):
    if rate >= 80:
        return "🟩"
    elif rate >= 50:
        return "🟨"
    elif rate > 0:
        return "🟧"
    else:
        return "⬜"


# =======================
# Keyboards
# =======================


def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ add task", callback_data="add_task"),
                InlineKeyboardButton(text="📋 today", callback_data="show_today"),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 recurring", callback_data="show_recurring"
                ),
                InlineKeyboardButton(
                    text="🎯 long-term", callback_data="show_longterm"
                ),
            ],
            [
                InlineKeyboardButton(text="📊 stats", callback_data="show_stats"),
                InlineKeyboardButton(
                    text="📅 calendar", callback_data="show_calendar"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📜 history", callback_data="show_history"
                ),
                InlineKeyboardButton(
                    text="⚙️ settings", callback_data="show_settings"
                ),
            ],
        ]
    )


def task_type_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 recurring (daily)",
                    callback_data="type_recurring",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📌 one-time (today)",
                    callback_data="type_onetime",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 long-term (goal)",
                    callback_data="type_longterm",
                )
            ],
            [InlineKeyboardButton(text="« cancel", callback_data="back_to_main")],
        ]
    )


def longterm_time_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏰ set time",
                    callback_data="longterm_with_time",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏸ no time",
                    callback_data="longterm_no_time",
                )
            ],
            [InlineKeyboardButton(text="« cancel", callback_data="back_to_main")],
        ]
    )


def deadline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1 week", callback_data="deadline_7"
                ),
                InlineKeyboardButton(
                    text="2 weeks", callback_data="deadline_14"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="1 month", callback_data="deadline_30"
                ),
                InlineKeyboardButton(
                    text="3 months", callback_data="deadline_90"
                ),
            ],
            [InlineKeyboardButton(text="« cancel", callback_data="back_to_main")],
        ]
    )


def task_action_keyboard(task_id, task_type):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ done",
                    callback_data=f"complete_{task_type}_{task_id}",
                ),
                InlineKeyboardButton(
                    text="⏭ skip",
                    callback_data=f"skip_{task_type}_{task_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ edit",
                    callback_data=f"edit_{task_type}_{task_id}",
                ),
                InlineKeyboardButton(
                    text="🗑 delete",
                    callback_data=f"delete_{task_type}_{task_id}",
                ),
            ],
        ]
    )


def edit_options_keyboard(task_type, task_id):
    buttons = [
        [
            InlineKeyboardButton(
                text="✏️ edit name",
                callback_data=f"editname_{task_type}_{task_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⏰ edit time",
                callback_data=f"edittime_{task_type}_{task_id}",
            )
        ],
    ]

    if task_type == "longterm":
        buttons.append(
            [
                InlineKeyboardButton(
                    text="📅 edit deadline",
                    callback_data=f"editdeadline_{task_type}_{task_id}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="« back", callback_data="back_to_main")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def task_list_keyboard(user_id, task_type, action="manage"):
    uid = str(user_id)
    keyboard = []

    tasks = data[uid][task_type]

    for i, task in enumerate(tasks):
        time_str = f" `{task.get('time')}`" if task.get("time") else ""
        deadline_str = (
            f" `[{task.get('deadline')}]`"
            if task.get("deadline")
            else ""
        )

        text = f"{i + 1}. {task['name']}{time_str}{deadline_str}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=text[:50],
                    callback_data=f"{action}_{task_type}_{i}",
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton(text="« back", callback_data="back_to_main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# =======================
# Commands / Main menu
# =======================


@dp.message(Command("start"))
async def cmd_start(message: Message):
    init_user(message.from_user.id)

    await message.answer(
        f"*{message.from_user.first_name}.*\n\n"
        "execution. habits. discipline. results.\n\n"
        "build your routine. track progress. no excuses.",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "execution.",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


# =======================
# Add task flow (start)
# =======================


@dp.callback_query(F.data == "add_task")
async def add_task_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "task type?",
        reply_markup=task_type_keyboard(),
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

    if task_type in ("recurring", "onetime"):
        await message.answer(
            "time?\n\n"
            "format: `HH:MM`\n"
            "example: `07:45` or `14:30`",
            parse_mode="Markdown",
        )
        await state.set_state(TaskStates.waiting_for_time)
    else:
        await message.answer(
            "set reminder time?",
            reply_markup=longterm_time_keyboard(),
        )
# =======================
# Add task flow (time / save)
# =======================


@dp.callback_query(F.data == "longterm_with_time")
async def longterm_with_time(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "time?\n\n"
        "format: `HH:MM`\n"
        "example: `07:45` or `14:30`",
        parse_mode="Markdown",
    )
    await state.update_data(longterm_has_time=True)
    await state.set_state(TaskStates.waiting_for_time)
    await callback.answer()


@dp.callback_query(F.data == "longterm_no_time")
async def longterm_no_time(callback: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    user_id = str(callback.from_user.id)
    task_name = state_data["task_name"]

    new_task = {
        "name": task_name,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed": False,
    }

    data[user_id]["long_term"].append(new_task)
    save_data(data)

    await callback.message.edit_text(
        f"long-term goal added.\n\n`{task_name}`\nno reminders. no deadline.",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await state.clear()
    await callback.answer()


@dp.message(TaskStates.waiting_for_time)
async def receive_time(message: Message, state: FSMContext):
    time_str = message.text.strip()

    if not validate_time(time_str):
        await message.answer(
            "invalid format.\n\n"
            "use: `HH:MM`\n"
            "example: `07:45` or `14:30`",
            parse_mode="Markdown",
        )
        return

    parts = time_str.split(":")
    time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    await state.update_data(task_time=time_str)
    state_data = await state.get_data()
    task_type = state_data["task_type"]

    if task_type == "longterm":
        await message.answer(
            "deadline?",
            reply_markup=deadline_keyboard(),
        )
    else:
        await save_task_with_time(message, state)


async def save_task_with_time(message: Message, state: FSMContext):
    state_data = await state.get_data()
    user_id = str(message.from_user.id)
    task_type = state_data["task_type"]
    task_name = state_data["task_name"]
    task_time = state_data["task_time"]

    new_task = {
        "name": task_name,
        "time": task_time,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed_today": False,
    }

    if task_type == "recurring":
        data[user_id]["recurring"].append(new_task)
        msg = (
            f"recurring task added.\n\n"
            f"`{task_name}`\n"
            f"time: `{task_time}` daily"
        )
    else:
        data[user_id]["one_time"].append(new_task)
        msg = (
            f"task added for today.\n\n"
            f"`{task_name}`\n"
            f"time: `{task_time}`"
        )

    save_data(data)

    await message.answer(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await state.clear()


@dp.callback_query(F.data.startswith("deadline_"))
async def receive_deadline(callback: CallbackQuery, state: FSMContext):
    days = int(callback.data.replace("deadline_", ""))
    deadline = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    state_data = await state.get_data()
    user_id = str(callback.from_user.id)
    task_name = state_data["task_name"]
    task_time = state_data.get("task_time")

    new_task = {
        "name": task_name,
        "deadline": deadline,
        "time": task_time,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed": False,
    }

    data[user_id]["long_term"].append(new_task)
    save_data(data)

    await callback.message.edit_text(
        f"long-term goal added.\n\n"
        f"`{task_name}`\n"
        f"deadline: `{deadline}`\n"
        f"reminder: `{task_time}` daily",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await state.clear()
    await callback.answer()

# =======================
# Add task flow (time / save)
# =======================


@dp.callback_query(F.data == "longterm_with_time")
async def longterm_with_time(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "time?\n\n"
        "format: `HH:MM`\n"
        "example: `07:45` or `14:30`",
        parse_mode="Markdown",
    )
    await state.update_data(longterm_has_time=True)
    await state.set_state(TaskStates.waiting_for_time)
    await callback.answer()


@dp.callback_query(F.data == "longterm_no_time")
async def longterm_no_time(callback: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    user_id = str(callback.from_user.id)
    task_name = state_data["task_name"]

    new_task = {
        "name": task_name,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed": False,
    }

    data[user_id]["long_term"].append(new_task)
    save_data(data)

    await callback.message.edit_text(
        f"long-term goal added.\n\n`{task_name}`\nno reminders. no deadline.",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await state.clear()
    await callback.answer()


@dp.message(TaskStates.waiting_for_time)
async def receive_time(message: Message, state: FSMContext):
    time_str = message.text.strip()

    if not validate_time(time_str):
        await message.answer(
            "invalid format.\n\n"
            "use: `HH:MM`\n"
            "example: `07:45` or `14:30`",
            parse_mode="Markdown",
        )
        return

    parts = time_str.split(":")
    time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    await state.update_data(task_time=time_str)
    state_data = await state.get_data()
    task_type = state_data["task_type"]

    if task_type == "longterm":
        await message.answer(
            "deadline?",
            reply_markup=deadline_keyboard(),
        )
    else:
        await save_task_with_time(message, state)


async def save_task_with_time(message: Message, state: FSMContext):
    state_data = await state.get_data()
    user_id = str(message.from_user.id)
    task_type = state_data["task_type"]
    task_name = state_data["task_name"]
    task_time = state_data["task_time"]

    new_task = {
        "name": task_name,
        "time": task_time,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed_today": False,
    }

    if task_type == "recurring":
        data[user_id]["recurring"].append(new_task)
        msg = (
            f"recurring task added.\n\n"
            f"`{task_name}`\n"
            f"time: `{task_time}` daily"
        )
    else:
        data[user_id]["one_time"].append(new_task)
        msg = (
            f"task added for today.\n\n"
            f"`{task_name}`\n"
            f"time: `{task_time}`"
        )

    save_data(data)

    await message.answer(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await state.clear()


@dp.callback_query(F.data.startswith("deadline_"))
async def receive_deadline(callback: CallbackQuery, state: FSMContext):
    days = int(callback.data.replace("deadline_", ""))
    deadline = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    state_data = await state.get_data()
    user_id = str(callback.from_user.id)
    task_name = state_data["task_name"]
    task_time = state_data.get("task_time")

    new_task = {
        "name": task_name,
        "deadline": deadline,
        "time": task_time,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "completed": False,
    }

    data[user_id]["long_term"].append(new_task)
    save_data(data)

    await callback.message.edit_text(
        f"long-term goal added.\n\n"
        f"`{task_name}`\n"
        f"deadline: `{deadline}`\n"
        f"reminder: `{task_time}` daily",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await state.clear()
    await callback.answer()


# =======================
# Edit task flow
# =======================


@dp.callback_query(F.data.startswith("edit_"))
async def edit_task(callback: CallbackQuery):
    _, task_type, task_id = callback.data.split("_")

    await callback.message.edit_text(
        "what to edit?",
        reply_markup=edit_options_keyboard(task_type, int(task_id)),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("editname_"))
async def edit_name_start(callback: CallbackQuery, state: FSMContext):
    _, task_type, task_id = callback.data.split("_")

    await state.update_data(edit_type=task_type, edit_id=int(task_id))
    await callback.message.edit_text("new name:")
    await state.set_state(TaskStates.editing_name)
    await callback.answer()


@dp.message(TaskStates.editing_name)
async def edit_name_receive(message: Message, state: FSMContext):
    state_data = await state.get_data()
    user_id = str(message.from_user.id)

    task_type = state_data["edit_type"]
    task_id = state_data["edit_id"]

    data[user_id][task_type][task_id]["name"] = message.text.strip()
    save_data(data)

    await message.answer(
        "name updated.",
        reply_markup=main_keyboard(),
    )
    await state.clear()


@dp.callback_query(F.data.startswith("edittime_"))
async def edit_time_start(callback: CallbackQuery, state: FSMContext):
    _, task_type, task_id = callback.data.split("_")

    await state.update_data(edit_type=task_type, edit_id=int(task_id))
    await callback.message.edit_text(
        "new time?\n\n"
        "format: `HH:MM`\n"
        "example: `07:45` or `14:30`",
        parse_mode="Markdown",
    )
    await state.set_state(TaskStates.editing_time)
    await callback.answer()


@dp.message(TaskStates.editing_time)
async def edit_time_receive(message: Message, state: FSMContext):
    time_str = message.text.strip()

    if not validate_time(time_str):
        await message.answer(
            "invalid format.\n\n"
            "use: `HH:MM`\n"
            "example: `07:45` or `14:30`",
            parse_mode="Markdown",
        )
        return

    parts = time_str.split(":")
    time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    state_data = await state.get_data()
    user_id = str(message.from_user.id)

    task_type = state_data["edit_type"]
    task_id = state_data["edit_id"]

    data[user_id][task_type][task_id]["time"] = time_str
    save_data(data)

    await message.answer(
        "time updated.",
        reply_markup=main_keyboard(),
    )
    await state.clear()


@dp.callback_query(F.data.startswith("editdeadline_"))
async def edit_deadline_start(callback: CallbackQuery, state: FSMContext):
    _, task_type, task_id = callback.data.split("_")

    await state.update_data(edit_type=task_type, edit_id=int(task_id))
    await callback.message.edit_text(
        "new deadline?",
        reply_markup=deadline_keyboard(),
    )
    await callback.answer()


# =======================
# Show tasks
# =======================


@dp.callback_query(F.data == "show_today")
async def show_today(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    init_user(callback.from_user.id)

    all_tasks = []

    for task in data[user_id]["recurring"]:
        all_tasks.append((task["time"], task, "recurring"))

    for task in data[user_id]["one_time"]:
        all_tasks.append((task["time"], task, "onetime"))

    for task in data[user_id]["long_term"]:
        if task.get("time") and not task.get("completed"):
            all_tasks.append((task["time"], task, "longterm"))

    all_tasks.sort(key=lambda x: x[0])

    if not all_tasks:
        await callback.message.edit_text(
            "no tasks for today.\nadd some.",
            reply_markup=main_keyboard(),
        )
        await callback.answer()
        return

    msg = "*today's schedule:*\n\n"

    for time, task, _ in all_tasks:
        status = "✅" if task.get("completed_today") else "⏸"
        msg += f"`{time}` {status} {task['name']}\n"

    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "show_recurring")
async def show_recurring(callback: CallbackQuery):
    user_id = str(callback.from_user.id)

    if not data[user_id]["recurring"]:
        await callback.message.edit_text(
            "no recurring tasks.\nadd daily habits.",
            reply_markup=main_keyboard(),
        )
        await callback.answer()
        return

    tasks = sorted(data[user_id]["recurring"], key=lambda x: x["time"])
    msg = "*recurring tasks:*\n\n"

    for i, task in enumerate(tasks, 1):
        status = "✅" if task.get("completed_today") else "⏸"
        msg += f"{i}. `{task['time']}` {status} {task['name']}\n"

    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=task_list_keyboard(
            callback.from_user.id,
            "recurring",
            "manage_recurring",
        ),
    )
    await callback.answer()


@dp.callback_query(F.data == "show_longterm")
async def show_longterm(callback: CallbackQuery):
    user_id = str(callback.from_user.id)

    if not data[user_id]["long_term"]:
        await callback.message.edit_text(
            "no long-term goals.\nset some.",
            reply_markup=main_keyboard(),
        )
        await callback.answer()
        return

    msg = "*long-term goals:*\n\n"

    for task in data[user_id]["long_term"]:
        status = "✅" if task.get("completed") else "⏳"
        time_info = f" `{task['time']}`" if task.get("time") else ""

        if task.get("deadline"):
            days_left = (
                datetime.strptime(task["deadline"], "%Y-%m-%d")
                - datetime.now()
            ).days
            deadline_info = (
                f"\n   `{task['deadline']}` ({days_left} days)"
            )
        else:
            deadline_info = "\n   no deadline"

        msg += f"{status} {task['name']}{time_info}{deadline_info}\n\n"

    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=task_list_keyboard(
            callback.from_user.id,
            "long_term",
            "manage_longterm",
        ),
    )
    await callback.answer()
# =======================
# Calendar
# =======================


@dp.callback_query(F.data == "show_calendar")
async def show_calendar(callback: CallbackQuery):
    user_id = str(callback.from_user.id)

    msg = "*30-day calendar:*\n\n"

    for week in range(5):
        week_str = ""
        for day in range(7):
            day_offset = 29 - (week * 7 + day)
            date = (
                datetime.now() - timedelta(days=day_offset)
            ).strftime("%Y-%m-%d")

            completion = get_day_completion(user_id, date)
            emoji = get_completion_emoji(completion)
            week_str += emoji

        msg += f"week {5 - week}: {week_str}\n"

    streak = data[user_id]["stats"].get("current_streak", 0)
    best = data[user_id]["stats"].get("best_streak", 0)

    msg += f"\n🔥 current streak: `{streak}` days"
    msg += f"\n⭐ best streak: `{best}` days"
    msg += "\n\n🟩 80-100% | 🟨 50-79% | 🟧 1-49% | ⬜ 0%"

    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


# =======================
# Complete / Skip / Delete
# =======================


@dp.callback_query(F.data.startswith("complete_"))
async def complete_task(callback: CallbackQuery):
    _, task_type, task_id = callback.data.split("_")
    task_id = int(task_id)

    user_id = str(callback.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")

    if task_type == "recurring":
        task = data[user_id]["recurring"][task_id]
        task["completed_today"] = True

        data[user_id]["history"].setdefault(today, {})
        data[user_id]["history"][today][task["name"]] = "done"

    elif task_type == "onetime":
        task = data[user_id]["one_time"].pop(task_id)

        data[user_id]["history"].setdefault(today, {})
        data[user_id]["history"][today][task["name"]] = "done"

    elif task_type == "longterm":
        data[user_id]["long_term"][task_id]["completed"] = True

    data[user_id]["stats"]["total_completed"] += 1

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if yesterday in data[user_id]["history"]:
        data[user_id]["stats"]["current_streak"] += 1
    else:
        data[user_id]["stats"]["current_streak"] = 1

    if (
        data[user_id]["stats"]["current_streak"]
        > data[user_id]["stats"]["best_streak"]
    ):
        data[user_id]["stats"]["best_streak"] = data[user_id]["stats"][
            "current_streak"
        ]

    save_data(data)

    reminder_key = f"{user_id}_{task_type}_{task_id}"
    reminders_sent.pop(reminder_key, None)

    await callback.message.edit_text(
        "done.\nnext.",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("skip_"))
async def skip_task(callback: CallbackQuery):
    _, task_type, task_id = callback.data.split("_")
    task_id = int(task_id)

    user_id = str(callback.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")

    if task_type == "recurring":
        task = data[user_id]["recurring"][task_id]
        data[user_id]["history"].setdefault(today, {})
        data[user_id]["history"][today][task["name"]] = "skipped"

    elif task_type == "onetime":
        data[user_id]["one_time"].pop(task_id)

    data[user_id]["stats"]["current_streak"] = 0
    save_data(data)

    await callback.message.edit_text(
        "skipped.",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("delete_"))
async def delete_task(callback: CallbackQuery):
    _, task_type, task_id = callback.data.split("_")
    task_id = int(task_id)

    user_id = str(callback.from_user.id)

    if task_type == "recurring":
        data[user_id]["recurring"].pop(task_id)
    elif task_type == "onetime":
        data[user_id]["one_time"].pop(task_id)
    elif task_type == "longterm":
        data[user_id]["long_term"].pop(task_id)

    save_data(data)

    await callback.message.edit_text(
        "deleted.",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("manage_"))
async def manage_task(callback: CallbackQuery):
    parts = callback.data.split("_")
    task_type = parts[1]
    task_id = int(parts[-1])

    await callback.message.edit_text(
        "action?",
        reply_markup=task_action_keyboard(task_id, task_type),
    )
    await callback.answer()


# =======================
# Stats / History / Settings
# ======================

@dp.callback_query(F.data == "show_stats")
async def show_stats(callback: CallbackQuery):
    user_id = str(callback.from_user.id)

    stats = data[user_id]["stats"]
    total = stats["total_completed"]
    streak = stats["current_streak"]
    best_streak = stats["best_streak"]

    today_tasks = data[user_id]["recurring"] + data[user_id]["one_time"]
    completed_today = sum(1 for t in today_tasks if t.get("completed_today"))
    total_today = len(today_tasks)
    rate = int((completed_today / total_today) * 100) if total_today else 0

    msg = (
        "*statistics:*\n\n"
        f"✅ total completed: `{total}`\n"
        f"📋 today: `{completed_today}/{total_today}` ({rate}%)\n"
        f"🔥 current streak: `{streak}` days\n"
        f"⭐ best streak: `{best_streak}` days\n\n"
        f"🔄 recurring habits: `{len(data[user_id]['recurring'])}`\n"
        f"🎯 long-term goals: `{len([t for t in data[user_id]['long_term'] if not t.get('completed')])}`"
    )

    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "show_history")
async def show_history(callback: CallbackQuery):
    user_id = str(callback.from_user.id)

    if not data[user_id]["history"]:
        await callback.message.edit_text(
            "no history yet.\nstart completing tasks.",
            reply_markup=main_keyboard(),
        )
        await callback.answer()
        return

    msg = "*history (last 7 days):*\n\n"

    for i in range(7):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")

        if date in data[user_id]["history"]:
            day_data = data[user_id]["history"][date]
            done = sum(1 for v in day_data.values() if v == "done")
            skipped = sum(1 for v in day_data.values() if v == "skipped")
            msg += f"`{date}`: ✅ {done} | ⏭ {skipped}\n"
        else:
            msg += f"`{date}`: —\n"

    await callback.message.edit_text(
        msg,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "show_settings")
async def show_settings(callback: CallbackQuery):
    await callback.message.edit_text(
        "settings:\n\n"
        "coming soon.\n"
        "evening report time, reminder preferences, etc.",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


# =======================
# Smart reminders
# =======================


async def send_reminders():
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        for user_id, user_data in data.items():
            try:
                for i, task in enumerate(user_data["recurring"]):
                    if (
                        task["time"] == current_time
                        and not task.get("completed_today")
                    ):
                        key = f"{user_id}_recurring_{i}"
                        if key not in reminders_sent:
                            await bot.send_message(
                                user_id,
                                f"*time.*\n\n{task['name']}",
                                parse_mode="Markdown",
                                reply_markup=task_action_keyboard(i, "recurring"),
                            )
                            reminders_sent[key] = now

                for i, task in enumerate(user_data["one_time"]):
                    if task["time"] == current_time:
                        key = f"{user_id}_onetime_{i}"
                        if key not in reminders_sent:
                            await bot.send_message(
                                user_id,
                                f"*reminder.*\n\n{task['name']}",
                                parse_mode="Markdown",
                                reply_markup=task_action_keyboard(i, "onetime"),
                            )
                            reminders_sent[key] = now

            except Exception:
                pass

        if current_time == "00:00":
            for user_data in data.values():
                for task in user_data["recurring"]:
                    task["completed_today"] = False
            reminders_sent.clear()
            save_data(data)

        await asyncio.sleep(60)


# =======================
# Main
# =======================


async def main():
    print("execution v4.0 online.")
    print("features: edit tasks, smart reminders, calendar heatmap")

    asyncio.create_task(send_reminders())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
