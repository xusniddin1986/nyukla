"""
Health check web server for UptimeRobot keep-alive.
Bu fayl bot.py bilan birgalikda ishlaydigan kichik HTTP server.
"""
from aiohttp import web
import asyncio
import logging

logger = logging.getLogger(__name__)


async def health_check(request):
    return web.Response(text="✅ NyuklaBot is running!", status=200)


async def start_health_server(port: int = 8080):
    """Start a simple HTTP server for health checks."""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Health check server started on port {port}")
    return runner
