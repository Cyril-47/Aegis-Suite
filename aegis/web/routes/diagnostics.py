import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from aegis.diagnostics.packager import generate_package

logger = logging.getLogger("aegis.web.routes.diagnostics")
router = APIRouter()

@router.get("/api/diagnostics/package")
@router.get("/api/diagnostics/download")
def download_diagnostics(request: Request):
    """Generates a zip package containing logs and a sanitized system status snapshot using generate_package."""
    core = request.app.state.core
    try:
        zip_path = generate_package(core)
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=zip_path.name
        )
    except Exception as e:
        logger.exception("Failed to generate diagnostics package")
        raise HTTPException(status_code=500, detail=f"Failed to generate diagnostics package: {e}")
