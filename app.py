import ctypes
import io
import random
import sys
import threading
import tkinter as tk
import customtkinter as ctk
import pystray
import requests
from PIL import Image, ImageDraw

from extractor import get_lyrics, search_songs
from player import AudioPlayer
from storage import LibraryStorage

ctk.set_appearance_mode("dark")

SP_BLACK = "#000000"
SP_BG = "#0E0E0E"
SP_SURFACE = "#161616"
SP_HOVER = "#222222"
SP_BORDER = "#242424"
SP_GREEN = "#1DB954"
SP_GREEN_HOVER = "#1ED760"
SP_TEXT = "#FFFFFF"
SP_MUTED = "#A7A7A7"
SP_DIM = "#6A6A6A"


def style_win11_frame(window):
    # uses Win11 DWM attributes to paint the native titlebar black and border green
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        dwmapi = ctypes.windll.dwmapi
        # COLORREF uses 0x00BBGGRR
        caption_color = ctypes.c_int(0x00000000)
        border_color = ctypes.c_int(0x0054B91D)
        text_color = ctypes.c_int(0x00FFFFFF)
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), 4)
        dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border_color), 4)
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), 4)
    except Exception:
        pass


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d}"


def create_tray_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(29, 185, 84, 255))
    draw.polygon([(25, 19), (25, 45), (47, 32)], fill=(0, 0, 0, 255))
    return img


class ToolTip:
    def __init__(self, widget, text: str, delay: int = 350):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip_win = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self._tip_win or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() - 32

        self._tip_win = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.configure(bg=SP_GREEN)

        lbl = tk.Label(
            tw,
            text=self.text,
            bg=SP_SURFACE,
            fg=SP_TEXT,
            font=("Segoe UI", 9),
            padx=8,
            pady=4,
        )
        lbl.pack(padx=1, pady=1)

        tw.update_idletasks()
        tw.wm_geometry(f"+{max(0, x - tw.winfo_width() // 2)}+{max(0, y)}")

    def _hide(self, _event=None):
        self._cancel()
        if self._tip_win:
            self._tip_win.destroy()
            self._tip_win = None


class CreatePlaylistDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result: str | None = None

        self.title("New Playlist")
        self.geometry("360x175")
        self.resizable(False, False)
        self.configure(fg_color=SP_BG)
        self.transient(parent)
        self.grab_set()

        # center over parent window
        parent.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 360) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 175) // 2
        self.geometry(f"+{px}+{py}")

        style_win11_frame(self)

        ctk.CTkLabel(
            self,
            text="Create Playlist",
            font=("Segoe UI", 16, "bold"),
            text_color=SP_TEXT,
            anchor="w",
        ).pack(fill="x", padx=22, pady=(20, 10))

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="Playlist name...",
            placeholder_text_color=SP_DIM,
            fg_color=SP_SURFACE,
            border_color=SP_BORDER,
            border_width=1,
            text_color=SP_TEXT,
            corner_radius=6,
            height=36,
            font=("Segoe UI", 13),
        )
        self.entry.pack(fill="x", padx=22, pady=(0, 16))
        self.entry.bind("<Return>", lambda _e: self._confirm())
        self.entry.bind("<Escape>", lambda _e: self.destroy())
        self.after(50, self.entry.focus_set)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=22)

        ctk.CTkButton(
            btn_row,
            text="Create",
            width=90,
            height=34,
            corner_radius=17,
            fg_color=SP_GREEN,
            text_color=SP_BLACK,
            hover_color=SP_GREEN_HOVER,
            font=("Segoe UI", 12, "bold"),
            command=self._confirm,
        ).pack(side="right")

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            width=80,
            height=34,
            corner_radius=17,
            fg_color="transparent",
            border_color=SP_BORDER,
            border_width=1,
            text_color=SP_MUTED,
            hover_color=SP_HOVER,
            font=("Segoe UI", 12),
            command=self.destroy,
        ).pack(side="right", padx=(0, 8))

    def _confirm(self):
        val = self.entry.get().strip()
        if val:
            self.result = val
        self.destroy()


class LitePlayerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LITEPLAYER — bongychang")
        self.geometry("1120x690")
        self.minsize(860, 540)
        self.configure(fg_color=SP_BLACK)
        style_win11_frame(self)

        self.db = LibraryStorage()
        self.audio = AudioPlayer(on_track_end=lambda: self.after(0, self._on_track_finished))
        self.tray_icon = None
        self.is_hidden = False

        self.current_view = "home"
        self.search_results: list[dict] = []
        self.original_queue: list[dict] = []
        self.queue: list[dict] = []
        self.queue_index: int = -1
        self.active_song: dict | None = None
        self.row_widgets = {}

        self.shuffle_on = False
        self.repeat_mode = "off"
        self.is_muted = False
        self.prev_volume = 70.0
        self.is_seeking = False
        self.current_duration = 0.0
        self._art_image_ref = None
        self._toast_after_id = None

        self._build_layout()
        self._bind_shortcuts()
        self._refresh_sidebar()
        self._show_home_view()

        self.after(500, self._poll_progress)
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def _build_layout(self):
        body = ctk.CTkFrame(self, fg_color=SP_BLACK, corner_radius=0)
        body.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # sidebar
        self.sidebar = ctk.CTkFrame(body, width=235, fg_color=SP_BG, corner_radius=8)
        self.sidebar.pack(side="left", fill="y", padx=(0, 8))
        self.sidebar.pack_propagate(False)

        brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_frame.pack(fill="x", padx=18, pady=(18, 12))

        ctk.CTkLabel(
            brand_frame,
            text="LITEPLAYER",
            font=("Segoe UI", 16, "bold"),
            text_color=SP_GREEN,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            brand_frame,
            text="- bongychang",
            font=("Consolas", 11),
            text_color=SP_DIM,
            anchor="w",
        ).pack(anchor="w")

        self.nav_home_btn = self._make_sidebar_btn(self.sidebar, "⌂   Home", self._show_home_view)
        ToolTip(self.nav_home_btn, "Recently Played")

        self.nav_search_btn = self._make_sidebar_btn(self.sidebar, "⌕   Search", self._show_search_view)
        ToolTip(self.nav_search_btn, "Search YouTube Music (Ctrl+F)")

        ctk.CTkFrame(self.sidebar, height=1, fg_color=SP_BORDER, corner_radius=0).pack(
            fill="x", padx=14, pady=12
        )

        lib_header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        lib_header.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkLabel(
            lib_header, text="YOUR LIBRARY", font=("Segoe UI", 11, "bold"), text_color=SP_DIM
        ).pack(side="left")

        new_pl_btn = ctk.CTkButton(
            lib_header,
            text="+",
            width=26,
            height=26,
            corner_radius=13,
            fg_color="transparent",
            hover_color=SP_HOVER,
            text_color=SP_GREEN,
            font=("Segoe UI", 16, "bold"),
            command=self._prompt_new_playlist,
        )
        new_pl_btn.pack(side="right")
        ToolTip(new_pl_btn, "Create New Playlist")

        self.playlist_list_frame = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color=SP_BG,
            corner_radius=0,
            scrollbar_button_color=SP_HOVER,
            scrollbar_button_hover_color=SP_DIM,
        )
        self.playlist_list_frame.pack(fill="both", expand=True, padx=6, pady=(0, 10))

        # main panel
        self.main_panel = ctk.CTkFrame(body, fg_color=SP_BG, corner_radius=8)
        self.main_panel.pack(side="left", fill="both", expand=True)

        self.header_frame = ctk.CTkFrame(self.main_panel, fg_color=SP_BG, corner_radius=8)
        self.header_frame.pack(fill="x", padx=24, pady=(20, 12))

        ctk.CTkFrame(self.main_panel, height=1, fg_color=SP_BORDER, corner_radius=0).pack(fill="x")

        self.content_frame = ctk.CTkScrollableFrame(
            self.main_panel,
            fg_color=SP_BG,
            corner_radius=0,
            scrollbar_button_color=SP_HOVER,
            scrollbar_button_hover_color=SP_DIM,
        )
        self.content_frame.pack(fill="both", expand=True, padx=16, pady=8)

        self.toast_label = ctk.CTkLabel(
            self.main_panel,
            text="",
            fg_color=SP_GREEN,
            text_color=SP_BLACK,
            font=("Segoe UI", 12, "bold"),
            corner_radius=16,
            padx=16,
            pady=6,
        )

        # bottom player bar
        player_bar = ctk.CTkFrame(self, fg_color=SP_BLACK, corner_radius=0, height=92)
        player_bar.pack(fill="x", padx=12, pady=4)
        player_bar.pack_propagate(False)

        left_col = ctk.CTkFrame(player_bar, fg_color="transparent", width=295)
        left_col.pack(side="left", fill="y", padx=(8, 8))
        left_col.pack_propagate(False)

        self.art_label = ctk.CTkLabel(
            left_col,
            text="♪",
            width=54,
            height=54,
            corner_radius=4,
            fg_color=SP_SURFACE,
            text_color=SP_GREEN,
            font=("Segoe UI", 20),
        )
        self.art_label.pack(side="left", pady=16, padx=(0, 12))

        info_stack = ctk.CTkFrame(left_col, fg_color="transparent")
        info_stack.pack(side="left", fill="y", pady=20)

        self.now_title = ctk.CTkLabel(
            info_stack, text="Not Playing", font=("Segoe UI", 13, "bold"), text_color=SP_TEXT, anchor="w", width=165
        )
        self.now_title.pack(anchor="w")

        self.now_artist = ctk.CTkLabel(
            info_stack, text="—", font=("Segoe UI", 11), text_color=SP_MUTED, anchor="w", width=165
        )
        self.now_artist.pack(anchor="w")

        self.like_btn = ctk.CTkButton(
            left_col,
            text="♡",
            width=32,
            height=32,
            corner_radius=16,
            fg_color="transparent",
            hover_color=SP_HOVER,
            text_color=SP_MUTED,
            font=("Segoe UI", 16),
            command=self.on_toggle_like_current,
        )
        self.like_btn.pack(side="right", padx=4)
        ToolTip(self.like_btn, "Save to Liked Songs")

        center_col = ctk.CTkFrame(player_bar, fg_color="transparent")
        center_col.pack(side="left", fill="both", expand=True, pady=8)

        btn_row = ctk.CTkFrame(center_col, fg_color="transparent")
        btn_row.pack(pady=(2, 6))

        self.shuffle_btn = self._make_icon_btn(btn_row, "🔀", self.on_toggle_shuffle, "Shuffle")
        self._make_icon_btn(btn_row, "⏮", self.on_prev_track, "Previous Track")

        self.pause_btn = ctk.CTkButton(
            btn_row,
            text="▶",
            width=36,
            height=36,
            corner_radius=18,
            fg_color=SP_GREEN,
            text_color=SP_BLACK,
            hover_color=SP_GREEN_HOVER,
            font=("Segoe UI", 13, "bold"),
            command=self.on_toggle_pause,
        )
        self.pause_btn.pack(side="left", padx=10)
        ToolTip(self.pause_btn, "Play / Pause (Space)")

        self._make_icon_btn(btn_row, "⏭", self.on_next_track, "Next Track")
        self.repeat_btn = self._make_icon_btn(btn_row, "🔁", self.on_cycle_repeat, "Repeat: Off / All / One")

        prog_row = ctk.CTkFrame(center_col, fg_color="transparent")
        prog_row.pack(fill="x", padx=24)

        self.time_elapsed_lbl = ctk.CTkLabel(
            prog_row, text="0:00", font=("Consolas", 10), text_color=SP_MUTED, width=36
        )
        self.time_elapsed_lbl.pack(side="left")

        self.progress_slider = ctk.CTkSlider(
            prog_row,
            from_=0,
            to=100,
            height=12,
            fg_color="#333333",
            progress_color=SP_GREEN,
            button_color=SP_TEXT,
            button_hover_color=SP_GREEN_HOVER,
            command=self._on_slider_drag,
        )
        self.progress_slider.set(0)
        self.progress_slider.pack(side="left", fill="x", expand=True, padx=8)
        self.progress_slider.bind("<ButtonPress-1>", lambda _e: setattr(self, "is_seeking", True))
        self.progress_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        self.time_total_lbl = ctk.CTkLabel(
            prog_row, text="0:00", font=("Consolas", 10), text_color=SP_MUTED, width=36
        )
        self.time_total_lbl.pack(side="right")

        right_col = ctk.CTkFrame(player_bar, fg_color="transparent", width=240)
        right_col.pack(side="right", padx=(8, 8))

        self.lyrics_btn = self._make_icon_btn(right_col, "🎤", self._toggle_lyrics_view, "Lyrics")
        self.queue_btn = self._make_icon_btn(right_col, "☰", self._toggle_queue_view, "Queue")
        self.mute_btn = self._make_icon_btn(right_col, "🔊", self.on_toggle_mute, "Mute / Unmute (M)")

        self.vol_slider = ctk.CTkSlider(
            right_col,
            from_=0,
            to=100,
            width=100,
            height=12,
            fg_color="#333333",
            progress_color=SP_GREEN,
            button_color=SP_TEXT,
            button_hover_color=SP_GREEN_HOVER,
            command=self._on_volume_change,
        )
        self.vol_slider.set(70)
        self.vol_slider.pack(side="left", padx=(4, 0))
        self.vol_slider.bind("<MouseWheel>", self._on_volume_scroll)
        ToolTip(self.vol_slider, "Volume (Scroll or ↑/↓)")

    def _make_icon_btn(self, parent, text, command, tooltip: str):
        btn = ctk.CTkButton(
            parent,
            text=text,
            width=32,
            height=32,
            corner_radius=16,
            fg_color="transparent",
            hover_color=SP_HOVER,
            text_color=SP_MUTED,
            font=("Segoe UI", 13),
            command=command,
        )
        btn.pack(side="left", padx=2)
        ToolTip(btn, tooltip)
        return btn

    def _make_sidebar_btn(self, parent, text, command, active=False):
        btn = ctk.CTkButton(
            parent,
            text=text,
            anchor="w",
            height=36,
            corner_radius=6,
            fg_color=SP_HOVER if active else "transparent",
            hover_color=SP_SURFACE,
            text_color=SP_GREEN if active else SP_MUTED,
            font=("Segoe UI", 13, "bold" if active else "normal"),
            command=command,
        )
        btn.pack(fill="x", padx=8, pady=2)
        return btn

    def _bind_shortcuts(self):
        self.bind("<space>", self._kb_toggle_pause)
        self.bind("<Left>", lambda e: self._kb_seek(e, -5))
        self.bind("<Right>", lambda e: self._kb_seek(e, 5))
        self.bind("<Up>", lambda e: self._kb_volume(e, 5))
        self.bind("<Down>", lambda e: self._kb_volume(e, -5))
        self.bind("m", self._kb_mute)
        self.bind("M", self._kb_mute)
        self.bind("<Control-f>", self._kb_focus_search)

    def _is_typing(self) -> bool:
        return isinstance(self.focus_get(), (tk.Entry, ctk.CTkEntry))

    def _kb_toggle_pause(self, _e):
        if not self._is_typing():
            self.on_toggle_pause()

    def _kb_seek(self, _e, delta: int):
        if not self._is_typing() and self.active_song:
            pos, dur = self.audio.get_progress()
            if dur > 0:
                self.audio.seek(max(0.0, min(dur, pos + delta)))

    def _kb_volume(self, _e, delta: int):
        if not self._is_typing():
            new_vol = max(0, min(100, self.vol_slider.get() + delta))
            self.vol_slider.set(new_vol)
            self._on_volume_change(new_vol)

    def _kb_mute(self, _e):
        if not self._is_typing():
            self.on_toggle_mute()

    def _kb_focus_search(self, _e):
        if self.current_view != "search":
            self._show_search_view()
        if hasattr(self, "search_entry") and self.search_entry.winfo_exists():
            self.search_entry.focus_set()

    def _on_volume_scroll(self, event):
        delta = 5 if event.delta > 0 else -5
        new_vol = max(0, min(100, self.vol_slider.get() + delta))
        self.vol_slider.set(new_vol)
        self._on_volume_change(new_vol)

    def _show_toast(self, message: str):
        if self._toast_after_id:
            self.after_cancel(self._toast_after_id)
        self.toast_label.configure(text=message)
        self.toast_label.place(relx=0.5, rely=0.94, anchor="center")
        self.toast_label.lift()
        self._toast_after_id = self.after(1800, self.toast_label.place_forget)

    def _refresh_sidebar(self):
        self.nav_home_btn.configure(
            fg_color=SP_HOVER if self.current_view == "home" else "transparent",
            text_color=SP_GREEN if self.current_view == "home" else SP_MUTED,
            font=("Segoe UI", 13, "bold" if self.current_view == "home" else "normal"),
        )
        self.nav_search_btn.configure(
            fg_color=SP_HOVER if self.current_view == "search" else "transparent",
            text_color=SP_GREEN if self.current_view == "search" else SP_MUTED,
            font=("Segoe UI", 13, "bold" if self.current_view == "search" else "normal"),
        )
        self.lyrics_btn.configure(text_color=SP_GREEN if self.current_view == "lyrics" else SP_MUTED)
        self.queue_btn.configure(text_color=SP_GREEN if self.current_view == "queue" else SP_MUTED)

        for w in self.playlist_list_frame.winfo_children():
            w.destroy()

        for pl in self.db.get_playlists():
            is_active = self.current_view == pl["id"]
            label = f"♥   {pl['name']}" if pl["is_system"] else f"♫   {pl['name']}"
            self._make_sidebar_btn(
                self.playlist_list_frame,
                label,
                lambda p=pl: self._show_playlist_view(p["id"]),
                active=is_active,
            )

    def _clear_header(self):
        for w in self.header_frame.winfo_children():
            w.destroy()

    def _show_home_view(self):
        self.current_view = "home"
        self._refresh_sidebar()
        self._clear_header()

        ctk.CTkLabel(
            self.header_frame, text="Recently Played", font=("Segoe UI", 24, "bold"), text_color=SP_TEXT
        ).pack(anchor="w")

        recent = self.db.get_recent_tracks(25)
        if recent:
            self._render_track_list(recent, is_playlist=False)
        else:
            self._show_empty_state("Nothing played yet. Head to Search to play your first track.")

    def _show_search_view(self):
        self.current_view = "search"
        self._refresh_sidebar()
        self._clear_header()

        self.search_entry = ctk.CTkEntry(
            self.header_frame,
            placeholder_text="What do you want to play?",
            placeholder_text_color=SP_DIM,
            fg_color=SP_SURFACE,
            border_color=SP_BORDER,
            border_width=1,
            text_color=SP_TEXT,
            corner_radius=18,
            height=38,
            font=("Segoe UI", 13),
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda _e: self.on_search())

        self.search_btn = ctk.CTkButton(
            self.header_frame,
            text="Search",
            width=90,
            height=38,
            corner_radius=19,
            fg_color=SP_GREEN,
            text_color=SP_BLACK,
            hover_color=SP_GREEN_HOVER,
            font=("Segoe UI", 13, "bold"),
            command=self.on_search,
        )
        self.search_btn.pack(side="right")

        if self.search_results:
            self._render_track_list(self.search_results, is_playlist=False)
        else:
            self._show_empty_state("Search for songs, artists, or albums.")

    def _show_playlist_view(self, playlist_id: int):
        self.current_view = playlist_id
        self._refresh_sidebar()
        self._clear_header()

        playlists = {p["id"]: p for p in self.db.get_playlists()}
        pl = playlists.get(playlist_id)
        if not pl:
            self._show_home_view()
            return

        tracks = self.db.get_tracks(playlist_id)

        left = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            left, text=pl["name"], font=("Segoe UI", 26, "bold"), text_color=SP_TEXT, anchor="w"
        ).pack(anchor="w")

        ctk.CTkLabel(
            left,
            text=f"{len(tracks)} song{'s' if len(tracks) != 1 else ''}",
            font=("Segoe UI", 12),
            text_color=SP_MUTED,
            anchor="w",
        ).pack(anchor="w")

        right = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right.pack(side="right")

        if tracks:
            play_btn = ctk.CTkButton(
                right,
                text="▶  Play",
                width=96,
                height=38,
                corner_radius=19,
                fg_color=SP_GREEN,
                text_color=SP_BLACK,
                hover_color=SP_GREEN_HOVER,
                font=("Segoe UI", 13, "bold"),
                command=lambda t=tracks: self.play_from_list(t, 0),
            )
            play_btn.pack(side="left", padx=(0, 8))
            ToolTip(play_btn, "Play Playlist")

        if not pl["is_system"]:
            del_btn = ctk.CTkButton(
                right,
                text="Delete",
                width=74,
                height=34,
                corner_radius=17,
                fg_color="transparent",
                border_color=SP_DIM,
                border_width=1,
                text_color=SP_MUTED,
                hover_color=SP_HOVER,
                font=("Segoe UI", 12),
                command=lambda pid=playlist_id: self._delete_playlist(pid),
            )
            del_btn.pack(side="left")
            ToolTip(del_btn, "Delete Playlist")

        if tracks:
            self._render_track_list(tracks, is_playlist=True, playlist_id=playlist_id)
        else:
            self._show_empty_state("This playlist is empty. Search for songs and click + to add them.")

    def _toggle_lyrics_view(self):
        if self.current_view == "lyrics":
            self._show_home_view()
            return
        self.current_view = "lyrics"
        self._refresh_sidebar()
        self._clear_header()

        title = self.active_song["title"] if self.active_song else "Lyrics"
        ctk.CTkLabel(
            self.header_frame, text=f"Lyrics — {title}", font=("Segoe UI", 20, "bold"), text_color=SP_TEXT
        ).pack(anchor="w")

        if not self.active_song:
            self._show_empty_state("Play a track to view its lyrics.")
            return

        self._show_empty_state("Loading lyrics...")
        vid = self.active_song["video_id"]
        threading.Thread(target=self._lyrics_worker, args=(vid,), daemon=True).start()

    def _lyrics_worker(self, video_id: str):
        text = get_lyrics(video_id)
        self.after(0, lambda: self._render_lyrics(text))

    def _render_lyrics(self, text: str):
        if self.current_view != "lyrics":
            return
        for w in self.content_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.content_frame,
            text=text,
            font=("Segoe UI", 16, "bold"),
            text_color=SP_TEXT,
            justify="left",
            wraplength=700,
        ).pack(anchor="w", padx=20, pady=20)

    def _toggle_queue_view(self):
        if self.current_view == "queue":
            self._show_home_view()
            return
        self.current_view = "queue"
        self._refresh_sidebar()
        self._clear_header()

        ctk.CTkLabel(
            self.header_frame, text="Queue", font=("Segoe UI", 24, "bold"), text_color=SP_TEXT
        ).pack(anchor="w")

        upcoming = self.queue[self.queue_index:] if self.queue and self.queue_index >= 0 else []
        if upcoming:
            self._render_track_list(upcoming, is_playlist=False, is_queue=True)
        else:
            self._show_empty_state("Your queue is empty.")

    def _prompt_new_playlist(self):
        dialog = CreatePlaylistDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            pl_id = self.db.create_playlist(dialog.result)
            if pl_id:
                self._show_playlist_view(pl_id)
                self._show_toast(f"Created playlist '{dialog.result}'")

    def _delete_playlist(self, playlist_id: int):
        self.db.delete_playlist(playlist_id)
        self._show_home_view()
        self._show_toast("Playlist deleted")

    def _show_empty_state(self, message: str):
        self.row_widgets.clear()
        for w in self.content_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.content_frame, text=message, font=("Segoe UI", 13), text_color=SP_MUTED
        ).pack(pady=80)

    def on_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        self.search_btn.configure(state="disabled", text="...")
        self._show_empty_state("Searching...")
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query: str):
        try:
            songs = search_songs(query, limit=18)
        except Exception as e:
            songs = []
            print("Search error:", e)
        self.after(0, lambda: self._on_search_done(songs))

    def _on_search_done(self, songs: list[dict]):
        self.search_results = songs
        if self.current_view == "search":
            self.search_btn.configure(state="normal", text="Search")
            if songs:
                self._render_track_list(songs, is_playlist=False)
            else:
                self._show_empty_state("No results found.")

    def _render_track_list(self, songs: list[dict], is_playlist: bool, playlist_id: int | None = None, is_queue: bool = False):
        self.row_widgets.clear()
        for w in self.content_frame.winfo_children():
            w.destroy()
        for idx, song in enumerate(songs):
            self._create_track_row(idx, song, songs, is_playlist, playlist_id, is_queue)

    def _create_track_row(self, idx: int, song: dict, song_list: list[dict], is_playlist: bool, playlist_id: int | None, is_queue: bool):
        active_vid = self.active_song["video_id"] if self.active_song else None
        is_active = song["video_id"] == active_vid

        row = ctk.CTkFrame(self.content_frame, fg_color=SP_HOVER if is_active else SP_BG, corner_radius=6, cursor="hand2")
        row.pack(fill="x", pady=1, padx=4)

        num_lbl = ctk.CTkLabel(
            row,
            text="▶" if is_active else f"{idx + 1}",
            width=32,
            font=("Consolas", 11),
            text_color=SP_GREEN if is_active else SP_MUTED,
        )
        num_lbl.pack(side="left", padx=(10, 6), pady=10)

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True, pady=8)

        title_lbl = ctk.CTkLabel(
            text_col,
            text=song["title"],
            font=("Segoe UI", 13, "bold" if is_active else "normal"),
            text_color=SP_GREEN if is_active else SP_TEXT,
            anchor="w",
        )
        title_lbl.pack(fill="x")

        artist_lbl = ctk.CTkLabel(
            text_col, text=song["artist"], font=("Segoe UI", 11), text_color=SP_MUTED, anchor="w"
        )
        artist_lbl.pack(fill="x")

        if is_playlist and playlist_id is not None:
            btn = ctk.CTkButton(
                row, text="×", width=28, height=28, corner_radius=14,
                fg_color="transparent", hover_color="#333333", text_color=SP_MUTED,
                font=("Segoe UI", 15),
                command=lambda s=song, pid=playlist_id: self._remove_from_playlist(pid, s["video_id"]),
            )
            btn.pack(side="right", padx=(4, 10))
            ToolTip(btn, "Remove from Playlist")
        elif not is_queue:
            btn = ctk.CTkButton(
                row, text="+", width=28, height=28, corner_radius=14,
                fg_color="transparent", hover_color="#333333", text_color=SP_GREEN,
                font=("Segoe UI", 15, "bold"),
                command=lambda s=song: self._open_track_menu(s),
            )
            btn.pack(side="right", padx=(4, 10))
            ToolTip(btn, "Add to Playlist or Queue")

        dur_lbl = ctk.CTkLabel(
            row, text=song.get("duration", ""), font=("Consolas", 11), text_color=SP_MUTED, width=48, anchor="e"
        )
        dur_lbl.pack(side="right", padx=(8, 6))

        self.row_widgets[song["video_id"]] = (row, num_lbl, title_lbl, idx + 1)

        def on_enter(_e, r=row, vid=song["video_id"]):
            if not (self.active_song and self.active_song["video_id"] == vid):
                r.configure(fg_color=SP_SURFACE)

        def on_leave(_e, r=row, vid=song["video_id"]):
            is_act = self.active_song and self.active_song["video_id"] == vid
            r.configure(fg_color=SP_HOVER if is_act else SP_BG)

        def on_click(_e, lst=song_list, i=idx):
            if is_queue:
                self.queue_index += i
                self._play_current_queue_item()
            else:
                self.play_from_list(lst, i)

        for widget in (row, num_lbl, text_col, title_lbl, artist_lbl, dur_lbl):
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", on_click)

    def _open_track_menu(self, song: dict):
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=SP_SURFACE,
            fg=SP_TEXT,
            activebackground=SP_GREEN,
            activeforeground=SP_BLACK,
            font=("Segoe UI", 11),
            bd=1,
            relief="solid",
        )
        menu.add_command(label="Add to Queue", command=lambda s=song: self._add_to_queue(s))
        menu.add_separator()
        for pl in self.db.get_playlists():
            label = f"♥  {pl['name']}" if pl["is_system"] else pl["name"]
            menu.add_command(
                label=f"Add to {label}",
                command=lambda pid=pl["id"], pname=pl["name"], s=song: self._add_to_playlist(pid, pname, s),
            )
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _add_to_queue(self, song: dict):
        self.queue.append(song)
        self._show_toast("Added to Queue")

    def _add_to_playlist(self, playlist_id: int, playlist_name: str, song: dict):
        self.db.add_track(playlist_id, song)
        self._show_toast(f"Added to {playlist_name}")
        if self.active_song and self.active_song["video_id"] == song["video_id"]:
            self._update_like_button()

    def _remove_from_playlist(self, playlist_id: int, video_id: str):
        self.db.remove_track(playlist_id, video_id)
        self._show_playlist_view(playlist_id)
        self._show_toast("Removed from playlist")

    def _update_active_row_highlight(self, new_vid: str | None):
        for vid, (row, num_lbl, title_lbl, idx) in self.row_widgets.items():
            if vid == new_vid:
                row.configure(fg_color=SP_HOVER)
                num_lbl.configure(text="▶", text_color=SP_GREEN)
                title_lbl.configure(text_color=SP_GREEN, font=("Segoe UI", 13, "bold"))
            else:
                row.configure(fg_color=SP_BG)
                num_lbl.configure(text=f"{idx}", text_color=SP_MUTED)
                title_lbl.configure(text_color=SP_TEXT, font=("Segoe UI", 13, "normal"))

    def play_from_list(self, song_list: list[dict], index: int):
        self.original_queue = list(song_list)
        if self.shuffle_on:
            current = song_list[index]
            rest = [s for i, s in enumerate(song_list) if i != index]
            random.shuffle(rest)
            self.queue = [current] + rest
            self.queue_index = 0
        else:
            self.queue = list(song_list)
            self.queue_index = index
        self._play_current_queue_item()

    def _play_current_queue_item(self):
        if not (0 <= self.queue_index < len(self.queue)):
            return
        song = self.queue[self.queue_index]
        self.active_song = song
        self.db.record_play(song)
        self._update_active_row_highlight(song["video_id"])

        title = song["title"]
        artist = song["artist"]
        self.title(f"{title} — {artist} | LITEPLAYER")
        self.now_title.configure(text=title if len(title) <= 22 else title[:21] + "…")
        self.now_artist.configure(text=artist if len(artist) <= 26 else artist[:25] + "…")
        self.pause_btn.configure(text="❚❚")
        self.progress_slider.set(0)
        self.time_elapsed_lbl.configure(text="0:00")
        self.time_total_lbl.configure(text=song.get("duration", "0:00"))
        self._update_like_button()

        threading.Thread(target=self._load_album_art, args=(song.get("thumbnail"),), daemon=True).start()
        threading.Thread(target=self.audio.play_video_id, args=(song["video_id"],), daemon=True).start()

        # prefetch next track so skipping is instant
        if self.queue_index + 1 < len(self.queue):
            self.audio.prefetch_video_id(self.queue[self.queue_index + 1]["video_id"])

        if self.current_view == "lyrics":
            self._toggle_lyrics_view()
            self._toggle_lyrics_view()
        elif self.current_view == "queue":
            self._toggle_queue_view()
            self._toggle_queue_view()

    def _load_album_art(self, url: str | None):
        if not url:
            return
        try:
            resp = requests.get(url, timeout=5)
            img = Image.open(io.BytesIO(resp.content)).resize((54, 54))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(54, 54))
            self.after(0, lambda: self._set_art_image(ctk_img))
        except Exception:
            pass

    def _set_art_image(self, ctk_img):
        self._art_image_ref = ctk_img
        self.art_label.configure(image=ctk_img, text="")

    def _on_track_finished(self):
        if self.repeat_mode == "one":
            self._play_current_queue_item()
        else:
            self.on_next_track()

    def on_next_track(self):
        if not self.queue:
            return
        if self.queue_index + 1 < len(self.queue):
            self.queue_index += 1
            self._play_current_queue_item()
        elif self.repeat_mode == "all":
            self.queue_index = 0
            self._play_current_queue_item()

    def on_prev_track(self):
        if not self.queue:
            return
        pos, _ = self.audio.get_progress()
        if pos > 3.0:
            self.audio.seek(0)
        elif self.queue_index > 0:
            self.queue_index -= 1
            self._play_current_queue_item()

    def on_toggle_pause(self):
        if not self.active_song:
            return
        is_paused = self.audio.toggle_pause()
        self.pause_btn.configure(text="▶" if is_paused else "❚❚")

    def on_toggle_shuffle(self):
        self.shuffle_on = not self.shuffle_on
        self.shuffle_btn.configure(text_color=SP_GREEN if self.shuffle_on else SP_MUTED)
        self._show_toast("Shuffle On" if self.shuffle_on else "Shuffle Off")
        if self.queue and self.active_song:
            if self.shuffle_on:
                rest = [s for s in self.queue if s["video_id"] != self.active_song["video_id"]]
                random.shuffle(rest)
                self.queue = [self.active_song] + rest
                self.queue_index = 0
            elif self.original_queue:
                self.queue = list(self.original_queue)
                vids = [s["video_id"] for s in self.queue]
                self.queue_index = vids.index(self.active_song["video_id"]) if self.active_song["video_id"] in vids else 0

    def on_cycle_repeat(self):
        modes = ["off", "all", "one"]
        self.repeat_mode = modes[(modes.index(self.repeat_mode) + 1) % 3]
        if self.repeat_mode == "off":
            self.repeat_btn.configure(text="🔁", text_color=SP_MUTED)
            self._show_toast("Repeat Off")
        elif self.repeat_mode == "all":
            self.repeat_btn.configure(text="🔁", text_color=SP_GREEN)
            self._show_toast("Repeat All")
        else:
            self.repeat_btn.configure(text="🔂", text_color=SP_GREEN)
            self._show_toast("Repeat One")

    def _update_like_button(self):
        if self.active_song and self.db.is_liked(self.active_song["video_id"]):
            self.like_btn.configure(text="♥", text_color=SP_GREEN)
        else:
            self.like_btn.configure(text="♡", text_color=SP_MUTED)

    def on_toggle_like_current(self):
        if not self.active_song:
            return
        liked = self.db.toggle_like(self.active_song)
        self._update_like_button()
        self._show_toast("Saved to Liked Songs" if liked else "Removed from Liked Songs")
        if self.current_view == self.db.get_liked_playlist_id():
            self._show_playlist_view(self.current_view)

    def _on_volume_change(self, val: float):
        self.is_muted = val == 0
        self.mute_btn.configure(text="🔇" if self.is_muted else "🔊")
        self.audio.set_volume(val)

    def on_toggle_mute(self):
        if self.is_muted:
            self.is_muted = False
            self.vol_slider.set(self.prev_volume)
            self.audio.set_volume(self.prev_volume)
            self.mute_btn.configure(text="🔊")
        else:
            self.prev_volume = self.vol_slider.get() or 70.0
            self.is_muted = True
            self.vol_slider.set(0)
            self.audio.set_volume(0)
            self.mute_btn.configure(text="🔇")

    def _poll_progress(self):
        # pause UI polling while hidden in tray
        if not self.is_hidden and not self.is_seeking and self.active_song:
            pos, dur = self.audio.get_progress()
            if dur > 0:
                self.current_duration = dur
                self.progress_slider.set(min(100.0, (pos / dur) * 100.0))
                self.time_elapsed_lbl.configure(text=format_time(pos))
                self.time_total_lbl.configure(text=format_time(dur))
        self.after(500, self._poll_progress)

    def _on_slider_drag(self, value: float):
        if self.current_duration > 0:
            self.time_elapsed_lbl.configure(text=format_time((value / 100.0) * self.current_duration))

    def _on_slider_release(self, _event):
        if self.current_duration > 0:
            self.audio.seek((self.progress_slider.get() / 100.0) * self.current_duration)
        self.is_seeking = False

    def hide_to_tray(self):
        self.is_hidden = True
        self.withdraw()
        if self.tray_icon is None:
            menu = pystray.Menu(
                pystray.MenuItem("Show LitePlayer", self.show_from_tray, default=True),
                pystray.MenuItem("Play / Pause", lambda: self.after(0, self.on_toggle_pause)),
                pystray.MenuItem("Next Track", lambda: self.after(0, self.on_next_track)),
                pystray.MenuItem("Quit", self.quit_app),
            )
            self.tray_icon = pystray.Icon(
                "LitePlayer", create_tray_icon_image(), "LitePlayer", menu
            )
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_from_tray(self):
        self.is_hidden = False
        self.after(0, self.deiconify)

    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.audio.shutdown()
        self.after(0, self.destroy)


if __name__ == "__main__":
    app = LitePlayerApp()
    app.mainloop()