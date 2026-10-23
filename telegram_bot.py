#!/usr/bin/env python3
"""
Telegram-бот Джарвиса. 
Любое сообщение = задача в inbox. 
Поддерживает флаги: --area, --project, --priority, --due
"""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dateparser import parse

# ---- Импорт функций из ядра Джарвиса ----
from database import (
    get_today_plan, add_task, get_inbox_tasks,
    complete_task_and_reschedule, set_task_priority,
    get_seasonal_hints, get_active_temperature_hints,
    get_task_by_id, update_task, get_stats, PROJECTS_BY_AREA
)

# ⚠️ ВАЖНО: Для безопасности лучше вынести токен в переменные окружения (.env)
# Но пока оставим здесь для простоты тестирования.
TOKEN = "8298576297:AAGfPSv0rcYmNsmSWVTgIA6eOey2QZlvfHM"
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ── Парсер текста ────────────────────────────────────────────────────────
def parse_task_text(text: str):
    """
    Возвращает (title, area, project, priority, due_date).
    Примеры:
        "Купить хлеб через 2 дня"
        "Позвонить маме --area Семья --priority now"
        "Изучить Terraform --project DevOps --due завтра"
    """
    area = "Личные проекты"
    project = "Без проекта"
    priority = "inbox"
    due = None
    
    words = text.split()
    title_parts = []
    i = 0
    
    while i < len(words):
        w = words[i]
        if w == "--area" and i + 1 < len(words):
            area = words[i + 1]
            i += 2
        elif w == "--project" and i + 1 < len(words):
            project = words[i + 1]
            i += 2
        elif w == "--priority" and i + 1 < len(words):
            priority = words[i + 1]
            i += 2
        elif w == "--due" and i + 1 < len(words):
            due_str = words[i + 1]
            parsed = parse(due_str, settings={"RELATIVE_BASE": datetime.now()})
            due = parsed.strftime("%Y-%m-%d") if parsed else None
            i += 2
        else:
            title_parts.append(w)
            i += 1
            
    title = " ".join(title_parts).strip()
    return title, area, project, priority, due

# ── Клавиатура для /now ────────────────────────────────────────────────
def now_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="⏸ Отложить на завтра", callback_data="postpone_tomorrow")
    b.button(text="✅ Готово (первая задача)", callback_data="mark_done")
    b.adjust(2)
    return b.as_markup()

task_context = {}   # user_id -> {urgent:[], overdue:[], today:[]}

# ── Команды ────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет, я Джарвис! \n\n"
        "Просто напиши мне задачу, и она попадёт во Входящие.\n"
        "Можно использовать флаги:\n"
        "• `--area` (например: Семья)\n"
        "• `--project` (например: DevOps)\n"
        "• `--priority` (now, later, future)\n"
        "• `--due` (завтра, 15 октября)\n\n"
        "Доступные команды:\n"
        "/now – План на сегодня\n"
        "/inbox – Неразобранные задачи (отсортированы по важности)\n"
        "/remind – Сезонные и погодные напоминания"
    )

@dp.message(Command("now"))
async def cmd_now(message: types.Message):
    plan = get_today_plan()
    urgent = plan["urgent_list"]
    overdue = plan["overdue_list"]
    today = plan["today_list"]
    
    text = "🔹 *Сейчас (срочно)*:\n" + "\n".join(
        f"• {t['title']}" + (f" (до {t['due_date']})" if t.get('due_date') else "") for t in urgent[:5]
    ) or "— нет —"
    
    if overdue:
        text += "\n\n⏳ *Просрочено*:\n" + "\n".join(f"• {t['title']}" for t in overdue[:3])
    if today:
        text += "\n\n📅 *Дедлайн сегодня*:\n" + "\n".join(f"• {t['title']}" for t in today[:5])

    task_context[message.from_user.id] = {
        "urgent": urgent[:5],
        "overdue": overdue[:3],
        "today": today[:5],
    }
    await message.answer(text, reply_markup=now_keyboard(), parse_mode="Markdown")

