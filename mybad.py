import os
import sys
import re
import io
import csv
import json
import sqlite3
import hashlib
import shutil
import argparse
import subprocess
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"

if os.name == "nt":
    os.system("")
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_dotenv():
    for p in (ENV_FILE, Path.cwd() / ".env"):
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass


load_dotenv()

KEY = os.environ.get("GROQ_API_KEY", "").strip()
ES = os.environ.get("ES_PATH", "es.exe")
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
DB = str(HERE / "mybad2.db")
MAX_READ = 150000


def default_root():
    if os.environ.get("MYBAD_ROOT"):
        return os.environ["MYBAD_ROOT"]
    if sys.platform == "win32":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return str(Path.home())


ROOT = default_root()

DEFAULT_EXTS = (
    "py", "pyw", "ipynb", "pyx",
    "ino", "pde", "vhd", "vhdl", "sv",
    "c", "cpp", "cc", "cxx", "h", "hpp", "hh", "hxx", "asm",
    "html", "htm", "css", "scss", "sass", "less",
    "js", "mjs", "cjs", "jsx", "ts", "mts", "cts", "tsx",
    "vue", "svelte", "astro", "php", "ejs",
    "java", "kt", "kts", "scala", "groovy", "gradle",
    "cs", "vb", "vbs", "xaml",
    "go", "rs", "swift", "dart", "zig", "nim",
    "rb", "lua", "jl", "ex", "exs", "hs", "clj", "lisp", "ml",
    "sh", "bash", "bat", "cmd", "ps1", "ahk", "au3", "cmake",
    "sql", "prisma", "graphql", "proto",
    "gd", "glsl", "hlsl", "shader",
)

EXTS = tuple(
    x.strip().lower().lstrip(".")
    for x in os.environ.get("MYBAD_EXTS", ",".join(DEFAULT_EXTS)).split(",")
    if x.strip()
)
EXT_SET = set(EXTS)

EX_ANY = {
    "venv", ".venv", "node_modules", "bower_components",
    "site-packages", "dist-packages", "__pycache__", "$recycle.bin", "appdata",
    ".git", ".svn", ".hg", ".vs", ".idea", ".vscode", ".pio", ".gradle",
    ".next", ".nuxt", ".svelte-kit", "cmake-build-debug", "cmake-build-release",
}

ROOT_EX = {
    "windows", "wındows", "program files", "program files (x86)",
    "program dosyaları (x86)", "program dosyalari (x86)", "programdata",
    "riot games", "xboxgames", "$sysreset", "onedrivetemp", "perflogs",
    "inetpub", "adobetemp", "platform-tools",
}
if sys.platform != "win32":
    ROOT_EX |= {"usr", "bin", "sbin", "lib", "proc", "sys", "dev", "etc", "var", "snap"}

SUB_EX = ["\\pinokio\\bin\\", "\\pinokio\\cache\\", "/pinokio/bin/", "/pinokio/cache/"]
MK = ("pyvenv.cfg", "conda-meta", "python.exe")
VAR = re.compile(r"[\s_\-#\(\)]*[a-z0-9ğüşıöç]{1,3}\)?|[\s_\-]*(?:copy|kopya)[\s\d\(\)]*", re.I)

SYS = """Kullanicinin anlattigi kayip dosyayi bulmak icin JSON filtre uret. Sadece JSON dondur. Bugun: {today}.
Her anahtar {"value": ..., "trust": 1-10} bicimindedir. Trust: kesinlikle/eminim 9-10, galiba/sanirim 4-6, tam bilmiyorum/belki 1-3.
Kullanicinin soylemedigi ama mantikli cikarimlari dusuk trust ile ekle.
Anahtarlar: modified_before_days(int, X gunden uzun suredir dokunulmadi), modified_within_days(int),
ext_any(list, noktasiz uzantilar: orn ["ino", "cpp", "c", "h"] veya ["html", "css", "js"] veya ["py"]),
name_any(list), name_regex(str), content_any(list), content_all(list), content_none(list), sibling_ext_any(list), sibling_name_any(list),
path_any(list, klasor veya yol parcasi: orn ["stemdefterim", "proje", "desktop\\odev"] — kullanici bir klasor adi soylerse mutlaka kullan),
outside_git(bool), git_dirty(bool), writes_ext(list), has_main(bool), size_min_kb(int), size_max_kb(int), path_exclude(list).
Kullanici "X klasoru icinde", "Y klasorunde", "Z yolunda" derse path_any ile o klasor/yol parcasini yukle; name_any sadece dosya adina bakar, klasore bakmaz.
Dil, kutuphane veya arac anlatiminda ext_any ve content_any icin dile uygun alternatif ifadeleri tahmin et (ornek Python indirme: import requests, urllib, httpx, yt_dlp; Arduino/ESP: #include <WiFi.h>, Serial.begin, void setup, digitalWrite; C/C++: #include <iostream>, #include <stdio.h>, int main, std::; Web/HTML/JS: <html, <div, <script, fetch, document.getElementById, addEventListener).
Kullanici celiskili bilgi verirse kisa bir uyariyi "warning" anahtarina yaz.
Kullanici duzeltme yazarsa onceki filtreyi ona gore guncelle ve tam JSON dondur."""

