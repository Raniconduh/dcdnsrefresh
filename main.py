import os
import time
import httpx
import logging
import asyncio
import uvicorn
import urllib.parse
import email.utils
from http import HTTPStatus
from cachetools import TLRUCache
from dataclasses import dataclass
from contextlib import asynccontextmanager
from starlette.routing import Route
from starlette.applications import Starlette
from starlette.responses import RedirectResponse, PlainTextResponse

cache_lock = asyncio.Lock()

inflight_locks = [
    asyncio.Lock() for _ in range(256)
]

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("Error: DISCORD_TOKEN not passed in environment variables")
    quit(1)

API = "https://discord.com/api/v10/attachments/refresh-urls"
REPO = "https://github.com/Raniconduh/dcdnrefresh"
VERSION = "1.0.0"

@dataclass
class RefreshedURL:
    val: str = None
    ex: int = None

cache = TLRUCache(
    maxsize=2,
    ttu=lambda k, v, now: v.ex,
    timer=time.time
)

logger = logging.getLogger("uvicorn.error")

def parse_url(refreshed):
    parsed = urllib.parse.urlparse(refreshed)
    qs = urllib.parse.parse_qs(parsed.query)
    try:
        ex = int(qs["ex"][0], base=16)
    except Exception:
        return None

    return RefreshedURL(refreshed, ex)

async def query(app, cdn_url):
    idx = hash(cdn_url) % len(inflight_locks)
    async with inflight_locks[idx]:
        async with cache_lock:
            if cdn_url in cache:
                logger.info(f'Cache hit')
                return HTTPStatus.OK, cache[cdn_url]

        # the result has not been cached
        r = await app.state.client.post(
            API,
            headers={
                "Authorization": f'Bot {TOKEN}',
                "User-Agent": f'DiscordBot ({REPO}, {VERSION})'
            },
            json={
                "attachment_urls": [cdn_url]
            }
        )
        logger.info(f'Fetched from Discord API')

        if r.status_code != HTTPStatus.OK:
            return r.status_code, RefreshedURL()

        try:
            refreshed = r.json()["refreshed_urls"][0]["refreshed"]
        except Exception:
            logger.warning(f'Getting refreshed URL failed for {cdn_url}')
            return HTTPStatus.BAD_GATEWAY, RefreshedURL()

        parsed = parse_url(refreshed)

        if parsed is None:
            logger.warning(f'Could not parse refreshed URL {refreshed}')
            return HTTPStatus.BAD_GATEWAY, RefreshedURL()

        async with cache_lock:
            cache[cdn_url] = parsed

        return HTTPStatus.OK, parsed


async def route(request):
    # canonicalize path
    path = request.path_params["path"]
    path = path.removeprefix("https://")
    path = path.removeprefix("https%3A//")
    path = path.removeprefix("cdn.discordapp.com")
    path = path.removeprefix("/")
    q_pos = path.find("?")
    if q_pos >= 0:
        path = path[:q_pos]

    cdn_url = f'https://cdn.discordapp.com/{path}'
    status, redirect = await query(request.app, cdn_url)

    if status != HTTPStatus.OK:
        return PlainTextResponse(
            content=status.name,
            status_code=status.value
        )

    fmt_ex = email.utils.formatdate(redirect.ex, usegmt=True)

    return RedirectResponse(
        url=redirect.val,
        headers={
            'Expires': fmt_ex
        }
    )

@asynccontextmanager
async def lifespan(app):
    app.state.client = httpx.AsyncClient()

    try:
        yield
    finally:
        await app.state.client.aclose()

app = Starlette(routes=[
    Route('/cdn/{path:path}', route)
],
    lifespan=lifespan
)

if __name__ == '__main__':
    uvicorn.run('main:app', port=8100, log_level='info')
