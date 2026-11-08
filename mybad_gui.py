import os
import json
import queue
import threading
import contextlib
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from datetime import datetime

import mybad

Q = queue.Queue()


def post(fn):
    Q.put(fn)


def start_msgs(query):
    return [
        {"role": "system", "content": mybad.SYS.replace("{today}", datetime.now().strftime("%Y-%m-%d"))},
        {"role": "user", "content": query},
    ]


def correction_msg(text):
    return {
        "role": "user",
        "content": "Duzeltme: " + text + ". Onceki filtreyi buna gore guncelle ve tam JSON dondur.",
    }


def find(files, flt, W):
    if not isinstance(flt, dict):
        flt = {}
    ex = flt["path_exclude"].get("value") if isinstance(flt.get("path_exclude"), dict) else None
    if isinstance(ex, list) and ex:
        pool = [f for f in files if mybad.CH["path_exclude"](f, ex)]
    else:
        pool = files
    flt2 = {k: v for k, v in flt.items() if k not in ("path_exclude", "warning")}
    res, act = mybad.run(pool, flt2, W)
    res.sort(key=lambda x: (-x[0], -x[1]["m"].timestamp()))
    return res, act, pool, flt2


def why_lines(pool, flt2, W, name_fragment):
    name_fragment = (name_fragment or "").strip().lower()
    if not name_fragment:
        return ["Isim/parca bos."]
    matches = [f for f in pool if name_fragment in str(f["p"]).lower()]
    if not matches:
        return [
            "Havuzda bu isim/parca ile dosya yok: " + name_fragment,
            "Toplam havuz: " + str(len(pool)),
            "Not: path_exclude veya tarama kapsami disinda olabilir.",
        ]
    keys = [k for k in flt2 if k in mybad.CH and isinstance(flt2[k], dict) and "value" in flt2[k]]

    def o(k):
        try:
            return float(flt2[k].get("trust", 5))
        except Exception:
            return 5.0

    def e(k):
        return min(10.0, max(1.0, o(k) * W.get(k, 1)))

    lines = []
    total = sum(e(k) for k in keys) or 1.0
    threshold = 0.6 * total
    lines.append("Aranan: " + name_fragment)
    lines.append("Havuzda eslesen: " + str(len(matches)))
    lines.append("Esik (0.6 * toplam): " + str(round(threshold, 2)) + " | filtre sayisi: " + str(len(keys)))
    lines.append("")
    for f in sorted(matches, key=lambda x: str(x["p"]))[:12]:
        s = 0.0
        hit, miss_hard, miss_soft = [], [], []
        for k in keys:
            try:
                ok = bool(mybad.CH[k](f, flt2[k]["value"]))
            except Exception:
                ok = False
            wt = e(k)
            if ok:
                s += wt
                hit.append(k + "(" + str(round(wt, 1)) + ")")
            elif o(k) >= 9:
                miss_hard.append(k + "(trust=" + str(round(o(k), 1)) + ")")
            else:
                miss_soft.append(k + "(" + str(round(wt, 1)) + ")")
        status = "GECER" if (s >= threshold and not miss_hard) else "ELENDI"
        lines.append(status + "  " + str(round(s, 1)) + "p  " + str(f["p"]))
        if hit:
            lines.append("  + " + ", ".join(hit))
        if miss_hard:
            lines.append("  HARD miss: " + ", ".join(miss_hard))
        if miss_soft:
            lines.append("  soft miss: " + ", ".join(miss_soft))
        lines.append("")
    if len(matches) > 12:
        lines.append("... +" + str(len(matches) - 12) + " dosya daha")
    return lines


class Writer:
    def __init__(self, status=None):
        self.buf = []
        self.status = status

    def write(self, s):
        self.buf.append(s)
        line = s.strip()
        if line and self.status:
            post(lambda l=line: self.status(l))
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False

    def text(self):
        return "".join(self.buf)