JUNK = re.compile(r"^(?:deneme|denem|dnm|test|yeni|new|untitled|asd|qwe|temp|tmp|kopya|copy|sketch).*$|^[a-z]{1,3}[\d\W_]*$|^[\d\W_]+$|^(\w)\1+[\d\W_]*$", re.I)

MAIN_RE = re.compile(
    r"(__main__|\b(?:int|void|func|fn)\s+main\s*\(|public\s+static\s+void\s+main\b|\bvoid\s+setup\s*\(|<!doctype\s+html|<html\b)",
    re.I,
)

DEP_PATTERNS = [
    re.compile(r"^\s*(?:import|from)\s+([\w\.]+)", re.M),
    re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M),
    re.compile(r"\brequire\s*\(\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]\s*\)", re.M),
    re.compile(r"\bimport\s+(?:.*\s+from\s+)?[\x27\x22]([^\x27\x22]+)[\x27\x22]", re.M),
    re.compile(r"^\s*using\s+([\w\.]+)\s*;", re.M),
    re.compile(r"<script[^>]+src=[\x27\x22]([^\x27\x22]+)[\x27\x22]", re.I),
    re.compile(r"<link[^>]+href=[\x27\x22]([^\x27\x22]+)[\x27\x22]", re.I),
]


def color(text, code):
    if sys.stdout.isatty():
        return "\033[" + code + "m" + str(text) + "\033[0m"
    return str(text)


def c_cyan(t): return color(t, "36")
def c_green(t): return color(t, "32")
def c_yellow(t): return color(t, "33")
def c_red(t): return color(t, "31")
def c_bold(t): return color(t, "1")
def c_dim(t): return color(t, "2")


def protect_env():
    root = next((d for d in [HERE, *HERE.parents] if (d / ".git").exists()), None)
    if not root:
        return
    gi = root / ".gitignore"
    try:
        cur = gi.read_text(encoding="utf-8", errors="ignore").splitlines() if gi.is_file() else []
        add = [x for x in (".env", "mybad2.db") if x not in [l.strip() for l in cur]]
        if add:
            gi.write_text("\n".join(cur + add) + "\n", encoding="utf-8")
    except Exception:
        pass


def save_key(key):
    lines = []
    if ENV_FILE.is_file():
        lines = [
            l for l in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not l.strip().startswith("GROQ_API_KEY")
        ]
    lines.append("GROQ_API_KEY=" + key)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    protect_env()


def ask_key():
    global KEY
    print(c_yellow("\n[Kurulum] Groq API anahtari bulunamadi."))
    val = input("Groq API anahtarinizi giriniz (bos=AI'siz devam): ").strip().strip("'\"")
    if not val:
        return False
    KEY = val
    os.environ["GROQ_API_KEY"] = val
    try:
        save_key(val)
        print(c_green(".env olusturuldu: " + str(ENV_FILE)))
    except Exception as e:
        print(c_red(".env yazilamadi: " + str(e)))
    return True


def parse_json(c):
    c = c.strip()
    c = re.sub(r"^```(?:json)?\s*|\s*```$", "", c)
    try:
        return json.loads(c)
    except Exception:
        a, b = c.find("{"), c.rfind("}")
        if a >= 0 and b > a:
            return json.loads(c[a:b + 1])
        raise


