import locale
import os
import threading
from pathlib import Path

# point python-mpv at the local libmpv-2.dll
os.environ["PATH"] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + os.environ["PATH"]

import mpv
import yt_dlp

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024  # 2GB


class AudioPlayer:
    def __init__(self, on_track_end=None):
        # libmpv crashes on windows if numeric locale isn't C
        locale.setlocale(locale.LC_NUMERIC, "C")
        self.on_track_end = on_track_end
        self._downloading: set[str] = set()
        self._lock = threading.Lock()

        self.player = mpv.MPV(
            vid="no",
            ytdl=True,
            ytdl_format="bestaudio/best",
            ytdl_raw_options="no-playlist=,force-ipv4=",
            cache="yes",
            demuxer_max_bytes="15MiB",
            demuxer_readahead_secs=20,
        )
        self.player.volume = 70

        @self.player.event_callback("end-file")
        def _handle_end_file(event):
            # reason 0 = normal EOF, ignore manual skips/stops
            if event.data.reason == 0 and self.on_track_end:
                self.on_track_end()

    def _get_cached_file(self, video_id: str) -> Path | None:
        for f in CACHE_DIR.glob(f"{video_id}.*"):
            if f.suffix not in (".part", ".ytdl", ".temp"):
                return f
        return None

    def _enforce_cache_limit(self):
        files = [f for f in CACHE_DIR.iterdir() if f.is_file() and f.suffix not in (".part", ".ytdl")]
        total_size = sum(f.stat().st_size for f in files)
        if total_size <= MAX_CACHE_BYTES:
            return
        files.sort(key=lambda f: f.stat().st_atime)
        for f in files:
            try:
                size = f.stat().st_size
                f.unlink()
                total_size -= size
                if total_size <= MAX_CACHE_BYTES:
                    break
            except OSError:
                pass

    def _download_worker(self, video_id: str):
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(CACHE_DIR / f"{video_id}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ratelimit": 500_000,  # cap at 500KB/s so background caching doesn't spike ping
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            self._enforce_cache_limit()
        except Exception as e:
            print(f"Cache download failed for {video_id}: {e}")
        finally:
            with self._lock:
                self._downloading.discard(video_id)

    def prefetch_video_id(self, video_id: str):
        if self._get_cached_file(video_id):
            return
        with self._lock:
            if video_id in self._downloading:
                return
            self._downloading.add(video_id)
        threading.Thread(target=self._download_worker, args=(video_id,), daemon=True).start()

    def play_video_id(self, video_id: str):
        cached = self._get_cached_file(video_id)
        if cached:
            self.player.play(str(cached))
        else:
            self.player.play(f"https://www.youtube.com/watch?v={video_id}")
            self.prefetch_video_id(video_id)
        self.player.pause = False

    def toggle_pause(self) -> bool:
        self.player.pause = not self.player.pause
        return bool(self.player.pause)

    def stop(self):
        self.player.stop()

    def set_volume(self, level: float):
        self.player.volume = max(0, min(100, int(level)))

    def seek(self, seconds: float):
        try:
            self.player.seek(seconds, reference="absolute")
        except Exception:
            pass

    def get_progress(self) -> tuple[float, float]:
        pos = self.player.time_pos or 0.0
        dur = self.player.duration or 0.0
        return float(pos), float(dur)

    def shutdown(self):
        self.player.terminate()