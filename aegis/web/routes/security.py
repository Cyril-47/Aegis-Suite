from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/api/guilds/{guild_id}/permissions")
async def analyze_permissions(guild_id: str, request: Request):
    from aegis.web.routes.dashboard import get_active_bot
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.bot.permission_analyzer import PermissionAnalyzer
    analyzer = PermissionAnalyzer(bot)
    result = await analyzer.analyze_permissions(int(guild_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/api/guilds/{guild_id}/config-doctor")
async def diagnose_config(guild_id: str, request: Request):
    from aegis.web.routes.dashboard import get_active_bot
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.bot.config_doctor import ConfigDoctor
    doctor = ConfigDoctor(bot)
    result = await doctor.diagnose_config(int(guild_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/api/guilds/{guild_id}/security-overview")
async def security_overview(guild_id: str, request: Request):
    from aegis.web.routes.dashboard import get_active_bot
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.bot.security_center import SecurityCenter
    center = SecurityCenter(bot)
    result = await center.get_security_overview(int(guild_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
