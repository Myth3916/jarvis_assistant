from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import uvicorn
from pathlib import Path
from database import (
    get_tasks_with_deadline_info, get_completed_tasks, restore_task, get_stats,
    get_task_by_id, update_task, delete_task, suggest_priority, get_inbox_tasks,
    set_task_priority, add_task, get_seasonal_hints, get_fasting_status,
    add_note, get_all_notes, delete_note, get_projects_by_area,
    add_project, archive_project, get_all_projects, PROJECTS_BY_AREA, update_project,
    restore_project, can_delete_project, delete_project,
    complete_task_and_reschedule,
    get_seasonal_reminders, add_seasonal_reminder, update_seasonal_reminder,
    delete_seasonal_reminder, toggle_seasonal_reminder,
    get_temperature_reminders, add_temperature_reminder, delete_temperature_reminder,
    toggle_temperature_reminder, get_active_temperature_hints, update_temperature_reminder,
    toggle_pin_task, get_today_plan,
    toggle_pin_task, get_today_plan, get_weekly_report
)


app = FastAPI(title="Jarvis Assistant")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, added: int = Query(default=0), area: str = Query(default=None)):
    tasks = get_tasks_with_deadline_info(area)
    stats = get_stats()
    hints = get_seasonal_hints()
    temp_hints = get_active_temperature_hints()
    fasting = get_fasting_status()
    projects_by_area = get_projects_by_area()
    
    # Получаем краткую сводку на сегодня для главной страницы
    today_plan = get_today_plan()
    today_summary = {
        'total': today_plan['stats']['total'],
        'urgent': today_plan['stats']['urgent_count'],
        'overdue': today_plan['stats']['overdue_count'],
        # Берём топ-3 задачи: сначала срочные, потом просроченные
        'top_tasks': (today_plan['urgent_list'] + today_plan['overdue_list'])[:3]
    }
    
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={
            "user_name": "Олег", 
            "tasks": tasks, 
            "added": added, 
            "current_area": area, 
            "stats": stats,
            "projects_by_area": projects_by_area,
            "seasonal_hints": hints,
            "temperature_hints": temp_hints,
            "fasting": fasting,
            "today_summary": today_summary
        }
    )

@app.post("/add_task")
async def add_task_handler(request: Request, title: str = Form(...), area: str = Form(...), project: str = Form(...), priority: str = Form(...), due_date: str = Form(None), repeat: str = Form("none")):
    add_task(title, area, project, priority, due_date if due_date else None, repeat)
    return RedirectResponse(url="/?added=1", status_code=303)

@app.post("/complete_task/{task_id}")
async def complete_task_handler(task_id: int, from_page: str = Form(default="home")):
    complete_task_and_reschedule(task_id)
    
    # Возвращаемся туда, откуда пришли
    if from_page == "today":
        return RedirectResponse(url="/today", status_code=303)
    elif from_page == "inbox":
        return RedirectResponse(url="/inbox", status_code=303)
    else:
        return RedirectResponse(url="/", status_code=303)

@app.get("/archive", response_class=HTMLResponse)
async def archive(request: Request, restored: int = Query(default=0)):
    tasks = get_completed_tasks(limit=50)
    return templates.TemplateResponse(request=request, name="archive.html", context={"user_name": "Олег", "tasks": tasks, "restored": restored})

@app.post("/restore_task/{task_id}")
async def restore_task_handler(task_id: int):
    restore_task(task_id)
    return RedirectResponse(url="/archive?restored=1", status_code=303)

@app.get("/today", response_class=HTMLResponse)
async def today_plan(request: Request):
    from database import get_today_plan
    plan = get_today_plan()
    return templates.TemplateResponse(request=request, name="today.html", context={"user_name": "Олег", "plan": plan})

