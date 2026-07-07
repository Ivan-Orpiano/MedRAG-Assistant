import httpx
from nicegui import app, ui

from app import api_client
from app.components.layout import disclaimer_banner


@ui.page("/login")
def login_page() -> None:
    with ui.column().classes("absolute-center items-center w-96 gap-4"):
        ui.icon("medical_information").classes("text-6xl text-blue-900")
        ui.label("MedAssist — Medical Knowledge Assistant").classes("text-xl font-bold text-center")
        disclaimer_banner()
        email = ui.input("Email").classes("w-full").props("outlined")
        password = ui.input("Password", password=True, password_toggle_button=True).classes(
            "w-full"
        ).props("outlined")
        error = ui.label("").classes("text-red-600 text-sm")

        async def do_login() -> None:
            error.text = ""
            try:
                result = await api_client.login(email.value.strip(), password.value)
            except httpx.HTTPStatusError as exc:
                error.text = api_client.api_error_detail(exc)
                return
            except httpx.HTTPError:
                error.text = "Cannot reach the API server."
                return
            app.storage.user.update(
                token=result["access_token"],
                role=result["role"],
                full_name=result["full_name"],
            )
            ui.navigate.to("/")

        password.on("keydown.enter", do_login)
        ui.button("Sign in", on_click=do_login).classes("w-full").props("color=primary")
