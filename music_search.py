import os
import asyncio
import logging
import uuid
import aiohttp
from config import DOWNLOADS_DIR, DEEZER_API

logger = logging.getLogger(__name__)


class MusicSearcher:
    def __init__(self):
        self.downloads_dir = DOWNLOADS_DIR
        self.api_base = DEEZER_API
        os.makedirs(self.downloads_dir, exist_ok=True)

    async def search(self, query: str, limit: int = 5) -> list:
        """Deezer API orqali musiqa qidirish"""
        url = f"{self.api_base}/search?q={query}&limit={limit}&output=json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    tracks = []
                    for item in data.get('data', [])[:limit]:
                        duration = item.get('duration', 0)
                        mins = duration // 60
                        secs = duration % 60
                        tracks.append({
                            'id': str(item['id']),
                            'title': item.get('title', 'Noma\'lum'),
                            'artist': item.get('artist', {}).get('name', 'Noma\'lum'),
                            'duration': f"{mins}:{secs:02d}" if duration else "",
                            'preview': item.get('preview', ''),
                            'album': item.get('album', {}).get('title', '')
                        })
                    return tracks
        except Exception as e:
            logger.error(f"Deezer search error: {e}")
            return []

    async def download_track(self, track_id: str) -> dict | None:
        """
        Deezer preview (30 soniya) yoki yt-dlp orqali yuklab olish.
        To'liq musiqa uchun yt-dlp ishlatiladi (YouTube Music).
        """
        # Avval track info olamiz
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_base}/track/{track_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return await self._download_via_ytdlp_by_id(track_id)
                    info = await resp.json()

            title = info.get('title', 'track')
            artist = info.get('artist', {}).get('name', '')
            search_query = f"{artist} {title}"

            # YouTube Music orqali to'liq musiqa yuklab olish
            result = await self._download_via_ytdlp(search_query, title, artist)
            return result

        except Exception as e:
            logger.error(f"Track download error: {e}")
            return None

    async def _download_via_ytdlp(self, query: str, title: str, artist: str) -> dict | None:
        """yt-dlp orqali YouTube Music dan musiqa yuklab olish"""
        file_id = str(uuid.uuid4())[:8]
        output_path = os.path.join(self.downloads_dir, f"{file_id}.%(ext)s")

        # YouTube Music qidirish
        search_url = f"ytsearch1:{query}"

        cmd = (
            f'yt-dlp '
            f'--no-playlist '
            f'--extract-audio '
            f'--audio-format mp3 '
            f'--audio-quality 0 '
            f'--max-filesize 20M '
            f'--no-warnings '
            f'-o "{output_path}" '
            f'"{search_url}"'
        )

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                logger.error(f"yt-dlp audio error: {stderr.decode(errors='ignore')[:300]}")
                return None

            for f in os.listdir(self.downloads_dir):
                if f.startswith(file_id):
                    filepath = os.path.join(self.downloads_dir, f)
                    return {
                        'file': filepath,
                        'title': title,
                        'artist': artist
                    }
            return None

        except asyncio.TimeoutError:
            logger.error("Audio download timeout")
            return None
        except Exception as e:
            logger.error(f"Audio download error: {e}")
            return None

    async def _download_via_ytdlp_by_id(self, track_id: str) -> dict | None:
        """Fallback: track_id ni qidiruv so'rovi sifatida ishlatish"""
        return await self._download_via_ytdlp(
            f"music track {track_id}", "Musiqa", "Ijrochi"
        )