@app.get("/inbox", response_class=HTMLResponse)
async def inbox_page(request: Request):
    # get_inbox_tasks() теперь возвращает задачи с полем project_weight и сортирует по весу
    tasks = get_inbox_tasks()
    
    # Добавляем рекомендуемый приоритет для каждой задачи
    tasks_with_suggestions = []
    for task in tasks:
        task['suggested_priority'] = suggest_priority(task['title'], task['area'])
        tasks_with_suggestions.append(task)
    
    return templates.TemplateResponse(
        request=request, 
        name="inbox.html", 
        context={
            "user_name": "Олег", 
            "tasks": tasks_with_suggestions,
            "has_tasks": len(tasks) > 0  # Флаг для шаблона
        }
    )

@app.post("/set_priority/{task_id}")
async def set_priority_handler(task_id: int, priority: str = Form(...)):
    set_task_priority(task_id, priority)
    return RedirectResponse(url="/inbox", status_code=303)

@app.get("/edit_task/{task_id}", response_class=HTMLResponse)
async def edit_task_page(request: Request, task_id: int, from_page: str = Query(default="home")):
    task = get_task_by_id(task_id)
    if not task: return HTMLResponse("Задача не найдена", status_code=404)
    projects_by_area = get_projects_by_area()
    return templates.TemplateResponse(
        request=request, name="edit_task.html", 
        context={
            "user_name": "Олег", 
            "task": task, 
            "projects_by_area": projects_by_area,
            "from_page": from_page
        }
    )

@app.post("/edit_task/{task_id}")
async def edit_task_handler(
    task_id: int, 
    title: str = Form(...), 
    area: str = Form(...), 
    project: str = Form(...), 
    priority: str = Form(...), 
    due_date: str = Form(None),
    repeat: str = Form("none"),
    from_page: str = Form("home")
):
    update_task(task_id, title, area, project, priority, due_date if due_date else None, repeat)
    
    # Редиректим туда, откуда пришли
    if from_page == "inbox":
        return RedirectResponse(url="/inbox", status_code=303)
    elif from_page == "today":
        return RedirectResponse(url="/today", status_code=303)
    elif from_page == "archive":
        return RedirectResponse(url="/archive", status_code=303)
    else:
        return RedirectResponse(url="/", status_code=303)

@app.post("/delete_task/{task_id}")
async def delete_task_handler(task_id: int):
    delete_task(task_id)
    return RedirectResponse(url="/", status_code=303)

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request):
    notes = get_all_notes()
    projects_by_area = get_projects_by_area()
    return templates.TemplateResponse(
        request=request, name="notes.html",
        context={
            "user_name": "Олег", 
            "notes": notes, 
            "projects_by_area": projects_by_area,
            "areas": list(PROJECTS_BY_AREA.keys())
        }
    )

@app.post("/add_note")
async def add_note_handler(request: Request, area: str = Form(...), project: str = Form(...), title: str = Form(...), content: str = Form("")):
    add_note(area, project, title, content)
    return RedirectResponse(url="/notes", status_code=303)

@app.post("/delete_note/{note_id}")
async def delete_note_handler(note_id: int):
    delete_note(note_id)
    return RedirectResponse(url="/notes", status_code=303)

@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    projects = get_all_projects()
    return templates.TemplateResponse(
        request=request, name="projects.html",
        context={"user_name": "Олег", "projects": projects, "areas": list(PROJECTS_BY_AREA.keys())}
    )

@app.post("/add_project")
async def add_project_handler(
    request: Request, 
    area: str = Form(...), 
    name: str = Form(...),
    strategic_weight: int = Form(5)
):
    add_project(area, name, strategic_weight)
    return RedirectResponse(url="/projects", status_code=303)

@app.post("/archive_project/{project_id}")
async def archive_project_handler(project_id: int):
    archive_project(project_id)
    return RedirectResponse(url="/projects", status_code=303)

@app.get("/edit_project/{project_id}", response_class=HTMLResponse)
async def edit_project_page(request: Request, project_id: int):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project = dict(cursor.fetchone())
    conn.close()
    
    if not project:
        return HTMLResponse("Проект не найден", status_code=404)
    
    return templates.TemplateResponse(
        request=request, name="edit_project.html",
        context={"user_name": "Олег", "project": project, "areas": list(PROJECTS_BY_AREA.keys())}
    )

