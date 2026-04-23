import os
import asyncio
import logging
import uuid
from config import DOWNLOADS_DIR, MAX_FILE_SIZE_MB

logger = logging.getLogger(__name__)


class VideoDownloader:
    def __init__(self):
        self.downloads_dir = DOWNLOADS_DIR
        os.makedirs(self.downloads_dir, exist_ok=True)

    async def download(self, url: str) -> dict | None:
        """URL dan video yuklab olish"""
        file_id = str(uuid.uuid4())[:8]
        output_path = os.path.join(self.downloads_dir, f"{file_id}.%(ext)s")

        # cookies.txt mavjud bo'lsa ishlatamiz
        cookies_arg = ""
        cookies_file = os.path.join(os.path.dirname(__file__), "cookies.txt")
        if os.path.exists(cookies_file):
            cookies_arg = f'--cookies "{cookies_file}"'

        cmd = (
            f'yt-dlp '
            f'{cookies_arg} '
            f'--no-playlist '
            f'--max-filesize {MAX_FILE_SIZE_MB}M '
            f'-f "bestvideo[ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]+bestaudio[ext=m4a]/best[ext=mp4]/best" '
            f'--merge-output-format mp4 '
            f'--no-warnings '
            f'--print-json '
            f'-o "{output_path}" '
            f'"{url}"'
        )

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

            if proc.returncode != 0:
                err = stderr.decode(errors='ignore')
                logger.error(f"yt-dlp error: {err[:500]}")
                return None

            # Yuklangan faylni topish
            for f in os.listdir(self.downloads_dir):
                if f.startswith(file_id):
                    filepath = os.path.join(self.downloads_dir, f)
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    if size_mb > MAX_FILE_SIZE_MB:
                        os.remove(filepath)
                        return None

                    # Sarlavhani olish
                    import json
                    title = "Video"
                    try:
                        info = json.loads(stdout.decode(errors='ignore').split('\n')[-2])
                        title = info.get('title', 'Video')
                    except Exception:
                        pass

                    return {
                        'file': filepath,
                        'title': title
                    }

            return None

        except asyncio.TimeoutError:
            logger.error("Download timeout")
            self._cleanup(file_id)
            return None
        except Exception as e:
            logger.error(f"Download error: {e}")
            self._cleanup(file_id)
            return None

    def _cleanup(self, file_id: str):
        for f in os.listdir(self.downloads_dir):
            if f.startswith(file_id):
                try:
                    os.remove(os.path.join(self.downloads_dir, f))
                except Exception:
                    pass
