import httpx
from nicegui import ui

from app import api_client
from app.components.layout import page_frame, require_login


@ui.page("/admin")
def admin_page() -> None:
    if not require_login():
        return
    page_frame("Admin dashboard", active="admin")

    with ui.column().classes("w-full max-w-5xl mx-auto px-4 gap-4"):
        stats_row = ui.row().classes("w-full gap-4 flex-wrap")
        ui.label("Indexing activity").classes("text-lg font-bold")
        indexing_table = ui.table(
            columns=[
                {"name": "title", "label": "Document", "field": "title", "align": "left"},
                {"name": "version", "label": "Version", "field": "version"},
                {"name": "status", "label": "Status", "field": "status"},
                {"name": "chunks", "label": "Chunks", "field": "chunks"},
                {"name": "ocr_pages", "label": "OCR pages", "field": "ocr_pages"},
                {"name": "created_at", "label": "Uploaded", "field": "created_at", "align": "left"},
                {"name": "error", "label": "Error", "field": "error", "align": "left"},
            ],
            rows=[],
            row_key="version_id",
        ).classes("w-full")

        ui.label("User management").classes("text-lg font-bold")
        with ui.card().classes("w-full gap-2"):
            ui.label("Create user").classes("font-bold")
            with ui.row().classes("w-full gap-2"):
                email = ui.input("Email").classes("grow").props("outlined dense")
                name = ui.input("Full name").classes("grow").props("outlined dense")
                password = ui.input("Password (min 10 chars)", password=True).classes("grow").props("outlined dense")
                role = ui.select(
                    {"admin": "Administrator", "doctor": "Doctor", "researcher": "Researcher"},
                    value="researcher", label="Role",
                ).classes("w-48").props("outlined dense")
                ui.button("Create", on_click=lambda: create_user()).props("color=primary")
        users_table = ui.table(
            columns=[
                {"name": "email", "label": "Email", "field": "email", "align": "left"},
                {"name": "full_name", "label": "Name", "field": "full_name", "align": "left"},
                {"name": "role", "label": "Role", "field": "role"},
                {"name": "is_active", "label": "Active", "field": "is_active"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full")

    def _stat_card(label: str, value) -> None:
        with ui.card().classes("items-center min-w-40"):
            ui.label(str(value if value is not None else "—")).classes("text-2xl font-bold")
            ui.label(label).classes("text-xs text-gray-500")

    async def refresh() -> None:
        try:
            stats = await api_client.get_json("/api/v1/admin/stats")
            indexing = await api_client.get_json("/api/v1/admin/indexing")
            users = await api_client.get_json("/api/v1/auth/users")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                ui.notify("Admin role required", type="negative")
                ui.navigate.to("/")
            return
        except httpx.HTTPError:
            return
        stats_row.clear()
        with stats_row:
            _stat_card("Documents", stats["documents"])
            _stat_card("Indexed chunks", stats["chunks"])
            _stat_card("Users", stats["users"])
            _stat_card("Grounded answers", stats["answers_grounded"])
            _stat_card("Refused (not in corpus)", stats["answers_refused_ungrounded"])
            _stat_card("Avg latency (ms)", stats["avg_answer_latency_ms"])
            for status, count in stats["versions_by_status"].items():
                _stat_card(f"Versions: {status}", count)
        indexing_table.rows = indexing
        users_table.rows = users

    async def create_user() -> None:
        try:
            await api_client.post_json(
                "/api/v1/auth/users",
                {
                    "email": email.value,
                    "full_name": name.value,
                    "password": password.value,
                    "role": role.value,
                },
            )
            ui.notify("User created", type="positive")
            email.value = name.value = password.value = ""
            await refresh()
        except httpx.HTTPStatusError as exc:
            ui.notify(api_client.api_error_detail(exc), type="negative")

    ui.timer(0.1, refresh, once=True)
    ui.timer(10.0, refresh)
