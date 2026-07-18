from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import BOOKING_PROVIDER_NAME, config

_template_dir = Path(__file__).parent
_templates = Jinja2Templates(directory=str(_template_dir))


def render(request: Request, name: str, **context) -> HTMLResponse:
    return _templates.TemplateResponse(
        request,
        name,
        {
            "config_version": config.app.version,
            "booking_provider": BOOKING_PROVIDER_NAME,
            **context,
        },
    )