def chat(msgs, js=False, _retry=True):
    if not KEY and not ask_key():
        raise RuntimeError("API anahtari yok")
    p = {"model": MODEL, "temperature": 0, "messages": msgs}
    if js:
        p["response_format"] = {"type": "json_object"}
    r = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        json.dumps(p).encode(),
        {"Content-Type": "application/json", "Authorization": "Bearer " + KEY, "User-Agent": "Mozilla/5.0"},
    )
    try:
        raw = urllib.request.urlopen(r, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry:
            print(c_red("[HATA] API anahtari gecersiz."))
            if ask_key():
                return chat(msgs, js, False)
        raise RuntimeError("API hatasi " + str(e.code) + ": " + e.read().decode("utf-8", "ignore")[:300])
    c = json.loads(raw)["choices"][0]["message"]["content"]
    return parse_json(c) if js else c


def conn():
    c = sqlite3.connect(DB)
    cols = [r[1] for r in c.execute("pragma table_info(files)")]
    if cols and "is_bin" not in cols:
        c.execute("drop table files")
    c.execute("create table if not exists files(p text primary key, size int, m text, t text, h text, is_bin int default 0)")
    c.execute("create table if not exists fb(k text primary key, good int default 0, bad int default 0)")
    try:
        c.execute("drop table if exists files_fts")
    except Exception:
        pass
    c.commit()
    return c


def low(v):
    return [str(x).lower() for x in v]


def norm_exts(v):
    if isinstance(v, str):
        v = [v]
    return [str(x).lower().strip().lstrip(".") for x in v if str(x).strip()]


TEXT_CHARS = bytes({7, 8, 9, 10, 12, 13, 27} | (set(range(0x20, 0x100)) - {0x7F}))


def looks_binary(chunk):
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    return len(chunk.translate(None, TEXT_CHARS)) / len(chunk) > 0.30


def fsize(p):
    try:
        return os.path.getsize(p)
    except Exception:
        return 0


def has_es():
    if sys.platform != "win32":
        return False
    return bool(shutil.which(ES)) or Path(ES).is_file()


def load_es(root_path):
    ext_query = "ext:" + ";".join(EXTS)
    cmd = [ES, "-n", "2000000", "-csv", "-utf8-bom", "-size", "-dm", "-date-format", "1", "-full-path-and-name", "-path", str(root_path), ext_query]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError("es.exe sonuc vermedi (Everything acik mi?)")
    out = r.stdout
    try:
        out = out.decode("utf-8-sig")
    except UnicodeDecodeError:
        out = out.decode("oem", errors="replace")
    files = []
    for row in csv.DictReader(io.StringIO(out)):
        try:
            files.append({
                "p": Path(row["Filename"]),
                "size": int(re.sub(r"\D", "", row.get("Size", "")) or 0),
                "m": datetime.fromisoformat(row["Date Modified"].strip()[:19]),
            })
        except Exception:
            pass
    return files


EXTRA = []
LC = {}


def load_extra():
    try:
        t = (HERE / "mybad_exclude.txt").read_text(encoding="utf-8")
        return [x.strip().lower() for x in t.splitlines() if x.strip()]
    except Exception:
        return []


EXTRA = load_extra()


def lib_dir(d):
    if d not in LC:
        LC[d] = any((d / m).exists() for m in MK)
    return LC[d]


def excluded(p):
    ps = [x.lower() for x in p.parts]
    if any(x.startswith(".") for x in ps[1:]):
        return True
    if any(x in EX_ANY for x in ps):
        return True
    if len(ps) > 1 and ps[1] in ROOT_EX:
        return True
    s = str(p).lower()
    if any(x in s for x in SUB_EX + EXTRA):
        return True
    return any(lib_dir(d) for d in p.parents)


def walk_python(root_path):
    files = []
    root = Path(root_path).resolve()
    stack = [root]
    n = 0
    while stack:
        cur = stack.pop()
        if lib_dir(cur):
            continue
        try:
            with os.scandir(cur) as it:
                for e in it:
                    nm = e.name.lower()
                    if nm.startswith("."):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if nm in EX_ANY:
                            continue
                        if cur == root and nm in ROOT_EX:
                            continue
                        stack.append(Path(e.path))
                    elif e.is_file(follow_symlinks=False):
                        if Path(nm).suffix.lstrip(".") in EXT_SET:
                            try:
                                st = e.stat()
                                files.append({"p": Path(e.path), "size": st.st_size, "m": datetime.fromtimestamp(st.st_mtime)})
                                n += 1
                                if n % 5000 == 0:
                                    print(n, "dosya bulundu...")
                            except Exception:
                                pass
        except OSError:
            continue
    return files


def load_files(force_no_es, root_path):
    if not force_no_es and has_es():
        try:
            print(c_cyan("[Bilgi] Everything (es.exe) ile taraniyor..."))
            return load_es(root_path)
        except Exception as e:
            print(c_yellow("[Uyari] " + str(e) + " | Python tarayicisina geciliyor..."))
    print(c_cyan("[Bilgi] Python tarayicisi ile taraniyor (buyuk disklerde uzun surebilir)..."))
    return walk_python(root_path)


def process(f):
    p = f["p"]
    try:
        with open(p, "rb") as fh:
            data = fh.read(MAX_READ)
        binary = 1 if looks_binary(data[:1024]) else 0
    except Exception:
        data, binary = b"", 1
    t = "" if binary else data.decode("utf-8", errors="ignore").lower()
    h = hashlib.sha1((t if t else str(p)).encode("utf-8", "ignore")).hexdigest()
    return (str(p), f["size"] or fsize(p), f["m"].isoformat(), t, h, binary)


def scan(c, force_no_es=False, root_path=None):
    root_path = root_path or ROOT
    cur = {}
    for f in load_files(force_no_es, root_path):
        if not excluded(f["p"]):
            cur[str(f["p"])] = f
    old = {p: m for p, m in c.execute("select p, m from files")}
    new = [f for p, f in cur.items() if old.get(p) != f["m"].isoformat()]
    print(c_cyan("[Tarama] Toplam: " + str(len(cur)) + " | Okunacak yeni/degisen: " + str(len(new))))
    if new:
        bs = 500
        with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 2)) as ex:
            for i in range(0, len(new), bs):
                res = list(ex.map(process, new[i:i + bs]))
                c.executemany("insert or replace into files values(?,?,?,?,?,?)", res)
                c.commit()
                print("Isleme:", min(i + bs, len(new)), "/", len(new))
    rp = os.path.normcase(str(Path(root_path).resolve())).rstrip("\\/") + os.sep
    gone = [(p,) for p in old if p not in cur and os.path.normcase(p).startswith(rp)]
    if gone:
        c.executemany("delete from files where p=?", gone)
        c.commit()


