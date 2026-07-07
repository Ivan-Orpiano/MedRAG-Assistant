import httpx
from nicegui import events, ui

from app import api_client
from app.components.layout import page_frame, require_login
from app.settings import CATEGORIES

MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}

STATUS_COLORS = {
    "indexed": "positive",
    "processing": "warning",
    "pending": "grey",
    "failed": "negative",
    "superseded": "grey-5",
}


@ui.page("/documents")
def documents_page() -> None:
    if not require_login():
        return
    page_frame("Document library", active="documents")

    with ui.column().classes("w-full max-w-5xl mx-auto px-4 gap-4"):
        # ---- upload card ----
        with ui.card().classes("w-full"):
            ui.label("Upload a document").classes("font-bold")
            with ui.row().classes("w-full gap-2 items-center"):
                title_input = ui.input("Title").classes("grow").props("outlined dense")
                category_select = ui.select(CATEGORIES, value="clinical_guideline", label="Category").classes(
                    "w-60"
                ).props("outlined dense")
            with ui.row().classes("w-full gap-2 items-center"):
                description_input = ui.input("Description (optional)").classes("grow").props("outlined dense")
                tags_input = ui.input("Tags, comma-separated").classes("w-60").props("outlined dense")
            upload_status = ui.label("").classes("text-sm text-gray-600")

            async def handle_upload(e: events.UploadEventArguments) -> None:
                if not title_input.value or not title_input.value.strip():
                    upload_status.text = "Please set a title before uploading."
                    upload_status.classes(replace="text-sm text-red-600")
                    return
                ext = "." + e.name.rsplit(".", 1)[-1].lower() if "." in e.name else ""
                mime = MIME_BY_EXT.get(ext)
                if not mime:
                    upload_status.text = "Only PDF, DOCX, and TXT are supported."
                    upload_status.classes(replace="text-sm text-red-600")
                    return
                try:
                    await api_client.upload_document(
                        fields={
                            "title": title_input.value.strip(),
                            "category": category_select.value,
                            "description": description_input.value or "",
                            "tags": tags_input.value or "",
                        },
                        filename=e.name,
                        content=e.content.read(),
                        mime=mime,
                    )
                except httpx.HTTPStatusError as exc:
                    upload_status.text = api_client.api_error_detail(exc)
                    upload_status.classes(replace="text-sm text-red-600")
                    return
                upload_status.text = f"Uploaded '{e.name}' — indexing has been queued."
                upload_status.classes(replace="text-sm text-green-700")
                title_input.value = ""
                await refresh_list()

            ui.upload(on_upload=handle_upload, auto_upload=True, max_file_size=50 * 1024 * 1024).classes(
                "w-full"
            ).props("accept=.pdf,.docx,.txt label='Drop PDF / DOCX / TXT here or click to browse'")

        # ---- library ----
        with ui.row().classes("w-full items-center gap-2"):
            filter_category = ui.select({"": "All categories", **CATEGORIES}, value="", label="Filter").classes(
                "w-60"
            ).props("outlined dense")
            ui.button("Refresh", icon="refresh", on_click=lambda: refresh_list()).props("flat")
        library_column = ui.column().classes("w-full gap-2")

    async def refresh_list() -> None:
        params = {"category": filter_category.value} if filter_category.value else None
        try:
            docs = await api_client.get_json("/api/v1/documents", params=params)
        except httpx.HTTPError:
            ui.notify("Could not load documents", type="negative")
            return
        library_column.clear()
        with library_column:
            if not docs:
                ui.label("No documents yet.").classes("text-gray-500")
            for doc in docs:
                _render_document(doc)

    def _render_document(doc: dict) -> None:
        latest = doc["versions"][-1] if doc["versions"] else None
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(doc["title"]).classes("font-bold grow")
                ui.badge(CATEGORIES.get(doc["category"], doc["category"])).props("color=blue-8")
                if latest:
                    ui.badge(f"v{latest['version_number']} · {latest['status']}").props(
                        f"color={STATUS_COLORS.get(latest['status'], 'grey')}"
                    )
                with ui.button(icon="more_vert").props("flat round dense"):
                    with ui.menu():
                        ui.menu_item("Upload new version", lambda d=doc: _new_version_dialog(d))
                        ui.menu_item("Edit metadata", lambda d=doc: _edit_dialog(d))
                        ui.menu_item("Delete (admin)", lambda d=doc: _delete(d))
            if doc.get("description"):
                ui.label(doc["description"]).classes("text-sm text-gray-600")
            if doc.get("tags"):
                with ui.row().classes("gap-1"):
                    for tag in doc["tags"]:
                        ui.badge(tag).props("outline color=grey-7")
            if latest and latest["status"] == "failed":
                ui.label(f"Indexing failed: {latest['error']}").classes("text-xs text-red-600")
            if latest and latest["status"] == "indexed":
                ocr_note = f", {latest['ocr_pages']} OCR pages" if latest["ocr_pages"] else ""
                ui.label(
                    f"{latest['chunk_count']} chunks, {latest['page_count']} pages{ocr_note}"
                ).classes("text-xs text-gray-500")

    def _new_version_dialog(doc: dict) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"New version of '{doc['title']}'").classes("font-bold")

            async def handle(e: events.UploadEventArguments) -> None:
                ext = "." + e.name.rsplit(".", 1)[-1].lower() if "." in e.name else ""
                mime = MIME_BY_EXT.get(ext)
                if not mime:
                    ui.notify("Unsupported file type", type="negative")
                    return
                try:
                    await api_client.upload_document(
                        fields={}, filename=e.name, content=e.content.read(), mime=mime,
                        path=f"/api/v1/documents/{doc['id']}/versions",
                    )
                    ui.notify("New version queued for indexing", type="positive")
                    dialog.close()
                    await refresh_list()
                except httpx.HTTPStatusError as exc:
                    ui.notify(api_client.api_error_detail(exc), type="negative")

            ui.upload(on_upload=handle, auto_upload=True).props("accept=.pdf,.docx,.txt")
        dialog.open()

    def _edit_dialog(doc: dict) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-96 gap-2"):
            ui.label("Edit metadata").classes("font-bold")
            t = ui.input("Title", value=doc["title"]).classes("w-full").props("outlined dense")
            d = ui.input("Description", value=doc.get("description") or "").classes("w-full").props("outlined dense")
            c = ui.select(CATEGORIES, value=doc["category"], label="Category").classes("w-full").props("outlined dense")
            g = ui.input("Tags", value=", ".join(doc.get("tags") or [])).classes("w-full").props("outlined dense")

            async def save() -> None:
                try:
                    await api_client.patch_json(
                        f"/api/v1/documents/{doc['id']}",
                        {
                            "title": t.value,
                            "description": d.value,
                            "category": c.value,
                            "tags": [x.strip() for x in g.value.split(",") if x.strip()],
                        },
                    )
                    dialog.close()
                    await refresh_list()
                except httpx.HTTPStatusError as exc:
                    ui.notify(api_client.api_error_detail(exc), type="negative")

            ui.button("Save", on_click=save).props("color=primary")
        dialog.open()

    async def _delete(doc: dict) -> None:
        try:
            await api_client.delete(f"/api/v1/documents/{doc['id']}")
            ui.notify("Document deleted; vectors are being purged", type="positive")
            await refresh_list()
        except httpx.HTTPStatusError as exc:
            ui.notify(api_client.api_error_detail(exc), type="negative")

    filter_category.on_value_change(lambda _: refresh_list())
    ui.timer(0.1, refresh_list, once=True)
