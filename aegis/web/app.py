import os
import re as pyre
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from aegis.core.utils import get_resource_path
import aegis.core.auth as auth
import aegis.core.utils as utils
from aegis.web.routes.health import router as health_router
from aegis.web.routes.dashboard import router as dashboard_router
from aegis.web.routes.wizard import router as wizard_router
from aegis.web.routes.diagnostics import router as diagnostics_router
from aegis.web.routes.analytics import router as analytics_router
from aegis.web.routes.intelligence import router as intelligence_router
from aegis.web.routes.auditor import router as auditor_router
from aegis.web.routes.security import router as security_router
from aegis.web.routes.command_center import router as command_center_router
from aegis.web.routes.incidents import router as incidents_router
from aegis.web.routes.intelligence_extra import router as intel_extra_router
from aegis.web.routes.automation import router as automation_router
from aegis.web.routes.enhanced import router as enhanced_router
from aegis.web.routes.analytics_extra import router as analytics_extra_router
from aegis.web.routes.smart_features import router as smart_features_router
from fastapi.middleware.cors import CORSMiddleware

def build_app(core) -> FastAPI:
    """Builds and returns the FastAPI application with all routers registered."""
    app = FastAPI(title="Aegis Suite")
    app.state.core = core

    # 1. Resolve and create static directory if missing (Req 6)
    static_path = get_resource_path("static")
    os.makedirs(static_path, exist_ok=True)

    # 2. Mount static folder
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    # 2.5. CORS middleware - restrict to localhost origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # 3. Register authentication and authorization middleware (Req 22.1)
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        
        # Hardening Wizard and Recovery Routes
        if path.startswith("/wizard/") or path.startswith("/api/recovery/"):
            # 1. CSRF/Origin check for state-changing POST/PUT/DELETE requests
            if request.method in ("POST", "PUT", "DELETE"):
                origin = request.headers.get("Origin")
                if origin:
                    web_port = getattr(core, "web_port", None)
                    if web_port is not None:
                        expected_origin = f"http://127.0.0.1:{web_port}"
                        if origin != expected_origin:
                            return JSONResponse(
                                status_code=403,
                                content={"detail": "Forbidden: Cross-Origin Request Blocked."}
                            )
            
            # 2. Check if this is a destructive recovery endpoint
            is_destructive = False
            if path in ("/api/recovery/db/rebuild", "/api/recovery/db/restore", "/api/recovery/restart"):
                is_destructive = True
                
            # 3. Check if we need to enforce auth
            from aegis.core.state import LifecycleState
            current_state = core.state.current_state if core.state else None
            admin_pwd_set = bool(os.environ.get("ADMIN_PASSWORD_HASH"))
            
            # Destructive endpoints always require auth.
            # Other wizard/recovery endpoints require auth only if we are NOT in SAFE_MODE and admin password is set.
            # (i.e. if we are in SAFE_MODE or password is unset, we bypass auth).
            require_auth = True
            if not is_destructive:
                if current_state == LifecycleState.SAFE_MODE or not admin_pwd_set:
                    require_auth = False
                    
            if require_auth:
                auth_header = request.headers.get("Authorization")
                token = None
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    
                if not token or not auth.validate_session(token):
                    return JSONResponse(status_code=401, content={"detail": "Unauthorized: Invalid or missing token"})
                    
                session_role = auth.get_session_role(token)
                if session_role != "admin":
                    return JSONResponse(status_code=403, content={"detail": "Forbidden: Admin privileges required"})
            
            return await call_next(request)
            
        # Allow setup HTML page bypass
        if path == "/setup":
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)
            
        # Allow health and auth endpoints to bypass auth checks
        if (path == "/api/status" or 
            path == "/api/health" or
            path == "/api/public/status" or
            path.startswith("/api/auth/")):
            return await call_next(request)

        # Block other endpoints if admin password setup is incomplete
        if not os.environ.get("ADMIN_PASSWORD_HASH"):
            return JSONResponse(status_code=403, content={"detail": "Forbidden: Complete password setup first."})
            
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
        if not token or not auth.validate_session(token):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized: Invalid or missing token"})
            
        # Enforce guild-level access restriction for tenant sessions
        session_role = auth.get_session_role(token)
        if session_role in ("tenant", "moderator"):
            session_guild_id = auth.get_session_guild_id(token)
            
            # Enforce Sliding-Window Rate Limiting
            if not utils.check_guild_rate_limit(session_guild_id):
                return JSONResponse(status_code=429, content={"detail": "Too many requests. Rate limit is 60 requests per minute."})
                
            # Moderator restrictions: block global admin endpoints and sensitive operations
            if session_role == "moderator":
                moderator_blocked = [
                    "/api/bot/start", "/api/bot/stop",
                    "/api/config/import",
                    "/api/config/export",
                ]
                if path in moderator_blocked or (path.startswith("/api/templates/") and request.method == "DELETE"):
                    return JSONResponse(status_code=403, content={"detail": "Forbidden: Moderator role cannot access this endpoint"})
                if path.startswith("/api/recovery/") or path.startswith("/wizard/"):
                    return JSONResponse(status_code=403, content={"detail": "Forbidden: Moderator role cannot access recovery endpoints"})
                    
            # Strictly block global admin routes for tenant
            if session_role == "tenant":
                if path in ["/api/bot/start", "/api/bot/stop"] or (path.startswith("/api/templates/") and request.method == "DELETE"):
                    return JSONResponse(status_code=403, content={"detail": "Forbidden: Tenant users cannot access global administrative endpoints"})
                
            guild_match = pyre.search(r"/api/guilds/(\d+)", path)
            if guild_match:
                requested_guild_id = guild_match.group(1)
                if requested_guild_id != session_guild_id:
                    return JSONResponse(status_code=403, content={"detail": "Forbidden: Session not authorized for this server"})
            
        return await call_next(request)

    # 4. Always register all routers once (Router Registration Policy)
    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(wizard_router)
    app.include_router(diagnostics_router)
    app.include_router(analytics_router)
    app.include_router(intelligence_router)
    app.include_router(auditor_router)
    app.include_router(security_router)
    app.include_router(command_center_router)
    app.include_router(incidents_router)
    app.include_router(intel_extra_router)
    app.include_router(automation_router)
    app.include_router(enhanced_router)
    app.include_router(analytics_extra_router)
    app.include_router(smart_features_router)

    return app