def rows(c):
    return [
        {"p": Path(p), "size": s, "m": datetime.fromisoformat(m), "t": t, "h": h, "is_bin": b}
        for p, s, m, t, h, b in c.execute("select p, size, m, t, h, is_bin from files")
    ]


SC = {}
GC = {}
GS = {}


def sib(p):
    d = p.parent
    if d not in SC:
        try:
            SC[d] = list(d.iterdir())
        except Exception:
            SC[d] = []
    return [x for x in SC[d] if x != p]


def in_git(p):
    d = p.parent
    if d not in GC:
        GC[d] = any((x / ".git").exists() for x in [d, *d.parents])
    return GC[d]


def git_dirty(p):
    if not in_git(p):
        return False
    d = p.parent
    if d not in GS:
        try:
            out = subprocess.run(["git", "-C", str(d), "status", "--porcelain", "--", "."], capture_output=True, timeout=3).stdout.decode("utf-8", "ignore")
            names = set()
            for line in out.splitlines():
                item = line[3:].strip().strip('"').split(" -> ")[-1]
                names.add(os.path.basename(item.replace("/", os.sep)))
            GS[d] = names
        except Exception:
            GS[d] = set()
    return p.name in GS[d]


CH = {
    "modified_before_days": lambda f, v: (datetime.now() - f["m"]).days >= v,
    "modified_within_days": lambda f, v: (datetime.now() - f["m"]).days <= v,
    "ext_any": lambda f, v: f["p"].suffix.lower().lstrip(".") in norm_exts(v),
    "ext": lambda f, v: f["p"].suffix.lower().lstrip(".") in norm_exts(v),
    "path_exclude": lambda f, v: not any(x in str(f["p"]).lower() for x in low(v)),
    "path_any": lambda f, v: any(x in str(f["p"]).lower() for x in low(v)),
    "name_any": lambda f, v: any(x in f["p"].name.lower() for x in low(v)),
    "name_regex": lambda f, v: bool(re.search(v, f["p"].name, re.I)),
    "content_any": lambda f, v: any(x in f["t"] for x in low(v)),
    "content_all": lambda f, v: all(x in f["t"] for x in low(v)),
    "content_none": lambda f, v: not any(x in f["t"] for x in low(v)),
    "sibling_ext_any": lambda f, v: any(x.suffix.lower().lstrip(".") in norm_exts(v) for x in sib(f["p"])),
    "sibling_name_any": lambda f, v: any(s in x.name.lower() for x in sib(f["p"]) for s in low(v)),
    "outside_git": lambda f, v: (not in_git(f["p"])) == bool(v),
    "git_dirty": lambda f, v: git_dirty(f["p"]) == bool(v),
    "writes_ext": lambda f, v: any(x in f["t"] for x in low(v)),
    "has_main": lambda f, v: bool(MAIN_RE.search(f["t"])) == bool(v),
    "size_min_kb": lambda f, v: f["size"] >= v * 1024,
    "size_max_kb": lambda f, v: f["size"] <= v * 1024,
}


