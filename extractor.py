from ytmusicapi import YTMusic
import yt_dlp

ytmusic = YTMusic()

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
}


def search_songs(query: str, limit: int = 10) -> list[dict]:
    """Search YouTube Music and return clean song metadata."""
    results = ytmusic.search(query, filter="songs", limit=limit)
    songs = []
    for item in results:
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        songs.append({
            "video_id": item["videoId"],
            "title": item["title"],
            "artist": artists,
            "duration": item.get("duration", "0:00"),
            "thumbnail": item["thumbnails"][-1]["url"] if item.get("thumbnails") else None,
        })
    return songs


def get_audio_stream(video_id: str) -> tuple[str, dict]:
    """Resolve the direct audio-only stream URL and required HTTP headers."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(url, download=False)
        return info["url"], info.get("http_headers", {})


def get_lyrics(video_id: str) -> str:
    """Fetch lyrics for a track from YouTube Music."""
    try:
        watch = ytmusic.get_watch_playlist(videoId=video_id)
        lyrics_id = watch.get("lyrics")
        if not lyrics_id:
            return "No lyrics available for this track."
        data = ytmusic.get_lyrics(lyrics_id)
        return data.get("lyrics", "No lyrics available for this track.") if data else "No lyrics available."
    except Exception:
        return "Could not load lyrics for this track."