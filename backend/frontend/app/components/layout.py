from nicegui import app, ui

from app.settings import DISCLAIMER


def disclaimer_banner() -> None:
    with ui.row().classes(
        "w-full items-center bg-amber-100 text-amber-900 rounded-lg p-3 gap-2"
    ):
        ui.icon("warning").classes("text-xl")
        ui.label(DISCLAIMER).classes("text-sm")


def require_login() -> bool:
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return False
    return True


def page_frame(title: str, active: str) -> None:
    role = app.storage.user.get("role", "")
    with ui.header().classes("items-center bg-blue-900 text-white px-4"):
        ui.icon("medical_information").classes("text-2xl")
        ui.label("MedAssist").classes("text-lg font-bold mr-6")
        links = [("Chat", "/", "chat"), ("Documents", "/documents", "documents")]
        if role == "admin":
            links.append(("Admin", "/admin", "admin"))
        for text, target, key in links:
            classes = "text-white no-underline px-2"
            if key == active:
                classes += " font-bold underline"
            ui.link(text, target).classes(classes)
        ui.space()
        ui.label(f"{app.storage.user.get('full_name', '')} ({role})").classes("text-sm mr-2")
        ui.button("Log out", on_click=_logout).props("flat color=white size=sm")
    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        disclaimer_banner()
        ui.label(title).classes("text-2xl font-bold")


def _logout() -> None:
    app.storage.user.clear()
    ui.navigate.to("/login")