@app.post("/edit_project/{project_id}")
async def edit_project_handler(
    project_id: int, 
    area: str = Form(...), 
    name: str = Form(...),
    strategic_weight: int = Form(5)
):
    update_project(project_id, name, area, strategic_weight)
    return RedirectResponse(url="/projects", status_code=303)

@app.post("/restore_project/{project_id}")
async def restore_project_handler(project_id: int):
    restore_project(project_id)
    return RedirectResponse(url="/projects", status_code=303)

@app.post("/delete_project/{project_id}")
async def delete_project_handler(project_id: int):
    can_delete, message = can_delete_project(project_id)
    if not can_delete:
        return HTMLResponse(f"<h1>⚠️ Нельзя удалить проект</h1><p>{message}</p><a href='/projects'>← Назад</a>", status_code=400)
    delete_project(project_id)
    return RedirectResponse(url="/projects", status_code=303)

@app.get("/seasonal", response_class=HTMLResponse)
async def seasonal_page(request: Request):
    reminders = get_seasonal_reminders()
    temp_reminders = get_temperature_reminders()  
    return templates.TemplateResponse(
        request=request, name="seasonal.html",
        context={
            "user_name": "Олег", 
            "reminders": reminders, 
            "temp_reminders": temp_reminders,  
            "projects_by_area": get_projects_by_area(),
            "areas": list(PROJECTS_BY_AREA.keys())
        }
    )

@app.post("/add_seasonal_reminder")
async def add_seasonal_reminder_handler(
    request: Request,
    title: str = Form(...),
    area: str = Form(...),
    project: str = Form(...),
    month_start: int = Form(...),
    month_end: int = Form(...),
    priority: str = Form("later")
):
    add_seasonal_reminder(title, area, project, month_start, month_end, priority)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/edit_seasonal_reminder/{reminder_id}")
async def edit_seasonal_reminder_handler(
    reminder_id: int,
    title: str = Form(...),
    area: str = Form(...),
    project: str = Form(...),
    month_start: int = Form(...),
    month_end: int = Form(...),
    priority: str = Form(...)
):
    update_seasonal_reminder(reminder_id, title, area, project, month_start, month_end, priority)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/delete_seasonal_reminder/{reminder_id}")
async def delete_seasonal_reminder_handler(reminder_id: int):
    delete_seasonal_reminder(reminder_id)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/toggle_seasonal_reminder/{reminder_id}")
async def toggle_seasonal_reminder_handler(reminder_id: int):
    toggle_seasonal_reminder(reminder_id)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/add_temperature_reminder")
async def add_temperature_reminder_handler(
    title: str = Form(...),
    area: str = Form(...),
    project: str = Form(...),
    operator: str = Form(...),
    temperature: float = Form(...),
    priority: str = Form("later")
):
    add_temperature_reminder(title, area, project, operator, temperature, priority)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/delete_temperature_reminder/{reminder_id}")
async def delete_temperature_reminder_handler(reminder_id: int):
    delete_temperature_reminder(reminder_id)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/toggle_temperature_reminder/{reminder_id}")
async def toggle_temperature_reminder_handler(reminder_id: int):
    toggle_temperature_reminder(reminder_id)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/edit_temperature_reminder/{reminder_id}")
async def edit_temperature_reminder_handler(
    reminder_id: int,
    title: str = Form(...),
    area: str = Form(...),
    project: str = Form(...),
    operator: str = Form(...),
    temperature: float = Form(...),
    priority: str = Form(...)
):
    update_temperature_reminder(reminder_id, title, area, project, operator, temperature, priority)
    return RedirectResponse(url="/seasonal", status_code=303)

@app.post("/toggle_pin/{task_id}")
async def toggle_pin_handler(task_id: int):
    toggle_pin_task(task_id)
    return RedirectResponse(url="/today", status_code=303)

@app.get("/report", response_class=HTMLResponse)
async def weekly_report_page(request: Request):
    """Страница еженедельного стратегического отчёта."""
    report = get_weekly_report()
    return templates.TemplateResponse(
        request=request, name="report.html", 
        context={"user_name": "Олег", "report": report}
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)