@dp.message(Command("remind"))
async def cmd_remind(message: types.Message):
    seasonal = get_seasonal_hints()
    temp = get_active_temperature_hints()
    
    if not seasonal and not temp:
        await message.answer("🌤 Нет активных напоминаний на данный момент.")
        return
        
    lines = []
    if seasonal:
        lines.append("🌦 *Сезонные:*")
        for r in seasonal:
            lines.append(f"  • {r['title']} ({r['month_start']}–{r['month_end']} мес.)")
    if temp:
        lines.append("\n🌡 *Температурные:*")
        for r in temp:
            lines.append(f"  • {r['title']} ({r['operator_ru']} {r['trigger_temp']}°C {r['trigger_date']})")
            
    await message.answer("\n".join(lines), parse_mode="Markdown")

@dp.message(Command("inbox"))
async def cmd_inbox(message: types.Message):
    tasks = get_inbox_tasks()
    if not tasks:
        await message.answer("📭 Inbox пуст. Отличная работа!")
        return
    
    text = "📥 *Inbox (отсортировано по важности проекта)*:\n\n"
    for t in tasks[:15]:
        weight = t.get('project_weight', 5)
        # Иконка в зависимости от веса
        weight_icon = "🔴" if weight >= 8 else ("🔵" if weight >= 4 else "⚪")
        due_str = f" (до {t['due_date']})" if t.get('due_date') else ""
        
        text += f"{weight_icon} *{t['title']}*{due_str}\n"
        text += f"   _{t['area']} / {t['project']} (Вес: {weight}/10, рек: {t.get('suggested_priority', 'inbox')})_\n\n"
    
    await message.answer(text.strip(), parse_mode="Markdown")

# Любой текст, НЕ начинающийся с '/' → задача
@dp.message(F.text.regexp(r"^[^/]"))
async def any_text_to_task(message: types.Message):
    if not message.text or not message.text.strip():
        return
        
    title, area, project, priority, due = parse_task_text(message.text)
    
    if not title:
        await message.answer("Не удалось распознать задачу. Напиши что‑нибудь вроде «Купить молоко»")
        return
        
    # Мягкая валидация: если область не найдена, ставим дефолтную
    if area not in PROJECTS_BY_AREA:
        area = "Личные проекты"
        project = "Без проекта"

    task_id = add_task(
        title=title, area=area, project=project,
        priority=priority, due_date=due, repeat="none"
    )
    await message.answer(f"✅ *#{task_id}* добавлена в Inbox:\n_{title}_", parse_mode="Markdown")

# ── /add (оставлен для явного добавления) ──────────────────────────────
@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: `/add <текст> [--area ...] [--project ...] [--priority ...] [--due ...]`", parse_mode="Markdown")
        return
        
    title, area, project, priority, due = parse_task_text(parts[1])
    if not title:
        await message.answer("Не указана задача")
        return
        
    if area not in PROJECTS_BY_AREA:
        area = "Личные проекты"
        project = "Без проекта"

    task_id = add_task(title, area, project, priority, due, "none")
    await message.answer(f"✅ *#{task_id}* добавлена:\n_{title}_", parse_mode="Markdown")

# ── Кнопки клавиатуры /now ─────────────────────────────────────────────
@dp.callback_query(F.data.startswith("postpone_"))
async def postpone(call: types.CallbackQuery):
    user_id = call.from_user.id
    ctx = task_context.get(user_id, {})
    
    for t in ctx.get("urgent", []):
        task_id = t["id"]
        new_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        update_task(task_id, t["title"], t["area"], t["project"], t["priority"], new_date, t.get("repeat", "none"))
        
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("✅ Срочные задачи перенесены на завтра.")
    task_context.pop(user_id, None)
    await call.answer()

@dp.callback_query(F.data == "mark_done")
async def mark_done(call: types.CallbackQuery):
    user_id = call.from_user.id
    ctx = task_context.get(user_id, {})
    
    if ctx.get("urgent"):
        task_id = ctx["urgent"][0]["id"]
        complete_task_and_reschedule(task_id)
        await call.message.answer("✅ Первая срочная задача выполнена!")
    else:
        await call.message.answer("Нет срочных задач для выполнения.")
        
    task_context.pop(user_id, None)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer()

# ── Запуск ─────────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("🤖 Бот Джарвис запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())