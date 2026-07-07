from nicegui import ui

from app.pages import admin, chat, documents, login  # noqa: F401 - registers routes
from app.settings import STORAGE_SECRET

ui.run(
    host="0.0.0.0",
    port=8080,
    title="MedAssist",
    storage_secret=STORAGE_SECRET,
    reload=False,
    show=False,
)