def weights(c):
    return {k: 2 * (g + 1) / (g + b + 2) for k, g, b in c.execute("select k, good, bad from fb")}


def feedback(c, hit, good):
    col = "good" if good else "bad"
    for k in hit:
        c.execute("insert or ignore into fb(k, good, bad) values(?,0,0)", (k,))
        c.execute("update fb set " + col + "=" + col + "+1 where k=?", (k,))
    c.commit()


def run(files, flt, W):
    keys = [k for k in flt if k in CH and isinstance(flt[k], dict) and "value" in flt[k]]

    def o(k):
        try:
            return float(flt[k].get("trust", 5))
        except Exception:
            return 5.0

    def e(k):
        return min(10.0, max(1.0, o(k) * W.get(k, 1)))

    cache = {}

    def m(f, k):
        i = (id(f), k)
        if i not in cache:
            try:
                cache[i] = bool(CH[k](f, flt[k]["value"]))
            except Exception:
                cache[i] = False
        return cache[i]

    active = sorted(keys, key=e)
    while True:
        total = sum(e(k) for k in active)
        res = []
        for f in files:
            s = 0
            ok = True
            hit = []
            for k in reversed(active):
                if m(f, k):
                    s += e(k)
                    hit.append(k)
                elif o(k) >= 9:
                    ok = False
                    break
            if ok and s >= 0.6 * total:
                res.append((s, f, hit))
        if res or len(active) <= 1:
            return res, active
        active.pop(0)


def extract_deps(t):
    deps = set()
    for pat in DEP_PATTERNS:
        deps.update(pat.findall(t))
    return sorted(deps)


def read_text(f):
    if f.get("is_bin"):
        return None
    try:
        return f["p"].read_text(errors="ignore")
    except Exception:
        return None


def preview(f):
    t = read_text(f)
    if t is None:
        print(c_yellow("[Onizleme yok: ikili veya okunamayan dosya]"))
        return
    print(c_cyan("Bagimliliklar:"), ", ".join(extract_deps(t)[:20]) or "-")
    print(c_dim("-" * 60))
    print("\n".join(t.splitlines()[:25]))
    print(c_dim("-" * 60))


def explain(f):
    t = read_text(f)
    if t is None:
        print(c_yellow("[Aciklanamaz: ikili veya okunamayan dosya]"))
        return
    ext = f["p"].suffix or "kod"
    try:
        print(c_cyan("\nAI Aciklamasi:"))
        print(chat([
            {"role": "system", "content": "Verilen " + ext + " dosyasinin (" + f["p"].name + ") ne yaptigini Turkce, en fazla 4 cumleyle acikla."},
            {"role": "user", "content": t[:8000]},
        ]))
    except Exception as e:
        print(c_red("[HATA] " + str(e)))


def mt(x):
    try:
        return x.stat().st_mtime
    except Exception:
        return 0


def open_folder(p):
    s = str(p.resolve())
    if sys.platform == "win32":
        subprocess.run(["explorer", "/select," + s])
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", s])
    else:
        subprocess.run(["xdg-open", str(p.parent)])


def pick(c, item):
    s, f, hit = item
    print(c_bold("\nSecilen: " + str(f["p"])))
    sb = sorted([x for x in sib(f["p"]) if x.is_file()], key=mt, reverse=True)[:15]
    if sb:
        print(c_yellow("Kardes dosyalar:"))
        for x in sb:
            print("  ", datetime.fromtimestamp(mt(x)).strftime("%Y-%m-%d"), x.name)
    while True:
        x = input(c_green("1") + " Onizle  " + c_green("2") + " Klasoru ac  " + c_green("3") + " AI'ya sor  " + c_green("4") + " Dogru  " + c_green("5") + " Yanlis  (bos=geri): ").strip()
        if x == "1":
            preview(f)
        elif x == "2":
            open_folder(f["p"])
        elif x == "3":
            explain(f)
        elif x == "4":
            feedback(c, hit, True)
            print(c_green("Kaydedildi (+)"))
            break
        elif x == "5":
            feedback(c, hit, False)
            print(c_red("Kaydedildi (-)"))
            break
        else:
            break


