import json

import httpx
from nicegui import ui

from app import api_client
from app.components.layout import page_frame, require_login
from app.settings import CATEGORIES


@ui.page("/")
def chat_page() -> None:
    if not require_login():
        return
    page_frame("Ask the knowledge base", active="chat")
    state = {"conversation_id": None, "documents": [], "busy": False}

    with ui.row().classes("w-full max-w-5xl mx-auto px-4 gap-4 items-start"):
        # ---- left: conversation ----
        with ui.column().classes("grow gap-3"):
            messages_column = ui.column().classes(
                "w-full gap-3 min-h-[300px] max-h-[55vh] overflow-y-auto"
            )
            with ui.row().classes("w-full items-end gap-2"):
                question = ui.textarea(placeholder="e.g. What is the recommended anticoagulation protocol after hip replacement?").classes(
                    "grow"
                ).props("outlined autogrow input-style=max-height:120px")
                send_btn = ui.button(icon="send").props("round color=primary")
            with ui.row().classes("gap-2"):
                ui.button("New conversation", on_click=lambda: _reset()).props("flat size=sm")

        # ---- right: metadata filters ----
        with ui.card().classes("w-72 shrink-0"):
            ui.label("Retrieval filters").classes("font-bold")
            ui.label("Narrow the searched corpus before asking.").classes("text-xs text-gray-500")
            category_select = ui.select(CATEGORIES, multiple=True, label="Categories").classes(
                "w-full"
            ).props("outlined dense use-chips")
            document_select = ui.select({}, multiple=True, label="Specific documents").classes(
                "w-full"
            ).props("outlined dense use-chips")
            tags_input = ui.input("Tags (comma-separated)").classes("w-full").props("outlined dense")
            with ui.row().classes("w-full gap-2"):
                after_input = ui.input("Uploaded after").classes("grow").props(
                    "outlined dense type=date"
                )
                before_input = ui.input("Uploaded before").classes("grow").props(
                    "outlined dense type=date"
                )
            top_k_slider = ui.slider(min=2, max=20, value=8).props("label-always")
            ui.label("Chunks retrieved (top-k)").classes("text-xs text-gray-500")

    def _reset() -> None:
        state["conversation_id"] = None
        messages_column.clear()

    def build_filters() -> dict | None:
        filters: dict = {}
        if category_select.value:
            filters["categories"] = list(category_select.value)
        if document_select.value:
            filters["document_ids"] = list(document_select.value)
        if tags_input.value and tags_input.value.strip():
            filters["tags"] = [t.strip() for t in tags_input.value.split(",") if t.strip()]
        if after_input.value:
            filters["uploaded_after"] = f"{after_input.value}T00:00:00Z"
        if before_input.value:
            filters["uploaded_before"] = f"{before_input.value}T23:59:59Z"
        return filters or None

    def render_citations(container, citations: list[dict]) -> None:
        if not citations:
            return
        with container:
            with ui.expansion(f"Sources ({len(citations)})", icon="menu_book").classes(
                "w-full bg-blue-50 rounded"
            ):
                for c in citations:
                    page = f", page {c['page_number']}" if c.get("page_number") else ""
                    section = f" — {c['section']}" if c.get("section") else ""
                    ui.label(
                        f"[{c['marker']}] {c['document_title']} (v{c['version_number']}{page}){section}"
                    ).classes("font-medium text-sm")
                    ui.label(f"“{c['excerpt']}”").classes(
                        "text-xs text-gray-600 italic mb-2 whitespace-pre-wrap"
                    )

    async def send() -> None:
        text = (question.value or "").strip()
        if not text or state["busy"]:
            return
        state["busy"] = True
        send_btn.disable()
        question.value = ""
        with messages_column:
            with ui.card().classes("self-end bg-blue-100 max-w-[85%]"):
                ui.label(text).classes("whitespace-pre-wrap")
            answer_card = ui.card().classes("self-start bg-gray-50 max-w-[85%] w-fit")
            with answer_card:
                answer_md = ui.markdown("_Searching the knowledge base…_")
        buffer = ""
        try:
            payload = {
                "conversation_id": state["conversation_id"],
                "question": text,
                "filters": build_filters(),
                "top_k": int(top_k_slider.value),
            }
            async for event, data in api_client.chat_stream(payload):
                if event == "meta":
                    state["conversation_id"] = json.loads(data).get("conversation_id")
                elif event == "token":
                    buffer += data
                    answer_md.content = buffer
                elif event == "notfound":
                    answer_md.content = f"⚠️ {data}"
                elif event == "citations":
                    render_citations(answer_card, json.loads(data))
                elif event == "error":
                    answer_md.content = "⚠️ Something went wrong while answering. Please try again."
        except httpx.HTTPStatusError as exc:
            answer_md.content = f"⚠️ {api_client.api_error_detail(exc)}"
        except httpx.HTTPError:
            answer_md.content = "⚠️ Lost connection to the API."
        finally:
            state["busy"] = False
            send_btn.enable()

    send_btn.on_click(send)
    question.on("keydown.enter.prevent", send)

    async def load_documents() -> None:
        try:
            docs = await api_client.get_json("/api/v1/documents")
        except httpx.HTTPError:
            return
        document_select.set_options({d["id"]: d["title"] for d in docs})

    ui.timer(0.1, load_documents, once=True)
