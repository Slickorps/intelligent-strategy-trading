"""Visual strategy editor (static single-page web UI)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get(
    "/editor",
    summary="Visual strategy editor",
    description="Single-page web editor for composing strategies visually",
)
async def visual_editor() -> FileResponse:
    """Serve the visual strategy editor page."""
    return FileResponse(STATIC_DIR / "editor.html", media_type="text/html")