def search_query(c, files, initial_query=None):
    W = weights(c)
    msgs = [
        {"role": "system", "content": SYS.replace("{today}", datetime.now().strftime("%Y-%m-%d"))},
        {"role": "user", "content": initial_query or input("Dosyayi anlat: ")},
    ]
    while True:
        try:
            flt = chat(msgs, True)
        except Exception as e:
            print(c_red("[HATA] " + str(e)))
            return
        if not isinstance(flt, dict):
            flt = {}
        msgs.append({"role": "assistant", "content": json.dumps(flt, ensure_ascii=False)})
        if flt.get("warning"):
            print(c_yellow("Uyari: " + str(flt["warning"])))
        ex = flt["path_exclude"].get("value") if isinstance(flt.get("path_exclude"), dict) else None
        pool = [f for f in files if CH["path_exclude"](f, ex)] if isinstance(ex, list) and ex else files
        flt2 = {k: v for k, v in flt.items() if k not in ("path_exclude", "warning")}
        res, act = run(pool, flt2, W)
        res.sort(key=lambda x: (-x[0], -x[1]["m"].timestamp()))
        top = res[:20]
        print(c_cyan("Aktif filtreler:"), ", ".join(act) or "-")
        for i, (s, f, h) in enumerate(top, 1):
            tag = " " + c_yellow("[git-dirty]") if git_dirty(f["p"]) else ""
            print(c_bold(str(i)), str(round(s)) + "p", f["m"].strftime("%Y-%m-%d"), str(f["p"]) + tag)
        while True:
            x = input("\nNo sec / duzeltme yaz / bos=cik: ").strip()
            if not x:
                return
            if x.isdigit():
                if 1 <= int(x) <= len(top):
                    pick(c, top[int(x) - 1])
                continue
            msgs.append({"role": "user", "content": "Duzeltme: " + x + ". Onceki filtreyi buna gore guncelle ve tam JSON dondur."})
            break


def report(files):
    n = len(files)
    stems = [f["p"].stem.lower() for f in files if not (f["p"].stem.startswith("__") and f["p"].stem.endswith("__"))]
    junk = [s for s in stems if JUNK.match(s)]
    now = datetime.now()
    print(c_bold("\n=== GENEL RAPOR ==="))
    print("Toplam dosya:", n)
    ec = Counter(f["p"].suffix.lower() for f in files)
    if ec:
        print("En cok uzantilar:", ", ".join(k + ": " + str(v) for k, v in ec.most_common(12)))
    print("Anlamsiz isimli:", len(junk), "(%" + str(round(100 * len(junk) / max(n, 1))) + ")")
    print("\nEn cok tekrar eden isimler:")
    for s, k in Counter(f["p"].name.lower() for f in files if not (f["p"].stem.startswith("__") and f["p"].stem.endswith("__"))).most_common(10):
        print("  ", k, "x", s)
    groups = {}
    for f in files:
        if f["size"] > 0:
            groups.setdefault(f["h"], []).append(f["p"])
    dup = [g for g in groups.values() if len(g) > 1]
    print("\nAyni icerikli kopya grubu:", len(dup), "| fazla kopya:", sum(len(g) - 1 for g in dup))
    for g in sorted(dup, key=len, reverse=True)[:5]:
        print("  ", len(g), "kopya:", g[0])
    print("Git disinda basibos:", sum(1 for f in files if not in_git(f["p"])))
    print("90+ gundur dokunulmamis:", sum(1 for f in files if (now - f["m"]).days >= 90), "| 365+:", sum(1 for f in files if (now - f["m"]).days >= 365))
    print("Cok kucuk (<100 bayt):", sum(1 for f in files if f["size"] < 100))
    print("\nEn kalabalik klasorler:")
    for d, k in Counter(f["p"].parent for f in files).most_common(5):
        print("  ", k, d)


