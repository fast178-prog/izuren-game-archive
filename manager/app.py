from __future__ import annotations

import base64
import ctypes
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk

APP_NAME = "IzurenVideoManager"
CHANNEL_HANDLE = "izuren_world"
REPO = "fast178-prog/izuren-game-archive"
BRANCH = "main"
CUTOFF_UTC = dt.datetime(2026, 8, 27, 15, 0, tzinfo=dt.timezone.utc)
CHECK_MINUTES = 30
DATA_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME
STATE_FILE = DATA_DIR / "state.json"
SECRET_FILE = DATA_DIR / "secrets.bin"


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def http_json(url, headers=None, method="GET", body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def dpapi(data: bytes, protect=True) -> bytes:
    source = ctypes.create_string_buffer(data)
    source_blob = DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DataBlob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    args = (ctypes.byref(source_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not fn(*args):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def load_secrets():
    if not SECRET_FILE.exists():
        return {}
    raw = SECRET_FILE.read_bytes()
    if os.name == "nt":
        raw = dpapi(raw, False)
    return json.loads(raw.decode("utf-8"))


def save_secrets(value):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value).encode("utf-8")
    if os.name == "nt":
        raw = dpapi(raw, True)
    SECRET_FILE.write_bytes(raw)


class Store:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data = {"candidates": {}, "decisions": {}, "playlist_members": {}, "last_check": None}
        if STATE_FILE.exists():
            self.data.update(json.loads(STATE_FILE.read_text("utf-8")))

    def save(self):
        STATE_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")


class YouTube:
    def __init__(self, key):
        self.key = key

    def get(self, resource, **params):
        params["key"] = self.key
        url = "https://www.googleapis.com/youtube/v3/" + resource + "?" + urllib.parse.urlencode(params)
        return http_json(url)

    def pages(self, resource, **params):
        token = None
        while True:
            if token:
                params["pageToken"] = token
            result = self.get(resource, **params)
            yield from result.get("items", [])
            token = result.get("nextPageToken")
            if not token:
                break

    def channel(self):
        result = self.get("channels", part="contentDetails", forHandle=CHANNEL_HANDLE)
        if not result.get("items"):
            raise RuntimeError("유튜브 채널을 찾지 못했습니다.")
        item = result["items"][0]
        return item["id"], item["contentDetails"]["relatedPlaylists"]["uploads"]

    def scan(self):
        channel_id, uploads_id = self.channel()
        videos = []
        for item in self.pages("playlistItems", part="snippet", playlistId=uploads_id, maxResults=50):
            sn = item["snippet"]
            published = parse_time(sn["publishedAt"])
            if published < CUTOFF_UTC:
                break
            vid = sn["resourceId"]["videoId"]
            videos.append({"key": "video:" + vid, "kind": "video", "id": vid,
                           "title": sn["title"], "publishedAt": sn["publishedAt"],
                           "date": published.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat(),
                           "url": "https://youtu.be/" + vid,
                           "thumbnail": thumbnail(sn), "playlists": []})

        playlists = []
        members = {}
        for pl in self.pages("playlists", part="snippet,contentDetails", channelId=channel_id, maxResults=50):
            sn = pl["snippet"]
            if parse_time(sn["publishedAt"]) < CUTOFF_UTC:
                continue
            pid = pl["id"]
            member_ids = []
            for pi in self.pages("playlistItems", part="snippet", playlistId=pid, maxResults=50):
                rid = pi["snippet"].get("resourceId", {})
                if rid.get("kind") == "youtube#video":
                    member_ids.append(rid["videoId"])
            members[pid] = member_ids
            published = parse_time(sn["publishedAt"])
            playlists.append({"key": "playlist:" + pid, "kind": "playlist", "id": pid,
                              "title": sn["title"], "publishedAt": sn["publishedAt"],
                              "date": published.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat(),
                              "url": "https://www.youtube.com/playlist?list=" + pid,
                              "thumbnail": thumbnail(sn), "members": member_ids})
        for video in videos:
            video["playlists"] = [pid for pid, ids in members.items() if video["id"] in ids]
        return videos + playlists, members


def thumbnail(sn):
    choices = sn.get("thumbnails", {})
    for name in ("medium", "high", "default"):
        if name in choices:
            return choices[name]["url"]
    return ""


class GitHub:
    def __init__(self, token):
        self.headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": APP_NAME}

    def load_videos(self):
        url = f"https://api.github.com/repos/{REPO}/contents/videos.json?ref={BRANCH}"
        result = http_json(url, self.headers)
        content = base64.b64decode(result["content"]).decode("utf-8")
        return json.loads(content), result["sha"]

    def add_record(self, record):
        videos, sha = self.load_videos()
        canonical = normalize_url(record["url"])
        if any(normalize_url(v.get("url", "")) == canonical for v in videos):
            raise RuntimeError("이미 같은 링크가 등록되어 있습니다.")
        videos.insert(0, record)
        payload = {"message": f"Add {record['gameTitle']}", "branch": BRANCH, "sha": sha,
                   "content": base64.b64encode((json.dumps(videos, ensure_ascii=False, indent=2) + "\n").encode()).decode()}
        url = f"https://api.github.com/repos/{REPO}/contents/videos.json"
        return http_json(url, self.headers, "PUT", payload)


def normalize_url(url):
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "youtu.be" in parsed.netloc:
        return "video:" + parsed.path.strip("/")
    if "list" in query:
        return "playlist:" + query["list"][0]
    if "v" in query:
        return "video:" + query["v"][0]
    return url


def suggest_genres(title, history):
    title_chars = set(title.lower().replace(" ", ""))
    scores = []
    for row in history:
        other = set(str(row.get("gameTitle", "")).lower().replace(" ", ""))
        union = title_chars | other
        score = len(title_chars & other) / len(union) if union else 0
        if score:
            scores.append((score, row.get("genre", "")))
    weights = {}
    for score, genres in sorted(scores, reverse=True)[:12]:
        for genre in str(genres).split(","):
            genre = genre.strip()
            if genre:
                weights[genre] = weights.get(genre, 0) + score
    return [g for g, _ in sorted(weights.items(), key=lambda x: -x[1])[:5]]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("이즈렌 영상 등록 관리")
        self.geometry("1020x720")
        self.minsize(840, 600)
        self.store = Store()
        self.secrets = load_secrets()
        self.history = []
        self.current_key = None
        self.configure(bg="#f5f3ee")
        self.build_ui()
        if "--background" in sys.argv and self.secrets.get("youtube_api_key") and self.secrets.get("github_token"):
            self.withdraw()
        self.after(300, self.startup)
        self.after(CHECK_MINUTES * 60 * 1000, self.periodic_check)

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", padding=8)
        header = tk.Frame(self, bg="#17213a", padx=24, pady=18)
        header.pack(fill="x")
        tk.Label(header, text="이즈렌 영상 등록 관리", font=("맑은 고딕", 20, "bold"),
                 fg="white", bg="#17213a").pack(side="left")
        self.status = tk.Label(header, text="준비 중", fg="#b9c8ea", bg="#17213a")
        self.status.pack(side="right")
        body = tk.Frame(self, bg="#f5f3ee", padx=18, pady=18)
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg="white", width=330, bd=1, relief="solid")
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="승인 대기", font=("맑은 고딕", 14, "bold"), bg="white", pady=12).pack()
        self.listbox = tk.Listbox(left, font=("맑은 고딕", 10), bd=0, highlightthickness=0)
        self.listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.listbox.bind("<<ListboxSelect>>", self.select_candidate)
        right = tk.Frame(body, bg="white", padx=22, pady=18, bd=1, relief="solid")
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.kind_label = tk.Label(right, text="새 항목을 확인하세요", font=("맑은 고딕", 12, "bold"), bg="white")
        self.kind_label.pack(anchor="w")
        self.conflict = tk.Label(right, text="", fg="#b54708", bg="white", wraplength=580, justify="left")
        self.conflict.pack(anchor="w", pady=(8, 12))
        self.fields = {}
        for key, label in (("gameTitle", "제목"), ("date", "게시 날짜"), ("genre", "장르"), ("memo", "메모"), ("url", "링크")):
            tk.Label(right, text=label, bg="white", fg="#384152").pack(anchor="w", pady=(8, 3))
            entry = ttk.Entry(right, font=("맑은 고딕", 11))
            entry.pack(fill="x")
            self.fields[key] = entry
        self.suggestions = tk.Frame(right, bg="white")
        self.suggestions.pack(fill="x", pady=10)
        buttons = tk.Frame(right, bg="white")
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="등록", command=lambda: self.decide("register")).pack(side="left")
        ttk.Button(buttons, text="이번만 제외", command=lambda: self.decide("exclude")).pack(side="left", padx=8)
        ttk.Button(buttons, text="보류", command=lambda: self.decide("hold")).pack(side="left")
        ttk.Button(buttons, text="지금 새로 확인", command=self.check_async).pack(side="right")

    def startup(self):
        if not self.secrets.get("youtube_api_key") or not self.secrets.get("github_token"):
            self.setup_dialog()
        if self.secrets.get("youtube_api_key") and self.secrets.get("github_token"):
            self.check_async()

    def setup_dialog(self):
        win = tk.Toplevel(self)
        win.title("최초 설정")
        win.transient(self); win.grab_set(); win.geometry("620x260")
        tk.Label(win, text="최초 한 번만 입력합니다", font=("맑은 고딕", 15, "bold")).pack(pady=15)
        rows = {}
        for key, label in (("youtube_api_key", "YouTube Data API 키"), ("github_token", "GitHub 토큰")):
            frame = tk.Frame(win); frame.pack(fill="x", padx=24, pady=6)
            tk.Label(frame, text=label, width=22, anchor="w").pack(side="left")
            entry = ttk.Entry(frame, show="*", width=46); entry.pack(side="left", fill="x", expand=True)
            entry.insert(0, self.secrets.get(key, "")); rows[key] = entry
        def save():
            values = {k: e.get().strip() for k, e in rows.items()}
            if not all(values.values()): return
            save_secrets(values); self.secrets = values; win.destroy(); self.check_async()
        ttk.Button(win, text="저장하고 시작", command=save).pack(pady=18)

    def check_async(self):
        self.status.config(text="새 영상 확인 중…")
        threading.Thread(target=self.check, daemon=True).start()

    def periodic_check(self):
        if self.secrets.get("youtube_api_key") and self.secrets.get("github_token"):
            self.check_async()
        self.after(CHECK_MINUTES * 60 * 1000, self.periodic_check)

    def check(self):
        try:
            yt = YouTube(self.secrets["youtube_api_key"])
            items, members = yt.scan()
            gh = GitHub(self.secrets["github_token"])
            self.history, _ = gh.load_videos()
            for item in items:
                if item["key"] not in self.store.data["decisions"]:
                    self.store.data["candidates"][item["key"]] = item
            self.store.data["playlist_members"] = members
            self.store.data["last_check"] = now_iso(); self.store.save()
            self.after(0, self.refresh)
            self.after(0, lambda: self.status.config(text="확인 완료"))
            if self.store.data["candidates"]:
                self.after(0, self.notify)
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("확인 실패", str(exc)))
            self.after(0, lambda: self.status.config(text="확인 실패"))

    def notify(self):
        self.deiconify(); self.lift(); self.attributes("-topmost", True); self.after(800, lambda: self.attributes("-topmost", False))
        if os.name == "nt":
            try:
                ctypes.windll.user32.FlashWindow(ctypes.windll.user32.GetParent(self.winfo_id()), True)
            except Exception:
                pass

    def refresh(self):
        self.keys = sorted(self.store.data["candidates"], key=lambda k: self.store.data["candidates"][k]["publishedAt"], reverse=True)
        self.listbox.delete(0, "end")
        for key in self.keys:
            item = self.store.data["candidates"][key]
            icon = "재생목록" if item["kind"] == "playlist" else "영상"
            self.listbox.insert("end", f"[{icon}] {item['title']}")
        if self.keys:
            self.listbox.selection_set(0); self.show(self.keys[0])

    def select_candidate(self, _event=None):
        sel = self.listbox.curselection()
        if sel: self.show(self.keys[sel[0]])

    def show(self, key):
        self.current_key = key; item = self.store.data["candidates"][key]
        self.kind_label.config(text="새 재생목록" if item["kind"] == "playlist" else "새 업로드 영상")
        related = item.get("playlists", [])
        if item["kind"] == "playlist":
            related_count = sum(1 for v in self.store.data["candidates"].values() if v.get("kind") == "video" and v["id"] in item.get("members", []))
            text = f"현재 개별 영상 후보 {related_count}개와 겹칩니다. 재생목록을 등록하면 해당 영상은 각각 등록할지 물어봅니다." if related_count else "겹치는 새 영상이 없습니다."
        else:
            text = f"이 영상은 새 재생목록 {len(related)}개에 포함되어 있습니다. 개별 영상으로도 등록할지 선택하세요." if related else "겹치는 새 재생목록이 없습니다."
        self.conflict.config(text=text)
        values = {"gameTitle": item["title"], "date": item["date"], "genre": "", "memo": "", "url": item["url"]}
        for k, entry in self.fields.items(): entry.delete(0, "end"); entry.insert(0, values[k])
        for child in self.suggestions.winfo_children(): child.destroy()
        for genre in suggest_genres(item["title"], self.history):
            ttk.Button(self.suggestions, text=genre, command=lambda g=genre: self.add_genre(g)).pack(side="left", padx=(0, 5))

    def add_genre(self, genre):
        entry = self.fields["genre"]; current = [x.strip() for x in entry.get().split(",") if x.strip()]
        if genre not in current: current.append(genre)
        entry.delete(0, "end"); entry.insert(0, ",".join(current))

    def decide(self, action):
        if not self.current_key: return
        key = self.current_key
        if action == "hold": return
        if action == "register":
            record = {k: e.get().strip() for k, e in self.fields.items()}
            if not record["gameTitle"] or not record["url"]:
                messagebox.showwarning("확인", "제목과 링크는 필수입니다."); return
            try:
                GitHub(self.secrets["github_token"]).add_record(record)
            except Exception as exc:
                messagebox.showerror("등록 실패", str(exc)); return
        self.store.data["decisions"][key] = {"action": action, "at": now_iso()}
        self.store.data["candidates"].pop(key, None); self.store.save(); self.current_key = None; self.refresh()
        messagebox.showinfo("완료", "사이트 목록에 등록했습니다." if action == "register" else "이번 항목을 제외했습니다.")


if __name__ == "__main__":
    App().mainloop()
