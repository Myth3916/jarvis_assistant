import sqlite3
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
    
    # Добавляем колонку repeat (повторение)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            area TEXT DEFAULT 'Личные проекты',
            project TEXT DEFAULT 'Без проекта',
            priority TEXT NOT NULL,
            due_date TEXT,
            repeat TEXT DEFAULT 'none',  -- НОВОЕ: 'none', 'weekly', 'monthly', 'yearly'
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    ''')

    # Таблица задач
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            area TEXT DEFAULT 'Личные проекты',
            project TEXT DEFAULT 'Без проекта',
            priority TEXT NOT NULL,
            due_date TEXT,
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
    
    # Таблица проектов (НОВОЕ!)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area TEXT NOT NULL,
            name TEXT NOT NULL,
            is_archived INTEGER DEFAULT 0,
            UNIQUE(area, name)
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

def update_task(task_id: int, title: str, area: str, project: str, priority: str, due_date: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET title = ?, area = ?, project = ?, priority = ?, due_date = ? WHERE id = ?", 
                   (title, area, project, priority, due_date, task_id))
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'active' AND priority = 'inbox' ORDER BY created_at DESC")
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
    """Умный планировщик: собирает сбалансированный план на день."""
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("SELECT * FROM tasks WHERE status = 'active' ORDER BY due_date ASC")
    all_tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    overdue, today_deadline, study, family, other = [], [], [], [], []
    family_contexts = {'Семья и близкие', 'Здоровье'}
    study_contexts = {'Учёба и развитие', 'Работа и карьера'}
    
    for task in all_tasks:
        due = task.get('due_date')
        area = task.get('area', '')
        if due and due < today: overdue.append(task)
        elif due and due == today: today_deadline.append(task)
        elif area in study_contexts: study.append(task)
        elif area in family_contexts: family.append(task)
        else: other.append(task)
    
    plan_tasks, used_ids = [], set()
    def add_task(task):
        if task['id'] not in used_ids:
            plan_tasks.append(task)
            used_ids.add(task['id'])
            return True
        return False
    
    for task in overdue: add_task(task)
    for task in today_deadline: add_task(task)
    if study: add_task(study[0])
    if family: add_task(family[0])
    for task in other:
        if len(plan_tasks) >= 6: break
        add_task(task)
    for task in study + family:
        if len(plan_tasks) >= 6: break
        add_task(task)
    
    overdue_list, today_list, study_list, family_list, other_list = [], [], [], [], []
    for task in plan_tasks:
        due = task.get('due_date')
        area = task.get('area', '')
        if due and due < today: overdue_list.append(task)
        elif due and due == today: today_list.append(task)
        elif area in study_contexts: study_list.append(task)
        elif area in family_contexts: family_list.append(task)
        else: other_list.append(task)
        
    total = len(plan_tasks)
    if total == 0: advice = "На сегодня задач нет. Отличный день для отдыха!"
    elif total <= 3: advice = "Лёгкий день. Спокойно справишься со всем."
    elif total <= 6: advice = "Сбалансированный день. Начни с просроченных и срочных."
    else: advice = f"⚠️ Насыщенный день ({total} задач). Сфокусируйся на главном."
    
    return {
        'tasks': plan_tasks, 'urgent_count': len(overdue_list) + len(today_list),
        'study_count': len(study_list), 'family_count': len(family_list), 'other_count': len(other_list),
        'total_count': total, 'advice': advice, 'overdue_list': overdue_list, 'today_list': today_list,
        'study_list': study_list, 'family_list': family_list, 'other_list': other_list
    }

def get_seasonal_hints():
    """Возвращает умные подсказки в зависимости от текущего месяца."""
    current_month = datetime.now().month
    
    hints = []
    
    # Весна (Март, Апрель, Май)
    if current_month in [3, 4, 5]:
        hints.append({"area": "Дом и хозяйство", "project": "Виноградник", "title": "Обработка виноградника от болезней и открытие"})
        hints.append({"area": "Транспорт", "project": "Текущее обслуживание", "title": "Замена шин на летние и проверка кондиционера"})
        hints.append({"area": "Здоровье", "project": "Питание и Пост", "title": "Великий пост (проверьте постное меню)"})
    
    # Лето (Июнь, Июль, Август)
    elif current_month in [6, 7, 8]:
        hints.append({"area": "Дом и хозяйство", "project": "Виноградник", "title": "Полив, подкормка и защита от вредителей"})
        hints.append({"area": "Дом и хозяйство", "project": "Дача/Деревня", "title": "Подготовка инвентаря к уборке урожая"})
    
    # Осень (Сентябрь, Октябрь, Ноябрь)
    elif current_month in [9, 10, 11]:
        hints.append({"area": "Дом и хозяйство", "project": "Виноградник", "title": "Обрезка и укрытие виноградника на зиму"})
        hints.append({"area": "Транспорт", "project": "Текущее обслуживание", "title": "Замена шин на зимние и проверка АКБ"})
        hints.append({"area": "Здоровье", "project": "Питание и Пост", "title": "Рождественский пост (начинается 28 ноября)"})
    
    # Зима (Декабрь, Январь, Февраль)
    else:
        hints.append({"area": "Транспорт", "project": "Текущее обслуживание", "title": "Проверка зимней резины, антифриза и печки"})
        hints.append({"area": "Дом и хозяйство", "project": "Квартира", "title": "Проверка отопительной системы и окон"})

    return hints

def get_fasting_status():
    """Определяет статус питания на сегодня по православному календарю (упрощенная логика)."""
    today = datetime.now()
    month = today.month
    day = today.day
    weekday = today.weekday() # 0=Пн, 2=Ср, 4=Пт
    
    # Основные многодневные посты (даты примерные, можно уточнять по году)
    is_great_lent = (month == 3 and day >= 15) or (month == 4 and day <= 20) # Великий пост
    is_petrov = (month == 6) # Петров пост (примерно)
    is_dormition = (month == 8 and day >= 14 and day <= 27) # Успенский пост
    is_nativity = (month == 11 and day >= 28) or (month == 12) or (month == 1 and day <= 6) # Рождественский пост
    
    is_major_fast = is_great_lent or is_dormition # Самые строгие
    
    # Сплошные седмицы (когда поста нет даже в среду и пятницу) - упрощенно
    is_solid_week = False # Здесь можно добавить логику для Пасхальной, Масленицы и т.д.

    status = "Обычный день"
    color = "#69f0ae" # Зеленый
    advice = "Можно есть всё. Не забудь про овощи и фрукты!"
    task_suggestion = None

    if is_solid_week:
        status = "Сплошная седмица"
        color = "#69f0ae"
        advice = "Поста нет. Можно есть всё."
    elif is_major_fast:
        if weekday in [2, 4]: # Среда и пятница
            status = "Строгий пост (Среда/Пятница)"
            color = "#ff5252" # Красный
            advice = "Исключить: мясо, молоко, яйца, рыбу, масло. Только растительная пища."
            task_suggestion = "Купить продукты для строгого поста"
        else:
            status = "Умеренный пост"
            color = "#ffab40" # Оранжевый
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
            color = "#ffd740" # Желтый
            advice = "Можно рыбу и растительное масло."
    elif weekday in [2, 4] and not is_solid_week:
        status = "Однодневный пост (Среда/Пятница)"
        color = "#ffab40"
        advice = "Исключить мясо и молоко. Рыба и масло разрешены."
        task_suggestion = "Купить рыбу и молочные продукты (завтра можно)"

    return {
        "status": status,
        "color": color,
        "advice": advice,
        "task_suggestion": task_suggestion
    }

def add_note(area: str, project: str, title: str, content: str):
    """Добавляет новую заметку."""
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
    """Получает все заметки, отсортированные по дате."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notes ORDER BY created_at DESC")
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def delete_note(note_id: int):
    """Удаляет заметку."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()

def migrate_projects():
    """Переносит проекты из PROJECTS_BY_AREA в таблицу projects (один раз)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Проверяем, есть ли уже проекты в таблице
    cursor.execute("SELECT COUNT(*) as count FROM projects")
    count = cursor.fetchone()['count']
    
    if count == 0:
        print("🔄 Миграция проектов из кода в базу данных...")
        for area, projects_list in PROJECTS_BY_AREA.items():
            for project_name in projects_list:
                try:
                    cursor.execute(
                        "INSERT INTO projects (area, name) VALUES (?, ?)",
                        (area, project_name)
                    )
                except sqlite3.IntegrityError:
                    pass  # Уже существует
        conn.commit()
        print("✅ Проекты мигрированы в базу данных!")
    
    conn.close()

def get_projects_by_area():
    """Возвращает словарь {area: [project1, project2, ...]} из БД."""
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

def add_project(area: str, name: str):
    """Добавляет новый проект."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO projects (area, name) VALUES (?, ?)", (area, name))
        conn.commit()
        print(f"✅ Проект '{name}' добавлен в область '{area}'")
    except sqlite3.IntegrityError:
        print(f"⚠️ Проект '{name}' уже существует в области '{area}'")
    conn.close()

def archive_project(project_id: int):
    """Архивирует проект (не удаляет, а скрывает)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET is_archived = 1 WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def get_all_projects():
    """Возвращает все проекты (включая архивные) для страницы управления."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY area, is_archived, name")
    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return projects

def update_project(project_id: int, new_name: str, new_area: str):
    """Переименовывает проект и/или меняет его область, обновляя все ссылки."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Получаем старые данные проекта
    cursor.execute("SELECT area, name FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    if not project:
        conn.close()
        return False
    
    old_name = project['name']
    old_area = project['area']
    
    # 2. Обновляем проект в таблице projects
    cursor.execute(
        "UPDATE projects SET name = ?, area = ? WHERE id = ?",
        (new_name, new_area, project_id)
    )
    
    # 3. Обновляем ссылки во всех задачах
    cursor.execute(
        "UPDATE tasks SET project = ?, area = ? WHERE area = ? AND project = ?",
        (new_name, new_area, old_area, old_name)
    )
    
    # 4. Обновляем ссылки во всех заметках
    cursor.execute(
        "UPDATE notes SET project = ?, area = ? WHERE area = ? AND project = ?",
        (new_name, new_area, old_area, old_name)
    )
    
    conn.commit()
    conn.close()
    print(f"✅ Проект обновлён: '{old_area}/{old_name}' → '{new_area}/{new_name}'")
    return True

def restore_project(project_id: int):
    """Восстанавливает проект из архива."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET is_archived = 0 WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    print(f"✅ Проект ID {project_id} восстановлен из архива")

def can_delete_project(project_id: int):
    """Проверяет, можно ли безопасно удалить проект (нет связанных задач/заметок)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT area, name FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    if not project:
        conn.close()
        return False, "Проект не найден"
    
    area = project['area']
    name = project['name']
    
    # Проверяем задачи
    cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE area = ? AND project = ?", (area, name))
    tasks_count = cursor.fetchone()['count']
    
    # Проверяем заметки
    cursor.execute("SELECT COUNT(*) as count FROM notes WHERE area = ? AND project = ?", (area, name))
    notes_count = cursor.fetchone()['count']
    
    conn.close()
    
    if tasks_count > 0 or notes_count > 0:
        return False, f"Нельзя удалить: есть {tasks_count} задач и {notes_count} заметок"
    return True, "Можно удалять"

def delete_project(project_id: int):
    """Удаляет проект навсегда (только если нет связанных задач/заметок)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    print(f"🗑️ Проект ID {project_id} удалён навсегда")

from dateutil.relativedelta import relativedelta # Нам понадобится эта библиотека

def complete_task_and_reschedule(task_id: int):
    """Отмечает задачу как выполненную и, если она повторяющаяся, создаёт следующую."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Получаем данные задачи
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return
    
    task_dict = dict(task)
    
    # 2. Отмечаем текущую как выполненную
    cursor.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
    
    # 3. Если задача повторяющаяся, создаём следующую
    if task_dict['repeat'] and task_dict['repeat'] != 'none':
        next_due_date = None
        if task_dict['due_date']:
            current_date = datetime.strptime(task_dict['due_date'], "%Y-%m-%d").date()
            if task_dict['repeat'] == 'weekly':
                next_due_date = (current_date + relativedelta(weeks=1)).strftime("%Y-%m-%d")
            elif task_dict['repeat'] == 'monthly':
                next_due_date = (current_date + relativedelta(months=1)).strftime("%Y-%m-%d")
            elif task_dict['repeat'] == 'yearly':
                next_due_date = (current_date + relativedelta(years=1)).strftime("%Y-%m-%d")
        
        # Создаём копию задачи со статусом 'active' и новой датой
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO tasks (title, area, project, priority, due_date, repeat, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
        ''', (
            task_dict['title'], task_dict['area'], task_dict['project'], 
            task_dict['priority'], next_due_date, task_dict['repeat'], now
        ))
        print(f"🔄 Создана следующая задача: '{task_dict['title']}' на {next_due_date}")
    
    conn.commit()
    conn.close()

# Инициализация при импорте
init_db()