def show(t, lst):
    print("\n" + c_bold(t) + ":", len(lst))
    if not lst:
        return
    now = datetime.now()
    print("  klasor sayisi:", len({f["p"].parent for f in lst}))
    print("  90+ gundur dokunulmamis:", sum(1 for f in lst if (now - f["m"]).days >= 90), "| 365+:", sum(1 for f in lst if (now - f["m"]).days >= 365))
    print("  en eski:", min(f["m"] for f in lst).strftime("%Y-%m-%d"), "| en yeni:", max(f["m"] for f in lst).strftime("%Y-%m-%d"))
    print("  git disinda:", sum(1 for f in lst if not in_git(f["p"])))
    print("  cok kucuk (<100 bayt):", sum(1 for f in lst if f["size"] < 100))
    g = Counter(f["h"] for f in lst)
    print("  ayni icerikli fazla kopya:", sum(v - 1 for v in g.values() if v > 1))
    for f in sorted(lst, key=lambda f: f["m"])[:10]:
        print("   ", f["m"].strftime("%Y-%m-%d"), f["p"])


def name_report(files, query_name=None):
    q = (query_name or input("Isim (ornek deneme, blink.ino, index.html): ")).strip().lower()
    if not q:
        return
    suf = Path(q).suffix.lower().lstrip(".")
    has_ext = bool(suf and suf in EXT_SET)
    s = Path(q).stem.lower() if has_ext else q
    if not s:
        return
    ex, va, ot = [], [], []
    for f in files:
        if has_ext and f["p"].suffix.lower().lstrip(".") != suf:
            continue
        st = f["p"].stem.lower()
        if st == s:
            ex.append(f)
        elif st.startswith(s):
            if VAR.fullmatch(st[len(s):]):
                va.append(f)
            else:
                ot.append(f)
    label = s + "." + suf if has_ext else s + ".*"
    show("Tam eslesme (" + label + ")", ex)
    if va:
        print("\nVaryant isimleri:", ", ".join(k + " x" + str(v) for k, v in Counter(f["p"].name.lower() for f in va).most_common(12)))
    show("Varyantlar (" + s + " + 1-3 harf/rakam)", va)
    print("\nDaha uzun benzer isimler:", len(ot))
    for k, v in Counter(f["p"].name.lower() for f in ot).most_common(8):
        print("  ", k, "x", v)


def main():
    ap = argparse.ArgumentParser(description="mybad - AI destekli kod/dosya bulma araci")
    ap.add_argument("--scan", action="store_true", help="Diski tara, veritabanini guncelle")
    ap.add_argument("--no-es", action="store_true", help="es.exe yerine Python tarayicisi")
    ap.add_argument("--root", type=str, default=ROOT, help="Taranacak ana dizin")
    ap.add_argument("-q", "--find", type=str, help="Dogrudan arama sorgusu")
    ap.add_argument("--report", action="store_true", help="Karisiklik raporu")
    ap.add_argument("--name", type=str, help="Isim varyant raporu")
    a = ap.parse_args()

    needs_ai = not (a.report or a.name or (a.scan and not a.find))
    if needs_ai and not KEY:
        ask_key()

    c = conn()
    if a.scan:
        scan(c, a.no_es, a.root)
        print(c_green("Tarama tamamlandi."))
        if not (a.find or a.report or a.name):
            return

    files = rows(c)
    if not files and not a.scan:
        print(c_yellow("Veritabani bos. Ilk tarama basliyor..."))
        scan(c, a.no_es, a.root)
        files = rows(c)
    if not files:
        print(c_red("Hic dosya bulunamadi. --root veya MYBAD_ROOT ile klasoru kontrol et."))
        return
    print(c_green(str(len(files)) + " dosya hazir (" + str(len(EXTS)) + " uzanti)"))

    if a.find:
        search_query(c, files, a.find)
        return
    if a.report:
        report(files)
        return
    if a.name:
        name_report(files, a.name)
        return

    while True:
        print("\n" + c_bold("=== MYBAD ==="))
        x = input(c_cyan("1") + " Dosya ara  " + c_cyan("2") + " Karisiklik raporu  " + c_cyan("3") + " Isim raporu  " + c_cyan("4") + " Yeniden tara  (bos=cikis): ").strip()
        if x == "1":
            search_query(c, files)
        elif x == "2":
            report(files)
        elif x == "3":
            name_report(files)
        elif x == "4":
            scan(c, a.no_es, a.root)
            files = rows(c)
            print(c_green(str(len(files)) + " dosya guncellendi."))
        else:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCikildi.")
