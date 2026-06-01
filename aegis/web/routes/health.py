from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/health")
@router.get("/api/health")
def get_health(request: Request):
    """Returns the cached health registry payload without triggering any live probes."""
    core = request.app.state.core
    return core.health.payload()
