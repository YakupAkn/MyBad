import os
import sys
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

DEFAULT_BASE = os.environ.get(
    "MYBAD_RELEASE_BASE",
    "https://github.com/YakupAkn/MyBad/releases/latest/download",
).rstrip("/")

ASSETS = {
    "console": {
        "label": "Console surumu",
        "file": "MyBad-Console.exe",
        "desc": "Komut satiri arayuzu. Script ve otomasyon icin uygundur.",
    },
    "gui": {
        "label": "Arayuz surumu (GUI)",
        "file": "MyBad-GUI.exe",
        "desc": "Pencereli gorsel arayuz. Gunluk kullanim icin onerilir.",
    },
}

BG = "#0f1115"
CARD = "#171a21"
FG = "#e8eaed"
MUTED = "#9aa0a6"
ACCENT = "#4c8bf5"
ACCENT_HOVER = "#3b6fd4"
OK = "#34a853"
ERR = "#ea4335"
BORDER = "#2a2f3a"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MyBad - Indirme Yardimcisi")
        self.geometry("560x520")
        self.minsize(520, 480)
        self.configure(bg=BG)
        self.resizable(True, True)

        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self.choice = tk.StringVar(value="gui")
        self.dest = tk.StringVar(value=self._default_dest())
        self.status = tk.StringVar(value="Surumu secip Indir'e bas.")
        self.progress = tk.DoubleVar(value=0)
        self.busy = False

        self._style()
        self._build()
        self._center()

    def _default_dest(self):
        d = os.path.join(os.path.expanduser("~"), "Downloads")
        return d if os.path.isdir(d) else os.getcwd()

    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        s.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI Semibold", 16))
        s.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("Card.TLabel", background=CARD, foreground=FG, font=("Segoe UI", 10))
        s.configure("CardSub.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(16, 8))
        s.configure("TRadiobutton", background=CARD, foreground=FG, font=("Segoe UI", 10))
        s.map("TRadiobutton", background=[("active", CARD)], foreground=[("selected", ACCENT)])
        s.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=ACCENT, thickness=8)

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def _build(self):
        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="MyBad", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="Kayip dosya bulma araci — surum sec ve bilgisayarına indir.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 18))

        # Version cards
        ttk.Label(root, text="Surum", style="TLabel").pack(anchor="w", pady=(0, 8))
        cards = ttk.Frame(root)
        cards.pack(fill="x")

        for key in ("gui", "console"):
            self._card(cards, key)

        # Both option
        both = ttk.Frame(root, style="Card.TFrame", padding=12)
        both.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(
            both,
            text="Ikisini de indir (Console + GUI)",
            variable=self.choice,
            value="both",
            style="TRadiobutton",
        ).pack(anchor="w")

        # Destination
        ttk.Label(root, text="Kayit klasoru", style="TLabel").pack(anchor="w", pady=(18, 6))
        row = ttk.Frame(root)
        row.pack(fill="x")
        ent = ttk.Entry(row, textvariable=self.dest)
        ent.pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(row, text="Gozat...", command=self._browse).pack(side="left", padx=(8, 0))

        # Progress + status
        self.bar = ttk.Progressbar(root, variable=self.progress, maximum=100, mode="determinate")
        self.bar.pack(fill="x", pady=(20, 6))
        ttk.Label(root, textvariable=self.status, style="Status.TLabel").pack(anchor="w")

        # Actions
        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(18, 0))
        self.btn = tk.Button(
            actions,
            text="Indir",
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            cursor="hand2",
            padx=22,
            pady=8,
            command=self._start,
        )
        self.btn.pack(side="left")
        tk.Button(
            actions,
            text="Kapat",
            bg=CARD,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            font=("Segoe UI", 10),
            cursor="hand2",
            padx=16,
            pady=8,
            command=self.destroy,
        ).pack(side="right")

        ttk.Label(
            root,
            text="Kaynak: " + DEFAULT_BASE,
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(16, 0))

    def _card(self, parent, key):
        info = ASSETS[key]
        wrap = ttk.Frame(parent, style="Card.TFrame", padding=12)
        wrap.pack(fill="x", pady=(0, 8))
        ttk.Radiobutton(
            wrap,
            text=info["label"],
            variable=self.choice,
            value=key,
            style="TRadiobutton",
        ).pack(anchor="w")
        ttk.Label(wrap, text=info["desc"], style="CardSub.TLabel").pack(anchor="w", padx=(22, 0), pady=(2, 0))
        ttk.Label(wrap, text=info["file"], style="CardSub.TLabel").pack(anchor="w", padx=(22, 0))

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.dest.get() or self._default_dest())
        if d:
            self.dest.set(d)

    def _set_busy(self, on):
        self.busy = on
        self.btn.configure(state=("disabled" if on else "normal"), text=("Indiriliyor..." if on else "Indir"))

    def _start(self):
        if self.busy:
            return
        dest = self.dest.get().strip()
        if not dest or not os.path.isdir(dest):
            messagebox.showerror("MyBad", "Gecerli bir kayit klasoru sec.")
            return
        choice = self.choice.get()
        keys = ["gui", "console"] if choice == "both" else [choice]
        self._set_busy(True)
        self.progress.set(0)
        self.status.set("Indirme basliyor...")
        threading.Thread(target=self._worker, args=(keys, dest), daemon=True).start()

    def _worker(self, keys, dest):
        ok = 0
        n = len(keys)
        try:
            for i, key in enumerate(keys):
                info = ASSETS[key]
                name = info["file"]
                url = DEFAULT_BASE + "/" + name
                out = os.path.join(dest, name)
                self._ui(lambda m=f"Indiriliyor: {name}": self.status.set(m))
                if self._download(url, out, i, n):
                    ok += 1
                else:
                    self._ui(lambda m=f"Basarisiz: {name}": self.status.set(m))
        finally:
            def done():
                self._set_busy(False)
                if ok == n:
                    self.progress.set(100)
                    self.status.set("Tamam. " + str(ok) + " dosya indirildi.")
                    messagebox.showinfo("MyBad", "Indirme tamamlandi.\n\n" + dest)
                    try:
                        if os.name == "nt":
                            os.startfile(dest)
                    except Exception:
                        pass
                else:
                    self.status.set("Bazi dosyalar indirilemedi. Release URL'sini kontrol et.")
                    messagebox.showwarning(
                        "MyBad",
                        "Indirme tamamlanamadi.\n\n"
                        "Release adresini kontrol et veya MYBAD_RELEASE_BASE ortam degiskenini ayarla.\n"
                        + DEFAULT_BASE,
                    )

            self._ui(done)

    def _ui(self, fn):
        self.after(0, fn)

    def _download(self, url, out, index, total):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MyBad-Downloader/1.1"})
            with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
                total_bytes = r.headers.get("Content-Length")
                total_bytes = int(total_bytes) if total_bytes and total_bytes.isdigit() else None
                done = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total_bytes:
                        file_pct = done / total_bytes
                    else:
                        file_pct = 0.5
                    overall = ((index + file_pct) / total) * 100
                    self._ui(lambda v=overall: self.progress.set(v))
            return True
        except Exception:
            if os.path.isfile(out):
                try:
                    os.remove(out)
                except Exception:
                    pass
            return False


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
