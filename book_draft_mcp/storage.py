"""JSON storage layer with path safety and auto-backup."""
import json
import os
import re
import shutil
from datetime import datetime

_filename_re = re.compile(r"^[A-Za-z0-9._-]+$")

DEFAULT_DATA_DIR = os.environ.get(
    "BOOK_DRAFT_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)
BOOK_FILENAME = "draft.json"

def check_leaf_name(name):
    """Validate a single path component. Raises ValueError on anything risky."""
    if not name or not isinstance(name, str):
        raise ValueError("Name must be a non-empty string.")
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe path component: %r" % name)
    if not _filename_re.match(name):
        raise ValueError("Unsafe path component: only letters, digits, '.', '_', '-' allowed.")
    return name


def safe_path(data_dir, filename=BOOK_FILENAME, makedirs=True):
    """Resolve data_dir + filename safely; refuse escapes outside data_dir."""
    check_leaf_name(filename)
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
    base = os.path.realpath(os.path.abspath(data_dir))
    full = os.path.realpath(os.path.join(base, filename))
    if not (full == base or full.startswith(base + os.sep)):
        raise ValueError("Unsafe path component: escapes data directory.")
    if makedirs:
        os.makedirs(base, exist_ok=True)
    return full


def load(data_dir=None, filename=BOOK_FILENAME):
    path = safe_path(data_dir, filename, makedirs=False)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data, data_dir=None, filename=BOOK_FILENAME):
    path = safe_path(data_dir, filename)
    _backup(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


def _backup(path):
    """Copy existing file to backups/bookname-YYYYmmdd-HHMMSS.json before overwriting."""
    if not os.path.exists(path):
        return
    backups_dir = os.path.join(os.path.dirname(path), "backups")
    os.makedirs(backups_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = os.path.splitext(os.path.basename(path))[0]
    dst = os.path.join(backups_dir, "%s-%s.json" % (stem, stamp))
    shutil.copy2(path, dst)
    _prune(backups_dir, keep=10)


def _prune(backups_dir, keep=10):
    files = sorted(
        f for f in os.listdir(backups_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(backups_dir, f))
    )
    for extra in files[:-keep] if len(files) > keep else []:
        try:
            os.remove(os.path.join(backups_dir, extra))
        except OSError:
            pass
