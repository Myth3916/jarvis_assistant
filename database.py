import sqlite3
import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

DB_NAME = "jarvis.db"

PROJECTS_BY_AREA = {
    "Работа и карьера": ["Текущие задачи", "Автоматизация 1С", "Поиск новой работы"],
    "Учёба и развитие": ["DevOps", "Пентест", "Чтение книг", "Курсы"],
    "Семья и близкие": ["Мама (здоровье)", "Дети (учеба/помощь)", "Наследство жены", "Общие дела"],
    "Дом и хозяйство": ["Квартира", "Дача/Деревня", "Виноградник", "Крупные покупки"],
    "Транспорт": ["Текущее обслуживание", "Планирование замены авто"],
    "Финансы": ["Бюджет", "Накопления", "Долги/Кредиты"],
    "Здоровье": ["Моё здоровье", "Питание и Пост", "Спорт"],
    "Социальное": ["Соседи", "Друзья", "Юридические вопросы"],
    "Личные проекты": ["Идеи", "Хобби", "Когда-нибудь", "Без проекта"]
}

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_database():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'area' not in columns:
        print("🔄 Выполняется миграция базы данных на новую структуру...")
        cursor.execute("ALTER TABLE tasks ADD COLUMN area TEXT DEFAULT 'Личные проекты'")
        cursor.execute("ALTER TABLE tasks ADD COLUMN project TEXT DEFAULT 'Без проекта'")
        
        migration_map = {
            'мама': ('Семья и близкие', 'Мама (здоровье)'),
            'семья': ('Семья и близкие', 'Общие дела'),
            'учеба': ('Учёба и развитие', 'DevOps'),
            'работа': ('Работа и карьера', 'Текущие задачи'),
            'питание_пост': ('Здоровье', 'Питание и Пост'),
            'авто': ('Транспорт', 'Текущее обслуживание'),
            'дача': ('Дом и хозяйство', 'Дача/Деревня'),
            'финансы': ('Финансы', 'Бюджет'),
            'здоровье': ('Здоровье', 'Моё здоровье'),
            'соседи': ('Социальное', 'Соседи')
        }
        
        for old_ctx, (new_area, new_proj) in migration_map.items():
            cursor.execute("UPDATE tasks SET area = ?, project = ? WHERE context = ?", (new_area, new_proj, old_ctx))
        
        cursor.execute("UPDATE tasks SET area = 'Личные проекты', project = 'Без проекта' WHERE area IS NULL")
        conn.commit()
        print("✅ Миграция успешно завершена!")
        migrate_projects()
    conn.close()

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица Задач
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            area TEXT DEFAULT 'Личные проекты',
            project TEXT DEFAULT 'Без проекта',
            priority TEXT NOT NULL,
            due_date TEXT,
            repeat TEXT DEFAULT 'none',
            pinned INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    ''')
       
    # Таблица заметок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area TEXT NOT NULL,
            project TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    
    # Таблица проектов (объединённая и с strategic_weight)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area TEXT NOT NULL,
            name TEXT NOT NULL,
            strategic_weight INTEGER DEFAULT 5,
            is_archived INTEGER DEFAULT 0,
            UNIQUE(area, name)
        )
    ''')
    
    # Миграция: добавляем колонку strategic_weight, если её ещё нет в старой базе
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN strategic_weight INTEGER DEFAULT 5")
    except sqlite3.OperationalError:
        pass  # Колонка уже существует, всё ок

    # Таблица сезонных напоминаний
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seasonal_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            area TEXT NOT NULL,
            project TEXT NOT NULL,
            month_start INTEGER NOT NULL,
            month_end INTEGER NOT NULL,
            priority TEXT DEFAULT 'later',
            is_active INTEGER DEFAULT 1
        )
    ''')

    # Таблица температурных напоминаний
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temperature_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            area TEXT NOT NULL,
            project TEXT NOT NULL,
            operator TEXT NOT NULL,
            temperature REAL NOT NULL,
            priority TEXT DEFAULT 'later',
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    conn.commit()
    conn.close()
    migrate_database()

def add_task(title: str, area: str, project: str, priority: str, due_date: str = None, repeat: str = "none"):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO tasks (title, area, project, priority, due_date, repeat, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (title, area, project, priority, due_date, repeat, now))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def get_all_tasks(area: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    order_by = "CASE priority WHEN 'now' THEN 1 WHEN 'later' THEN 2 WHEN 'future' THEN 3 WHEN 'inbox' THEN 4 END, due_date ASC"
    
    if area:
        cursor.execute(f"SELECT * FROM tasks WHERE status = 'active' AND area = ? ORDER BY {order_by}", (area,))
    else:
        cursor.execute(f"SELECT * FROM tasks WHERE status = 'active' ORDER BY {order_by}")
    
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks

def get_tasks_with_deadline_info(area: str = None):
    tasks = get_all_tasks(area)
    today = datetime.now().date()
    enriched = []
    for task in tasks:
        if task['due_date']:
            due = datetime.strptime(task['due_date'], "%Y-%m-%d").date()
            days_left = (due - today).days
            if days_left < 0: task['deadline_status'] = 'overdue'
            elif days_left == 0: task['deadline_status'] = 'today'
            elif days_left <= 3: task['deadline_status'] = 'soon'
            else: task['deadline_status'] = 'ok'
        else:
            task['deadline_status'] = 'no_date'
        enriched.append(task)
    return enriched

def complete_task(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def get_completed_tasks(limit: int = 50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'done' ORDER BY created_at DESC LIMIT ?", (limit,))
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks

def restore_task(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status = 'active' WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    cursor.execute("SELECT COUNT(*) as total FROM tasks WHERE status = 'done'")
    total_done = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as today FROM tasks WHERE status = 'done' AND created_at >= ?", (today,))
    today_done = cursor.fetchone()['today']
    
    cursor.execute("SELECT COUNT(*) as week FROM tasks WHERE status = 'done' AND created_at >= ?", (week_ago,))
    week_done = cursor.fetchone()['week']
    
    cursor.execute("SELECT COUNT(*) as active FROM tasks WHERE status = 'active' AND priority != 'inbox'")
    active_count = cursor.fetchone()['active']
    
    cursor.execute("SELECT COUNT(*) as inbox FROM tasks WHERE status = 'active' AND priority = 'inbox'")
    inbox_count = cursor.fetchone()['inbox']
    
    conn.close()
    return {
        'total_done': total_done, 'today_done': today_done, 'week_done': week_done, 
        'active_count': active_count, 'inbox_count': inbox_count
    }

def get_task_by_id(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    conn.close()
    return dict(task) if task else None

def update_task(task_id: int, title: str, area: str, project: str, priority: str, due_date: str = None, repeat: str = "none"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET title = ?, area = ?, project = ?, priority = ?, due_date = ?, repeat = ? WHERE id = ?", 
        (title, area, project, priority, due_date, repeat, task_id)
    )
    conn.commit()
    conn.close()

def delete_task(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def suggest_priority(title: str, area: str) -> str:
    title_lower = title.lower()
    urgent_kw = ['срочно', 'завтра', 'сегодня', 'немедленно', 'асап', 'критично', 'важно', 'врач', 'лекарства', 'больница', 'экзамен', 'дедлайн']
    later_kw = ['на неделе', 'скоро', 'до пятницы', 'на днях', 'купить', 'позвонить', 'написать', 'сходить']
    future_kw = ['когда-нибудь', 'может быть', 'идея', 'подумать', 'обдумать', 'изучить', 'освоить', 'на будущее', 'потом']
    
    for kw in urgent_kw:
        if kw in title_lower: return 'now'
    for kw in later_kw:
        if kw in title_lower: return 'later'
    for kw in future_kw:
        if kw in title_lower: return 'future'
        
    if area == 'Семья и близкие' and any(w in title_lower for w in ['врач', 'лекарства', 'больница', 'здоровье']): return 'now'
    if area == 'Учёба и развитие' and any(w in title_lower for w in ['экзамен', 'лаба', 'дедлайн', 'сдать']): return 'now'
    
    return 'inbox'

def get_inbox_tasks():
    """Получает входящие задачи, отсортированные по стратегическому весу проекта."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Используем JOIN с таблицей projects для получения strategic_weight
    cursor.execute('''
        SELECT t.*, COALESCE(p.strategic_weight, 5) as project_weight
        FROM tasks t
        LEFT JOIN projects p ON t.area = p.area AND t.project = p.name
        WHERE t.status = 'active' AND t.priority = 'inbox'
        ORDER BY 
            project_weight DESC,  -- Сначала задачи из важных проектов
            t.created_at DESC     -- Потом по дате создания
    ''')
    
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks

def set_task_priority(task_id: int, priority: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET priority = ? WHERE id = ?", (priority, task_id))
    conn.commit()
    conn.close()

def get_today_plan():
    """Возвращает сбалансированный план на сегодня с умной сортировкой."""
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute('''
        SELECT * FROM tasks 
        WHERE status = 'active'
        ORDER BY 
            pinned DESC,
            CASE priority 
                WHEN 'now' THEN 1 
                WHEN 'later' THEN 2 
                WHEN 'future' THEN 3 
                ELSE 4 
            END,
            CASE 
                WHEN due_date < ? THEN 1
                WHEN due_date = ? THEN 2
                ELSE 3
            END,
            due_date ASC,
            title ASC
    ''', (today, today))
    
    all_tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    urgent = [t for t in all_tasks if t['priority'] == 'now']
    overdue = [t for t in all_tasks if t.get('due_date') and t['due_date'] < today and t['priority'] != 'now']
    today_deadline = [t for t in all_tasks if t.get('due_date') == today and t['priority'] != 'now']
    study_work = [t for t in all_tasks if t['area'] in ['Работа и карьера', 'Учёба и развитие'] and t['priority'] != 'now' and (not t.get('due_date') or t['due_date'] >= today)]
    family = [t for t in all_tasks if t['area'] == 'Семья и близкие' and t['priority'] != 'now' and (not t.get('due_date') or t['due_date'] >= today)]
    other = [t for t in all_tasks if t['area'] not in ['Работа и карьера', 'Учёба и развитие', 'Семья и близкие'] and t['priority'] != 'now' and (not t.get('due_date') or t['due_date'] >= today)]
    
    total_tasks = len(all_tasks)
    urgent_count = len(urgent)
    overdue_count = len(overdue)
    
    if total_tasks == 0:
        advice = {'text': '🎉 Сегодня свободный день! Отличное время для отдыха, творчества или стратегического планирования.', 'color': '#69f0ae'}
    elif urgent_count >= 5 or overdue_count >= 3:
        advice = {'text': '🔥 День серьёзно загружен! Сфокусируйся на срочном и просроченном. Не пытайся сделать всё — выбирай главное.', 'color': '#ff5252'}
    elif total_tasks >= 8:
        advice = {'text': '⚡ Много задач на сегодня. Начни с самого важного, остальное — по остаточному принципу. Ты справишься!', 'color': '#ffab40'}
    elif total_tasks >= 4:
        advice = {'text': '✅ Сбалансированный день. Начни с просроченных и срочных, потом переходи к остальному.', 'color': '#00e5ff'}
    else:
        advice = {'text': '🌟 Лёгкий день! Можно не только выполнить задачи, но и сделать что-то для будущего (учёба, планирование).', 'color': '#b0bec5'}
    
    return {
        'tasks': all_tasks,
        'urgent_list': urgent,
        'overdue_list': overdue,
        'today_list': today_deadline,
        'study_list': study_work,
        'family_list': family,
        'other_list': other,
        'advice': advice,
        'stats': {
            'urgent_count': len(urgent),
            'overdue_count': len(overdue),
            'today_count': len(today_deadline),
            'study_count': len(study_work),
            'family_count': len(family),
            'other_count': len(other),
            'total': total_tasks
        }
    }

def get_seasonal_hints():
    return get_active_seasonal_hints()

def get_fasting_status():
    today = datetime.now()
    month = today.month
    day = today.day
    weekday = today.weekday()
    
    is_great_lent = (month == 3 and day >= 15) or (month == 4 and day <= 20)
    is_petrov = (month == 6)
    is_dormition = (month == 8 and day >= 14 and day <= 27)
    is_nativity = (month == 11 and day >= 28) or (month == 12) or (month == 1 and day <= 6)
    
    is_major_fast = is_great_lent or is_dormition
    is_solid_week = False

    status = "Обычный день"
    color = "#69f0ae"
    advice = "Можно есть всё. Не забудь про овощи и фрукты!"
    task_suggestion = None

    if is_solid_week:
        status = "Сплошная седмица"
        color = "#69f0ae"
        advice = "Поста нет. Можно есть всё."
    elif is_major_fast:
        if weekday in [2, 4]:
            status = "Строгий пост (Среда/Пятница)"
            color = "#ff5252"
            advice = "Исключить: мясо, молоко, яйца, рыбу, масло. Только растительная пища."
            task_suggestion = "Купить продукты для строгого поста"
        else:
            status = "Умеренный пост"
            color = "#ffab40"
            advice = "Исключить: мясо и молоко. Можно рыбу и растительное масло."
            task_suggestion = "Купить рыбу и постные продукты"
    elif is_petrov or is_nativity:
        if weekday in [2, 4]:
            status = "Пост (Среда/Пятница)"
            color = "#ffab40"
            advice = "Рыба запрещена. Растительное масло только в выходные."
            task_suggestion = "Купить постные продукты"
        else:
            status = "Пост (Рыба разрешена)"
            color = "#ffd740"
            advice = "Можно рыбу и растительное масло."
    elif weekday in [2, 4] and not is_solid_week:
        status = "Однодневный пост (Среда/Пятница)"
        color = "#ffab40"
        advice = "Исключить мясо и молоко. Рыба и масло разрешены."
        task_suggestion = "Купить рыбу и молочные продукты (завтра можно)"

    return {"status": status, "color": color, "advice": advice, "task_suggestion": task_suggestion}

def add_note(area: str, project: str, title: str, content: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO notes (area, project, title, content, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (area, project, title, content, now))
    conn.commit()
    conn.close()

def get_all_notes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notes ORDER BY created_at DESC")
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def delete_note(note_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()

def migrate_projects():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM projects")
    count = cursor.fetchone()['count']
    
    if count == 0:
        print("🔄 Миграция проектов из кода в базу данных...")
        for area, projects_list in PROJECTS_BY_AREA.items():
            for project_name in projects_list:
                try:
                    # Добавлен strategic_weight = 5 по умолчанию
                    cursor.execute(
                        "INSERT INTO projects (area, name, strategic_weight) VALUES (?, ?, ?)",
                        (area, project_name, 5)
                    )
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
        print("✅ Проекты мигрированы в базу данных!")
    conn.close()

def get_projects_by_area():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT area, name FROM projects WHERE is_archived = 0 ORDER BY area, name")
    result = {}
    for row in cursor.fetchall():
        area = row['area']
        name = row['name']
        if area not in result:
            result[area] = []
        result[area].append(name)
    conn.close()
    return result

def add_project(area: str, name: str, strategic_weight: int = 5):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO projects (area, name, strategic_weight)
            VALUES (?, ?, ?)
        ''', (area, name, strategic_weight))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def archive_project(project_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET is_archived = 1 WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def get_all_projects():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY area, is_archived, name")
    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return projects

def update_project(project_id: int, new_name: str, new_area: str, strategic_weight: int):
    """Обновлено: добавлен параметр strategic_weight"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT area, name FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    if not project:
        conn.close()
        return False
    
    old_name = project['name']
    old_area = project['area']
    
    cursor.execute(
        "UPDATE projects SET name = ?, area = ?, strategic_weight = ? WHERE id = ?",
        (new_name, new_area, strategic_weight, project_id)
    )
    
    cursor.execute("UPDATE tasks SET project = ?, area = ? WHERE area = ? AND project = ?", (new_name, new_area, old_area, old_name))
    cursor.execute("UPDATE notes SET project = ?, area = ? WHERE area = ? AND project = ?", (new_name, new_area, old_area, old_name))
    
    conn.commit()
    conn.close()
    print(f"✅ Проект обновлён: '{old_area}/{old_name}' → '{new_area}/{new_name}' (Вес: {strategic_weight})")
    return True

def restore_project(project_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET is_archived = 0 WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def can_delete_project(project_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT area, name FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    if not project:
        conn.close()
        return False, "Проект не найден"
    
    area = project['area']
    name = project['name']
    
    cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE area = ? AND project = ?", (area, name))
    tasks_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM notes WHERE area = ? AND project = ?", (area, name))
    notes_count = cursor.fetchone()['count']
    
    conn.close()
    
    if tasks_count > 0 or notes_count > 0:
        return False, f"Нельзя удалить: есть {tasks_count} задач и {notes_count} заметок"
    return True, "Можно удалять"

def delete_project(project_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def complete_task_and_reschedule(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return
    
    task_dict = dict(task)
    cursor.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
    
    if task_dict['repeat'] and task_dict['repeat'] != 'none':
        next_due_date = None
        if task_dict['due_date']:
            current_date = datetime.strptime(task_dict['due_date'], "%Y-%m-%d").date()
            if task_dict['repeat'] == 'daily':
                next_due_date = (current_date + relativedelta(days=1)).strftime("%Y-%m-%d")
            elif task_dict['repeat'] == 'weekly':
                next_due_date = (current_date + relativedelta(weeks=1)).strftime("%Y-%m-%d")
            elif task_dict['repeat'] == 'monthly':
                next_due_date = (current_date + relativedelta(months=1)).strftime("%Y-%m-%d")
            elif task_dict['repeat'] == 'yearly':
                next_due_date = (current_date + relativedelta(years=1)).strftime("%Y-%m-%d")
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO tasks (title, area, project, priority, due_date, repeat, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
        ''', (task_dict['title'], task_dict['area'], task_dict['project'], task_dict['priority'], next_due_date, task_dict['repeat'], now))
    
    conn.commit()
    conn.close()

def get_seasonal_reminders():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM seasonal_reminders ORDER BY month_start, title")
    reminders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reminders

def add_seasonal_reminder(title: str, area: str, project: str, month_start: int, month_end: int, priority: str = "later"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO seasonal_reminders (title, area, project, month_start, month_end, priority)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, area, project, month_start, month_end, priority))
    conn.commit()
    conn.close()

def update_seasonal_reminder(reminder_id: int, title: str, area: str, project: str, month_start: int, month_end: int, priority: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE seasonal_reminders 
        SET title = ?, area = ?, project = ?, month_start = ?, month_end = ?, priority = ?
        WHERE id = ?
    ''', (title, area, project, month_start, month_end, priority, reminder_id))
    conn.commit()
    conn.close()

def delete_seasonal_reminder(reminder_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM seasonal_reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def toggle_seasonal_reminder(reminder_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE seasonal_reminders SET is_active = 1 - is_active WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def get_active_seasonal_hints():
    conn = get_connection()
    cursor = conn.cursor()
    current_month = datetime.now().month
    cursor.execute('''
        SELECT * FROM seasonal_reminders 
        WHERE is_active = 1 AND month_start <= ? AND month_end >= ?
        ORDER BY title
    ''', (current_month, current_month))
    hints = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return hints

def get_temperature_reminders():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM temperature_reminders ORDER BY temperature")
    reminders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reminders

def add_temperature_reminder(title: str, area: str, project: str, operator: str, temperature: float, priority: str = "later"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO temperature_reminders (title, area, project, operator, temperature, priority)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, area, project, operator, temperature, priority))
    conn.commit()
    conn.close()

def delete_temperature_reminder(reminder_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM temperature_reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def toggle_temperature_reminder(reminder_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE temperature_reminders SET is_active = 1 - is_active WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def update_temperature_reminder(reminder_id: int, title: str, area: str, project: str, operator: str, temperature: float, priority: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE temperature_reminders 
        SET title = ?, area = ?, project = ?, operator = ?, temperature = ?, priority = ?
        WHERE id = ?
    ''', (title, area, project, operator, temperature, priority, reminder_id))
    conn.commit()
    conn.close()

USE_MOCK_WEATHER = True  
_weather_cache = {"data": None, "timestamp": 0}

def get_weather_forecast():
    import time
    now = time.time()
    if _weather_cache["data"] and (now - _weather_cache["timestamp"]) < 3600:
        return _weather_cache["data"]
    
    if USE_MOCK_WEATHER:
        forecast = [
            {'date': '2026-10-20', 'max': 8.0, 'min': 4.0},
            {'date': '2026-10-21', 'max': 5.0, 'min': 1.0},
            {'date': '2026-10-22', 'max': 2.0, 'min': -1.0},
            {'date': '2026-10-23', 'max': -1.0, 'min': -4.0},
            {'date': '2026-10-24', 'max': -3.0, 'min': -6.0},
        ]
        _weather_cache["data"] = forecast
        _weather_cache["timestamp"] = now
        return forecast

    try:
        url = "https://wttr.in/Moscow?format=j1"
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        data = response.json()
        forecast = [{'date': day['date'], 'max': float(day['maxtempC']), 'min': float(day['mintempC'])} for i, day in enumerate(data.get('weather', [])[:7])]
        _weather_cache["data"] = forecast
        _weather_cache["timestamp"] = now
        return forecast
    except Exception as e:
        print(f"⚠️ Ошибка получения погоды: {e}")
        return _weather_cache["data"] or []

def get_active_temperature_hints():
    reminders = get_temperature_reminders()
    active_reminders = [r for r in reminders if r['is_active']]
    if not active_reminders:
        return []
    
    forecast = get_weather_forecast()
    if not forecast:
        return []
    
    triggered = []
    today = datetime.now().date()
    
    for reminder in active_reminders:
        for day in forecast:
            day_date = datetime.strptime(day['date'], "%Y-%m-%d").date()
            days_left = (day_date - today).days
            
            triggered_temp = None
            if reminder['operator'] == 'below' and day['max'] <= reminder['temperature']:
                triggered_temp = day['max']
            elif reminder['operator'] == 'above' and day['min'] >= reminder['temperature']:
                triggered_temp = day['min']
            
            if triggered_temp is not None:
                if days_left == 0: date_str = "сегодня"
                elif days_left == 1: date_str = "завтра"
                else: date_str = f"через {days_left} дн. ({day['date']})"
                
                triggered.append({
                    **reminder,
                    'trigger_date': date_str,
                    'trigger_temp': triggered_temp,
                    'operator_ru': 'ниже' if reminder['operator'] == 'below' else 'выше'
                })
                break
    return triggered

def toggle_pin_task(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET pinned = 1 - pinned WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def get_weekly_report():
    """Анализирует выполненные задачи за последние 7 дней, цели и даёт подробный стратегический разбор."""
    conn = get_connection()
    cursor = conn.cursor()
    
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Получаем выполненные задачи за неделю
    cursor.execute('''
        SELECT t.*, COALESCE(p.strategic_weight, 5) as project_weight
        FROM tasks t
        LEFT JOIN projects p ON t.area = p.area AND t.project = p.name
        WHERE t.status = 'done' AND t.created_at >= ?
        ORDER BY t.created_at DESC
    ''', (week_ago,))
    
    tasks = [dict(row) for row in cursor.fetchall()]
    
    # 2. Получаем стратегические цели (проекты с весом 8-10)
    cursor.execute('''
        SELECT area, name, strategic_weight 
        FROM projects 
        WHERE strategic_weight >= 8 AND is_archived = 0
        ORDER BY strategic_weight DESC, name ASC
    ''')
    goals = [dict(row) for row in cursor.fetchall()]
    
    # 3. Считаем прогресс по каждой цели
    for goal in goals:
        cursor.execute('''
            SELECT COUNT(*) as count 
            FROM tasks 
            WHERE status = 'done' 
            AND area = ? 
            AND project = ? 
            AND created_at >= ?
        ''', (goal['area'], goal['name'], week_ago))
        goal['completed_count'] = cursor.fetchone()['count']
        
    conn.close()
    
    # 4. Считаем общую статистику
    total = len(tasks)
    high_weight = len([t for t in tasks if t.get('project_weight', 5) >= 8])
    medium_weight = len([t for t in tasks if 4 <= t.get('project_weight', 5) <= 7])
    low_weight = len([t for t in tasks if t.get('project_weight', 5) <= 3])
    
    if total > 0:
        high_pct = round(high_weight / total * 100)
        medium_pct = round(medium_weight / total * 100)
        low_pct = round(low_weight / total * 100)
        tasks_per_day = round(total / 7, 1)
    else:
        high_pct = medium_pct = low_pct = 0
        tasks_per_day = 0
    
    # 5. Генерируем анализ (тем, что было раньше)
    analysis = {
        "tempo": "",
        "good": [],
        "trap": "",
        "recommendations": []
    }
    
    if total == 0:
        analysis["tempo"] = "😴 За неделю не выполнено ни одной задачи."
    elif tasks_per_day >= 2.5:
        analysis["tempo"] = f"🔥 Высокий темп! {total} задач за неделю ({tasks_per_day} в день)."
    elif tasks_per_day >= 1:
        analysis["tempo"] = f"✅ Хороший темп. {total} задач за неделю ({tasks_per_day} в день)."
    else:
        analysis["tempo"] = f" Спокойная неделя. {total} задач."
    
    if high_weight > 0:
        analysis["good"].append(f"Стратегические задачи присутствуют ({high_weight} шт.) — ты не полностью ушёл в операционку.")
    if low_weight <= 2:
        analysis["good"].append("Рутины минимум — ты умеешь фокусироваться на важном.")
    if not analysis["good"]:
        analysis["good"].append("Ты вообще делаешь задачи — это уже лучше, чем ничего.")
        
    if total == 0:
        analysis["trap"] = "Главная ловушка: отсутствие движения."
    elif high_pct < 30 and medium_pct > 50:
        analysis["trap"] = f"️ {medium_pct}% энергии уходит в «среднюю зону». Классическая ситуация: «Я занят весь день, но к главному не приблизился»."
    elif high_weight == 0:
        analysis["trap"] = "За неделю ни одной задачи из стратегических проектов."
    else:
        analysis["trap"] = "Явных ловушек не вижу. Ты в хорошем балансе."
        
    if high_pct < 40 and total > 0:
        needed = max(1, int(total * 0.4) - high_weight)
        analysis["recommendations"].append(f"Добавь {needed} маленькие задачи из проектов с весом 8-10 на следующую неделю.")
    if medium_pct > 50:
        analysis["recommendations"].append("Посмотри на свои «средние» задачи. Какие можно делегировать или отложить?")
    analysis["recommendations"].append("Правило: утро — для стратегического, день — для среднего.")
    
    # 6. Общий совет
    if total == 0:
        advice_text = "😴 За неделю не выполнено ни одной задачи. Возможно, стоит пересмотреть план?"
        advice_color = "#ffab40"
    elif high_pct >= 40:
        advice_text = f"🚀 Отличная неделя! {high_pct}% задач — стратегические. Ты движешься к главному!"
        advice_color = "#69f0ae"
    elif high_weight == 0:
        advice_text = "⚠️ За неделю ни одной задачи из стратегических проектов. Давай добавим одну маленькую задачу по важной цели."
        advice_color = "#ff5252"
    else:
        advice_text = f"✅ Хорошая работа! {total} задач, {high_pct}% — стратегических. Продолжай!"
        advice_color = "#00e5ff"
    
    return {
        "tasks": tasks,
        "goals": goals,  # <-- Передаём цели в шаблон
        "stats": {
            "total": total, "high": high_weight, "medium": medium_weight, "low": low_weight,
            "high_pct": high_pct, "medium_pct": medium_pct, "low_pct": low_pct, "tasks_per_day": tasks_per_day
        },
        "analysis": analysis,
        "advice": {"text": advice_text, "color": advice_color}
    }

# Инициализация при импорте
init_db()