class App:
    def __init__(self, root):
        self.root = root
        root.title("MyBad")
        root.geometry("1150x740")
        self.c = mybad.conn()
        self.files = []
        self.msgs = []
        self.pool = []
        self.flt2 = {}
        self.items = {}
        self.busy = False
        self.build()
        mybad.ask_key = self.ask_key
        root.after(50, self.poll)
        if not mybad.KEY:
            self.ask_key_dialog()
        self.load()

    def build(self):
        r = self.root
        top = ttk.Frame(r, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Dosyayi anlat:").pack(side="left")
        self.q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.q)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.bind("<Return>", lambda ev: self.search())
        e.focus_set()
        ttk.Button(top, text="Ara", command=self.search).pack(side="left")
        ttk.Button(top, text="Duzelt", command=self.fix).pack(side="left", padx=(4, 0))

        bar = ttk.Frame(r, padding=(6, 0, 6, 6))
        bar.pack(fill="x")
        for t, f in (("Yeniden tara", self.rescan), ("Karisiklik raporu", self.report), ("Isim raporu", self.name_report), ("Neden cikmadi?", self.why)):
            ttk.Button(bar, text=t, command=f).pack(side="left", padx=(0, 4))

        self.st = tk.StringVar(value="Hazirlaniyor...")
        ttk.Label(r, textvariable=self.st, anchor="w", padding=(6, 2)).pack(side="bottom", fill="x")

        act = ttk.Frame(r, padding=6)
        act.pack(side="bottom", fill="x")
        for t, f in (("Klasoru ac", self.open_dir), ("AI'ya sor", self.ask), ("Dogru", lambda: self.rate(True)), ("Yanlis", lambda: self.rate(False))):
            ttk.Button(act, text=t, command=f).pack(side="left", padx=(0, 4))

        pane = ttk.PanedWindow(r, orient="vertical")
        pane.pack(fill="both", expand=True, padx=6)
        tf = ttk.Frame(pane)
        cols = ("puan", "tarih", "git", "yol")
        self.tv = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse", height=12)
        for k, w in (("puan", 60), ("tarih", 90), ("git", 60), ("yol", 900)):
            self.tv.heading(k, text=k.capitalize())
            self.tv.column(k, width=w, anchor="w", stretch=(k == "yol"))
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<<TreeviewSelect>>", self.on_select)
        pane.add(tf, weight=2)

        xf = ttk.Frame(pane)
        self.tx = tk.Text(xf, wrap="none", font=("Consolas", 10))
        xs = ttk.Scrollbar(xf, orient="vertical", command=self.tx.yview)
        self.tx.configure(yscrollcommand=xs.set)
        self.tx.pack(side="left", fill="both", expand=True)
        xs.pack(side="right", fill="y")
        pane.add(xf, weight=3)

    def poll(self):
        while True:
            try:
                fn = Q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                self.status("Hata: " + str(e))
        self.root.after(50, self.poll)

    def status(self, s):
        self.st.set(str(s)[:220])

    def show(self, s):
        self.tx.delete("1.0", "end")
        self.tx.insert("1.0", s)

    def ask_key_dialog(self):
        v = simpledialog.askstring("Groq API anahtari", "Groq API anahtarinizi giriniz (.env dosyasina kaydedilir):", parent=self.root, show="*")
        v = (v or "").strip().strip("'\"")
        if not v:
            return False
        mybad.KEY = v
        os.environ["GROQ_API_KEY"] = v
        try:
            mybad.save_key(v)
            self.status(".env olusturuldu")
        except Exception as e:
            messagebox.showerror("MyBad", ".env yazilamadi: " + str(e))
        return True

    def ask_key(self):
        if threading.current_thread() is threading.main_thread():
            return self.ask_key_dialog()
        ev = threading.Event()
        box = []

        def go():
            box.append(self.ask_key_dialog())
            ev.set()

        post(go)
        ev.wait()
        return box[0]

    def run_bg(self, fn, done=None, label=""):
        if self.busy:
            self.status("Mesgul, bitmesini bekle...")
            return
        self.busy = True
        self.status(label)

        def work():
            try:
                r, err = fn(), None
            except Exception as e:
                r, err = None, e

            def fin():
                self.busy = False
                if err:
                    self.status("Hata: " + str(err))
                    self.show("Hata: " + str(err))
                elif done:
                    done(r)

            post(fin)

        threading.Thread(target=work, daemon=True).start()

    def scan_rows(self, force_scan):
        cw = mybad.conn()
        try:
            files = [] if force_scan else mybad.rows(cw)
            if not files:
                with contextlib.redirect_stdout(Writer(self.status)):
                    mybad.scan(cw)
                files = mybad.rows(cw)
            return files
        finally:
            cw.close()

    def set_files(self, files):
        self.files = files
        self.status(str(len(files)) + " dosya hazir")

    def load(self):
        self.run_bg(lambda: self.scan_rows(False), self.set_files, "Veritabani yukleniyor...")

    def rescan(self):
        self.run_bg(lambda: self.scan_rows(True), self.set_files, "Taraniyor...")

    def search(self):
        t = self.q.get().strip()
        if not t:
            return
        self.msgs = start_msgs(t)
        self.query()

    def fix(self):
        t = self.q.get().strip()
        if not t or not self.msgs:
            self.status("Once bir arama yap, sonra duzeltme yaz.")
            return
        self.msgs.append(correction_msg(t))
        self.query()

    def query(self):
        if not self.files:
            self.status("Dosyalar henuz yuklenmedi.")
            return
        W = mybad.weights(self.c)
        msgs = list(self.msgs)
        files = self.files

        def fn():
            flt = mybad.chat(msgs, True)
            if not isinstance(flt, dict):
                flt = {}
            res, act, pool, flt2 = find(files, flt, W)
            top = res[:20]
            dirty = [mybad.git_dirty(x[1]["p"]) for x in top]
            return flt, res, act, pool, flt2, dirty

        def done(r):
            flt, res, act, pool, flt2, dirty = r
            self.msgs.append({"role": "assistant", "content": json.dumps(flt, ensure_ascii=False)})
            self.pool, self.flt2 = pool, flt2
            self.tv.delete(*self.tv.get_children())
            self.items = {}
            for i, ((s, f, h), d) in enumerate(zip(res[:20], dirty), 1):
                iid = str(i)
                self.items[iid] = (s, f, h)
                self.tv.insert("", "end", iid=iid, values=(round(s), f["m"].strftime("%Y-%m-%d"), "dirty" if d else "", str(f["p"])))
            w = ("Uyari: " + str(flt["warning"]) + " | ") if flt.get("warning") else ""
            self.status(w + "Filtreler: " + (", ".join(act) or "-") + " | aday: " + str(len(res)))
            self.show("")

        self.run_bg(fn, done, "AI filtre uretiyor...")

    def sel(self):
        s = self.tv.selection()
        return self.items.get(s[0]) if s else None

    def on_select(self, ev=None):
        it = self.sel()
        if not it:
            return
        s, f, hit = it
        L = [str(f["p"]), "Eslesen filtreler: " + ", ".join(hit), ""]
        sb = sorted([x for x in mybad.sib(f["p"]) if x.is_file()], key=mybad.mt, reverse=True)[:15]
        if sb:
            L.append("Kardes dosyalar:")
            for x in sb:
                L.append("  " + datetime.fromtimestamp(mybad.mt(x)).strftime("%Y-%m-%d") + " " + x.name)
            L.append("")
        t = mybad.read_text(f)
        if t is None:
            L.append("[Onizleme yok: ikili veya okunamayan dosya]")
        else:
            L.append("Bagimliliklar: " + (", ".join(mybad.extract_deps(t)[:20]) or "-"))
            L.append("-" * 60)
            L.extend(t.splitlines()[:40])
        self.show("\n".join(L))

    def open_dir(self):
        it = self.sel()
        if it:
            mybad.open_folder(it[1]["p"])

    def rate(self, good):
        it = self.sel()
        if not it:
            return
        mybad.feedback(self.c, it[2], good)
        self.status("Geri bildirim kaydedildi " + ("(+)" if good else "(-)"))

    def ask(self):
        it = self.sel()
        if not it:
            return
        f = it[1]
        t = mybad.read_text(f)
        if t is None:
            self.show("[Aciklanamaz: ikili veya okunamayan dosya]")
            return
        ext = f["p"].suffix or "kod"
        msgs = [
            {"role": "system", "content": "Verilen " + ext + " dosyasinin (" + f["p"].name + ") ne yaptigini Turkce, en fazla 4 cumleyle acikla."},
            {"role": "user", "content": t[:8000]},
        ]
        self.run_bg(lambda: mybad.chat(msgs), lambda r: self.show(str(f["p"]) + "\n\nAI Aciklamasi:\n" + r), "AI okuyor...")

    def captured(self, fn, *a):
        w = Writer()
        with contextlib.redirect_stdout(w):
            fn(*a)
        return w.text()

    def report(self):
        if not self.files:
            return
        self.run_bg(lambda: self.captured(mybad.report, self.files), self.show, "Rapor hazirlaniyor...")

    def name_report(self):
        n = simpledialog.askstring("Isim raporu", "Isim (ornek: deneme, blink.ino, index.html):", parent=self.root)
        if not n or not self.files:
            return
        self.run_bg(lambda: self.captured(mybad.name_report, self.files, n), self.show, "Isim raporu hazirlaniyor...")

    def why(self):
        if not self.pool:
            self.status("Once bir arama yap.")
            return
        n = simpledialog.askstring("Neden cikmadi?", "Dosya adi veya yol parcasi (ornek: oyunalanim\\test.py):", parent=self.root)
        if not n:
            return
        W = mybad.weights(self.c)
        pool, flt2 = self.pool, self.flt2
        self.run_bg(lambda: "\n".join(why_lines(pool, flt2, W, n)), self.show, "Puanlar hesaplaniyor...")


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
