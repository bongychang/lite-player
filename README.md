# LitePlayer

![Python](https://img.shields.io/badge/Python-3.10%2B-1DB954?style=flat-square&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%2011-000000?style=flat-square&logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-242424?style=flat-square)

A lightweight desktop audio player for Windows built with `libmpv` and `CustomTkinter`. Designed to stay out of the way while gaming or multitasking—keeping RAM usage low, pausing UI overhead in system tray mode, and caching tracks locally without spiking your ping.

<!-- To add a screenshot: upload an image to assets/screenshot.png and uncomment the line below -->
<!-- ![LitePlayer Screenshot](assets/screenshot.png) -->

## Download (Portable Windows Build)

If you just want to run the app without installing Python or dependencies:

1. Go to the [**Releases**](https://github.com/bongychang/lite-player/releases) page.
2. Download the latest `LitePlayer-v1.0-win64.zip`.
3. Extract the folder anywhere and run **`LitePlayer.exe`**.

## Features

**Performance & Audio Engine**
* **Audio-Only Playback:** Powered by `libmpv` (`vid=no`) with a 15 MiB demuxer cap for minimal CPU/RAM usage.
* **Zero-GPU Tray Mode:** Closing the window minimizes the player to the Windows system tray and pauses all UI polling loops.
* **Local LRU Cache & Pre-fetching:** Played tracks are cached locally (2 GB limit) for instant replay. The next track in the queue is pre-fetched in the background at a 500 KB/s rate limit to prevent network/ping spikes.

**Playback & Library**
* **YouTube Music Integration:** Search tracks, load album art, and view live lyrics via `ytmusicapi`.
* **Local SQLite Library:** Persistent storage (`library.db`) for Liked Songs, custom playlists, and Recently Played history.
* **Queue Controls:** Shuffle, Repeat (Off / All / One), Up Next queue view, and a seekable progress bar.

**UI & Quality of Life**
* **Native Windows 11 Styling:** Black/green/white theme with a DWM-styled black title bar and green window border.
* **Built-in Feedback:** Hover tooltips, toast notifications, scroll-wheel volume control, and dynamic taskbar titles.

## Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| `Space` | Play / Pause |
| `←` / `→` | Seek -5s / +5s |
| `↑` / `↓` | Volume +5% / -5% |
| `M` | Mute / Unmute |
| `Ctrl + F` | Focus Search |

## Project Structure

```text
lite-player/
├── app.py           # CustomTkinter UI, Win11 DWM styling, tray icon, shortcuts
├── player.py        # libmpv wrapper, 2 GB LRU cache, rate-limited pre-fetcher
├── extractor.py     # YouTube Music search and lyrics lookup
├── storage.py       # SQLite database for playlists, likes, and history
└── requirements.txt
