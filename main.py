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
    complete_task_and_reschedule
)


app = FastAPI(title="Jarvis Assistant")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, added: int = Query(default=0), area: str = Query(default=None)):
        
    tasks = get_tasks_with_deadline_info(area)
    stats = get_stats()
    hints = get_seasonal_hints()
    fasting = get_fasting_status()
    projects_by_area = get_projects_by_area()  # <-- Теперь из БД!
    
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={
            "user_name": "Олег", 
            "tasks": tasks, 
            "added": added, 
            "current_area": area, 
            "stats": stats,
            "projects_by_area": projects_by_area,  # <-- Динамические проекты
            "seasonal_hints": hints,
            "fasting": fasting
        }
    )

@app.post("/add_task")
async def add_task_handler(request: Request, title: str = Form(...), area: str = Form(...), project: str = Form(...), priority: str = Form(...), due_date: str = Form(None), repeat: str = Form("none")):
    add_task(title, area, project, priority, due_date if due_date else None, repeat)
    return RedirectResponse(url="/?added=1", status_code=303)

@app.post("/complete_task/{task_id}")
async def complete_task_handler(task_id: int):
    complete_task_and_reschedule(task_id)
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
    tasks = get_inbox_tasks()
    tasks_with_suggestions = []
    for task in tasks:
        task['suggested_priority'] = suggest_priority(task['title'], task['area'])
        tasks_with_suggestions.append(task)
    return templates.TemplateResponse(request=request, name="inbox.html", context={"user_name": "Олег", "tasks": tasks_with_suggestions})

@app.post("/set_priority/{task_id}")
async def set_priority_handler(task_id: int, priority: str = Form(...)):
    set_task_priority(task_id, priority)
    return RedirectResponse(url="/inbox", status_code=303)

@app.get("/edit_task/{task_id}", response_class=HTMLResponse)
async def edit_task_page(request: Request, task_id: int):
    task = get_task_by_id(task_id)
    if not task: return HTMLResponse("Задача не найдена", status_code=404)
    projects_by_area = get_projects_by_area()  # <-- Динамически из БД
    return templates.TemplateResponse(
        request=request, name="edit_task.html", 
        context={"user_name": "Олег", "task": task, "projects_by_area": projects_by_area}
    )

@app.post("/edit_task/{task_id}")
async def edit_task_handler(task_id: int, title: str = Form(...), area: str = Form(...), project: str = Form(...), priority: str = Form(...), due_date: str = Form(None)):
    update_task(task_id, title, area, project, priority, due_date if due_date else None)
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete_task/{task_id}")
async def delete_task_handler(task_id: int):
    delete_task(task_id)
    return RedirectResponse(url="/", status_code=303)

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request):
    notes = get_all_notes()
    projects_by_area = get_projects_by_area()  # <-- Динамически из БД
    return templates.TemplateResponse(
        request=request, name="notes.html",
        context={"user_name": "Олег", "notes": notes, "projects_by_area": projects_by_area}
    )

@app.post("/add_note")
async def add_note_handler(request: Request, area: str = Form(...), project: str = Form(...), title: str = Form(...), content: str = Form("")):
    """Добавляет заметку и возвращает на страницу заметок."""
    add_note(area, project, title, content)
    return RedirectResponse(url="/notes", status_code=303)

@app.post("/delete_note/{note_id}")
async def delete_note_handler(note_id: int):
    """Удаляет заметку."""
    delete_note(note_id)
    return RedirectResponse(url="/notes", status_code=303)

@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    """Страница управления проектами."""
    projects = get_all_projects()
    return templates.TemplateResponse(
        request=request, name="projects.html",
        context={"user_name": "Олег", "projects": projects, "areas": list(PROJECTS_BY_AREA.keys())}
    )

@app.post("/add_project")
async def add_project_handler(request: Request, area: str = Form(...), name: str = Form(...)):
    """Добавляет новый проект."""
    add_project(area, name)
    return RedirectResponse(url="/projects", status_code=303)

@app.post("/archive_project/{project_id}")
async def archive_project_handler(project_id: int):
    """Архивирует проект."""
    archive_project(project_id)
    return RedirectResponse(url="/projects", status_code=303)

@app.get("/edit_project/{project_id}", response_class=HTMLResponse)
async def edit_project_page(request: Request, project_id: int):
    """Страница редактирования проекта."""
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
async def edit_project_handler(project_id: int, area: str = Form(...), name: str = Form(...)):
    """Сохраняет изменения проекта (название и/или область)."""
    update_project(project_id, name, area)
    return RedirectResponse(url="/projects", status_code=303)

@app.post("/restore_project/{project_id}")
async def restore_project_handler(project_id: int):
    """Восстанавливает проект из архива."""
    restore_project(project_id)
    return RedirectResponse(url="/projects", status_code=303)

@app.post("/delete_project/{project_id}")
async def delete_project_handler(project_id: int):
    """Удаляет проект навсегда (с проверкой безопасности)."""
    can_delete, message = can_delete_project(project_id)
    if not can_delete:
        # Если нельзя удалить — показываем предупреждение
        return HTMLResponse(f"<h1>⚠️ Нельзя удалить проект</h1><p>{message}</p><a href='/projects'>← Назад</a>", status_code=400)
    delete_project(project_id)
    return RedirectResponse(url="/projects", status_code=303)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)