import os
import re
import json
import shutil
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from PIL import Image
from PIL.ImageQt import ImageQt

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget, QCheckBox,
    QDialog, QScrollArea
)

# ----------------------------
# CONFIG YOU CAN EDIT
# ----------------------------
CATEGORIES = [
    "AccA", "AccB", "Beard", "BeastEars", "Cloak", "Clothing", "Ears", "Eyebrows",
    "Eyes", "Face", "FacialMark", "FrontHair", "Glasses", "Mouth", "Nose",
    "RearHair", "Tail", "Wing"
]

# Categories that may have optional layer suffixes 1/2 (e.g., Clothing1, Clothing2)
LAYERED_CATEGORIES = {"Cloak", "Clothing", "RearHair", "Beard", "FrontHair", "Tail", "Wing"}


# Folder mapping (root subfolder -> component key)
COMPONENT_FOLDERS = {
    "Face": "FACE",
    "SV": "SV",
    "TV": "TV",
    "TVD": "TVD",
    "Variation": "ICON",
}

GENDERS = ["Female", "Male", "Kid"]
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Regex helpers
# FIX: allow '.' after p01 (file extension), and underscore/dash too
RE_PART = re.compile(r"(?:^|[_-])p(\d{1,3})(?=[_.-]|$)", re.IGNORECASE)


# ----------------------------
# DATA MODELS
# ----------------------------
@dataclass(frozen=True)
class PartKey:
    gender: str
    category: str
    part_num: str  # "01" etc.


@dataclass
class FileEntry:
    path: str
    filename: str


@dataclass
class PartGroup:
    key: PartKey
    # component -> list of candidates (main art)
    candidates: Dict[str, List[FileEntry]]
    # masks only for SV/TV/TVD: "SV"|"TV"|"TVD" -> list of mask candidates
    masks: Dict[str, List[FileEntry]]


# ----------------------------
# SCANNING + MATCHING
# ----------------------------
def detect_category(filename: str) -> Optional[str]:
    """
    Detect category token in filename.
    For certain categories, allow optional 1/2 suffixes (e.g., Clothing, Clothing1, Clothing2),
    but normalize to the base category (e.g., Clothing).
    """
    # First handle layered categories with optional suffix
    for base in LAYERED_CATEGORIES:
        # Match token boundaries: start or _/-, then base, optional 1/2, then boundary/end
        # Examples matched: Clothing, Clothing1, Clothing2 (case-insensitive)
        if re.search(rf"(?:^|[_-]){re.escape(base)}(?:[12])?(?:[_-]|$)", filename, re.IGNORECASE):
            return base

    # Then handle everything else exactly (no numeric suffix allowed)
    for cat in CATEGORIES:
        if cat in LAYERED_CATEGORIES:
            continue
        if re.search(rf"(?:^|[_-]){re.escape(cat)}(?:[_-]|$)", filename, re.IGNORECASE):
            return cat

    return None


def detect_part_num(filename: str) -> Optional[str]:
    m = RE_PART.search(filename)
    if not m:
        return None
    num = int(m.group(1))
    return f"{num:02d}"


def is_mask_file(filename: str) -> bool:
    """
    Treat *_c.png, *_c1.png, etc. as mask sheets.
    Example: SV_AccA_p01_c.png or TV_AccA_p01_c1.png
    """
    stem = os.path.splitext(filename)[0].lower()
    if stem.endswith("_c") or stem.endswith("-c"):
        return True
    # ends with _c1, -c2, etc.
    if re.search(r"(?:[_-])c\d*$", stem):
        return True
    return False


def scan_generator(root: str) -> Dict[PartKey, PartGroup]:
    groups: Dict[PartKey, PartGroup] = {}

    for root_folder, comp_key in COMPONENT_FOLDERS.items():
        base = os.path.join(root, root_folder)
        if not os.path.isdir(base):
            continue

        for gender in GENDERS:
            gdir = os.path.join(base, gender)
            if not os.path.isdir(gdir):
                continue

            for fname in os.listdir(gdir):
                if not fname.lower().endswith(IMAGE_EXTS):
                    continue

                cat = detect_category(fname)
                part_num = detect_part_num(fname)
                if not cat or not part_num:
                    continue

                key = PartKey(gender=gender, category=cat, part_num=part_num)
                if key not in groups:
                    groups[key] = PartGroup(
                        key=key,
                        candidates={k: [] for k in COMPONENT_FOLDERS.values()},
                        masks={"SV": [], "TV": [], "TVD": []},
                    )

                full_path = os.path.join(gdir, fname)
                entry = FileEntry(path=full_path, filename=fname)

                # Route masks for SV/TV/TVD into separate list; keep ICON/FACE always as candidates
                if comp_key in ("SV", "TV", "TVD") and is_mask_file(fname):
                    groups[key].masks[comp_key].append(entry)
                else:
                    groups[key].candidates[comp_key].append(entry)

    # Remove empty groups (defensive)
    groups = {
        k: v for k, v in groups.items()
        if any(v.candidates[c] for c in v.candidates) or any(v.masks[m] for m in v.masks)
    }
    return groups


# ----------------------------
# IMAGE PREVIEW UTIL
# ----------------------------
def load_preview_pixmap(path: str, max_size: QSize) -> QPixmap:
    try:
        img = Image.open(path).convert("RGBA")
        img.thumbnail((max_size.width(), max_size.height()), Image.Resampling.LANCZOS)
        qim = ImageQt(img)
        return QPixmap.fromImage(qim)
    except Exception:
        return QPixmap()


# ----------------------------
# BIG VIEWER DIALOG
# ----------------------------
class ImageViewerDialog(QDialog):
    def __init__(self, path: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(980, 760)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.label)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

        pix = QPixmap(path)
        if pix.isNull():
            self.label.setText("Failed to load image.")
        else:
            self.label.setPixmap(pix)
            self.label.adjustSize()


# ----------------------------
# UI
# ----------------------------
class PreviewPanel(QWidget):
    def __init__(self, title: str):
        super().__init__()
        self.title = title

        self.title_label = QLabel(f"<b>{title}</b>")
        self.combo = QComboBox()
        self.combo.setMinimumWidth(260)

        self.image = QLabel()
        self.image.setFixedSize(260, 260)
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setCursor(Qt.PointingHandCursor)
        self.image.mousePressEvent = self._open_viewer  # type: ignore

        self.status = QLabel("")
        self.status.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(self.title_label)
        layout.addWidget(self.combo)
        layout.addWidget(self.image)
        layout.addWidget(self.status)
        self.setLayout(layout)

        self.combo.currentIndexChanged.connect(self._on_choice_changed)
        self._paths: List[str] = []

    def set_candidates(self, entries: List[FileEntry]):
        self.combo.blockSignals(True)
        self.combo.clear()
        self._paths = []

        if not entries:
            self.combo.addItem("(missing)")
            self._paths = [""]
            self.status.setText("❌ Missing")
        else:
            for e in entries:
                self.combo.addItem(e.filename)
                self._paths.append(e.path)
            self.status.setText(f"✅ {len(entries)} option(s)")

        self.combo.blockSignals(False)
        self.combo.setCurrentIndex(0)
        self._render_current()

    def selected_path(self) -> str:
        idx = self.combo.currentIndex()
        if idx < 0 or idx >= len(self._paths):
            return ""
        return self._paths[idx]

    def _on_choice_changed(self):
        self._render_current()

    def _render_current(self):
        path = self.selected_path()
        if not path:
            self.image.setPixmap(QPixmap())
            self.image.setText("Missing")
            return
        pix = load_preview_pixmap(path, self.image.size())
        if pix.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText("Failed to load")
        else:
            self.image.setPixmap(pix)
            self.image.setText("")

    def _open_viewer(self, event):
        path = self.selected_path()
        if not path:
            return
        dlg = ImageViewerDialog(path, f"{self.title} — {os.path.basename(path)}", self)
        dlg.exec()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RPG Maker MZ Generator Part Sorter")
        self.resize(1200, 800)

        self.root_path: Optional[str] = None
        self.groups: Dict[PartKey, PartGroup] = {}
        self.keys: List[PartKey] = []
        self.all_keys: List[PartKey] = []
        self.index: int = 0
        self.reviewed_ok: set[PartKey] = set()

        # Top controls
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("Select generator root folder…")
        self.browse_btn = QPushButton("Browse…")
        self.reload_btn = QPushButton("Scan")
        self.only_missing_chk = QCheckBox("Only show missing main components")
        self.only_missing_chk.setChecked(False)

        topbar = QHBoxLayout()
        topbar.addWidget(QLabel("Generator Root:"))
        topbar.addWidget(self.root_edit, 1)
        topbar.addWidget(self.browse_btn)
        topbar.addWidget(self.reload_btn)
        topbar.addSpacing(12)
        topbar.addWidget(self.only_missing_chk)

        # Navigation
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter (e.g., AccA or RearHair or p01)…")
        self.prev_btn = QPushButton("← Prev")
        self.next_btn = QPushButton("Next →")
        self.counter = QLabel("0 / 0")
        self.notice = QLabel("")
        self.notice.setWordWrap(True)

        nav = QHBoxLayout()
        nav.addWidget(self.filter_edit, 1)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.counter)

        # Preview panels
        self.face_panel = PreviewPanel("FACE (FG_...)")
        self.sv_panel = PreviewPanel("SV (SV_...)")
        self.tv_panel = PreviewPanel("TV (TV_...)")
        self.tvd_panel = PreviewPanel("TVD (TVD_...)")
        self.icon_panel = PreviewPanel("ICON (icon_...)")

        # Mask statuses
        self.mask_status_sv = QLabel("")
        self.mask_status_sv.setWordWrap(True)
        self.mask_status_tv = QLabel("")
        self.mask_status_tv.setWordWrap(True)
        self.mask_status_tvd = QLabel("")
        self.mask_status_tvd.setWordWrap(True)

        mask_box = QVBoxLayout()
        mask_box.addWidget(self.mask_status_sv)
        mask_box.addWidget(self.mask_status_tv)
        mask_box.addWidget(self.mask_status_tvd)
        mask_container = QWidget()
        mask_container.setLayout(mask_box)

        grid = QGridLayout()
        grid.addWidget(self.face_panel, 0, 0)
        grid.addWidget(self.sv_panel, 0, 1)
        grid.addWidget(self.tv_panel, 0, 2)
        grid.addWidget(self.tvd_panel, 1, 0)
        grid.addWidget(self.icon_panel, 1, 1)
        grid.addWidget(mask_container, 1, 2)

        # Actions
        self.ok_btn = QPushButton("OK (leave alone)")
        self.sort_copy_btn = QPushButton("Sort → Copy to Sort Folder")
        self.sort_move_btn = QPushButton("Sort → Move + Manifest")

        actions = QHBoxLayout()
        actions.addWidget(self.ok_btn)
        actions.addStretch(1)
        actions.addWidget(self.sort_copy_btn)
        actions.addWidget(self.sort_move_btn)

        # Main layout
        central = QWidget()
        layout = QVBoxLayout()
        layout.addLayout(topbar)
        layout.addLayout(nav)
        layout.addWidget(self.notice)
        layout.addLayout(grid)
        layout.addLayout(actions)
        central.setLayout(layout)
        self.setCentralWidget(central)

        # Events
        self.browse_btn.clicked.connect(self.choose_root)
        self.reload_btn.clicked.connect(self.scan)
        self.prev_btn.clicked.connect(self.prev)
        self.next_btn.clicked.connect(self.next)
        self.ok_btn.clicked.connect(self.mark_ok)
        self.sort_copy_btn.clicked.connect(lambda: self.sort_selected(mode="copy"))
        self.sort_move_btn.clicked.connect(lambda: self.sort_selected(mode="move"))
        self.filter_edit.textChanged.connect(self.apply_filter)
        self.only_missing_chk.toggled.connect(self.apply_filter)

        # Shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        act_next = QAction(self)
        act_next.setShortcut(QKeySequence(Qt.Key_Right))
        act_next.triggered.connect(self.next)
        self.addAction(act_next)

        act_prev = QAction(self)
        act_prev.setShortcut(QKeySequence(Qt.Key_Left))
        act_prev.triggered.connect(self.prev)
        self.addAction(act_prev)

        act_ok = QAction(self)
        act_ok.setShortcut(QKeySequence(Qt.Key_Return))
        act_ok.triggered.connect(self.mark_ok)
        self.addAction(act_ok)

        act_sort = QAction(self)
        act_sort.setShortcut(QKeySequence("S"))
        act_sort.triggered.connect(lambda: self.sort_selected(mode="copy"))
        self.addAction(act_sort)

        act_move = QAction(self)
        act_move.setShortcut(QKeySequence("M"))
        act_move.triggered.connect(lambda: self.sort_selected(mode="move"))
        self.addAction(act_move)

    def choose_root(self):
        path = QFileDialog.getExistingDirectory(self, "Select Generator Root Folder")
        if path:
            self.root_edit.setText(path)
            self.scan()

    def scan(self):
        root = self.root_edit.text().strip()
        if not root or not os.path.isdir(root):
            QMessageBox.warning(self, "Invalid folder", "Please pick a valid generator root folder.")
            return

        self.root_path = root
        self.groups = scan_generator(root)
        self.reviewed_ok.clear()

        self.all_keys = sorted(self.groups.keys(), key=lambda k: (k.gender, k.category, int(k.part_num)))
        self.keys = list(self.all_keys)
        self.index = 0
        self.apply_filter()

    def _jump_to_key(self, target_key):
        """After rescanning/filtering, jump to target_key if it still exists."""
        if not target_key:
            return
        try:
            self.index = self.keys.index(target_key)
        except ValueError:
            # If that exact key is gone (e.g., filtering changed), keep current index in range.
            self.index = min(self.index, max(0, len(self.keys) - 1))


    def apply_filter(self):
        if not self.all_keys:
            self.keys = []
            self.index = 0
            self.render_current()
            return

        txt = self.filter_edit.text().strip().lower()
        only_missing = self.only_missing_chk.isChecked()

        filtered: List[PartKey] = []
        for k in self.all_keys:
            if txt:
                if (txt not in k.category.lower()
                    and txt not in f"p{k.part_num}".lower()
                    and txt not in k.part_num.lower()
                    and txt not in k.gender.lower()):
                    continue

            if only_missing:
                g = self.groups[k]
                # main components missing if any of 5 are empty
                if all(g.candidates[c] for c in ["FACE", "SV", "TV", "TVD", "ICON"]):
                    continue

            filtered.append(k)

        self.keys = filtered
        self.index = 0
        self.render_current()

    def render_current(self):
        total = len(self.keys)
        if total == 0:
            self.counter.setText("0 / 0")
            self.face_panel.set_candidates([])
            self.sv_panel.set_candidates([])
            self.tv_panel.set_candidates([])
            self.tvd_panel.set_candidates([])
            self.icon_panel.set_candidates([])
            self.mask_status_sv.setText("No matching parts found with current filter.")
            self.mask_status_tv.setText("")
            self.mask_status_tvd.setText("")
            return

        self.index = max(0, min(self.index, total - 1))
        k = self.keys[self.index]
        g = self.groups[k]

        self.counter.setText(f"{self.index + 1} / {total}    |    {k.gender}  {k.category}  p{k.part_num}")

        self.face_panel.set_candidates(g.candidates["FACE"])
        self.sv_panel.set_candidates(g.candidates["SV"])
        self.tv_panel.set_candidates(g.candidates["TV"])
        self.tvd_panel.set_candidates(g.candidates["TVD"])
        self.icon_panel.set_candidates(g.candidates["ICON"])

        # Clear notice by default
        self.notice.setText("")

        # Determine if this key has any "main" sheets at all
        main_components = ["FACE", "SV", "TV", "TVD", "ICON"]
        has_any_main = any(bool(g.candidates[c]) for c in main_components)

        # Determine if it has any masks at all
        sv_mask_count = len(g.masks.get("SV", []))
        tv_mask_count = len(g.masks.get("TV", []))
        tvd_mask_count = len(g.masks.get("TVD", []))
        has_any_masks = (sv_mask_count + tv_mask_count + tvd_mask_count) > 0

        # If it's mask-only, show a big obvious notice
        if (not has_any_main) and has_any_masks:
            parts = []
            if sv_mask_count: parts.append(f"SV={sv_mask_count}")
            if tv_mask_count: parts.append(f"TV={tv_mask_count}")
            if tvd_mask_count: parts.append(f"TVD={tvd_mask_count}")
            self.notice.setText(
                "<b>⚠ Orphan mask-only entry:</b> Found mask sheet(s) "
                f"({', '.join(parts)}) but <b>no main sheets</b> for this part."
            )

        def mask_line(component: str, main_count: int) -> str:
            masks = g.masks.get(component, [])
            if masks:
                # Always show masks if found, even if main is missing
                if main_count > 0:
                    return f"<b>{component} mask:</b> ✅ {len(masks)} found (*_c)."
                else:
                    return f"<b>{component} mask:</b> ⚠ {len(masks)} found but main sheet is missing."
            else:
                # No masks found
                if main_count > 0:
                    return f"<b>{component} mask:</b> ❌ Missing (no *_c mask file found)."
                else:
                    return f"<b>{component} mask:</b> — (no mask, and main sheet missing)"

        self.mask_status_sv.setText(mask_line("SV", len(g.candidates["SV"])))
        self.mask_status_tv.setText(mask_line("TV", len(g.candidates["TV"])))
        self.mask_status_tvd.setText(mask_line("TVD", len(g.candidates["TVD"])))


    def next(self):
        if not self.keys:
            return
        self.index = min(self.index + 1, len(self.keys) - 1)
        self.render_current()

    def prev(self):
        if not self.keys:
            return
        self.index = max(self.index - 1, 0)
        self.render_current()

    def mark_ok(self):
        if not self.keys:
            return
        k = self.keys[self.index]
        self.reviewed_ok.add(k)
        if self.index < len(self.keys) - 1:
            self.index += 1
        self.render_current()

    def sort_selected(self, mode: str):
        """
        mode = "copy" or "move"
        Copies/moves the currently selected candidate file for each component into:
          <root>/Sort/<Gender>/<Category>_pXX/<component>/
        Masks for SV/TV/TVD go into <component>_MASK folders.
        Move mode writes manifest.json
        Copy mode writes copy_log.json
        """
        # Save current UI/filter state so we can restore it after a move
        saved_filter = self.filter_edit.text()
        saved_only_missing = self.only_missing_chk.isChecked()

        if not self.root_path or not self.keys:
            return

        k = self.keys[self.index]
        g = self.groups[k]

        selected = {
            "FACE": self.face_panel.selected_path(),
            "SV": self.sv_panel.selected_path(),
            "TV": self.tv_panel.selected_path(),
            "TVD": self.tvd_panel.selected_path(),
            "ICON": self.icon_panel.selected_path(),
        }

        any_selected = any(p for p in selected.values()) or any(g.masks[m] for m in g.masks)
        if not any_selected:
            QMessageBox.information(self, "Nothing to sort", "No files were selected/found for this part.")
            return

        sort_root = os.path.join(self.root_path, "Sort")
        part_folder = os.path.join(sort_root, k.gender, f"{k.category}_p{k.part_num}")
        os.makedirs(part_folder, exist_ok=True)

        manifest = {
            "mode": mode,
            "key": asdict(k),
            "selected": {},
            "masks": {"SV": [], "TV": [], "TVD": []},
        }

        def do_transfer(src: str, dest_dir: str) -> str:
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(src))
            if mode == "copy":
                shutil.copy2(src, dest)
            else:
                shutil.move(src, dest)
            return dest

        # Transfer main components (selected from dropdowns)
        for comp, src in selected.items():
            if not src:
                continue
            dest_dir = os.path.join(part_folder, comp)
            dest = do_transfer(src, dest_dir)
            manifest["selected"][comp] = {"from": src, "to": dest}

        # Transfer all masks for SV/TV/TVD (we keep them separate & all-inclusive)
        for comp in ("SV", "TV", "TVD"):
            masks = g.masks.get(comp, [])
            if not masks:
                continue
            dest_dir = os.path.join(part_folder, f"{comp}_MASK")
            for m in masks:
                dest = do_transfer(m.path, dest_dir)
                manifest["masks"][comp].append({"from": m.path, "to": dest})

        # Write manifest/log
        out_name = "manifest.json" if mode == "move" else "copy_log.json"
        manifest_path = os.path.join(part_folder, out_name)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Determine what "next" should be BEFORE we move anything
        next_key = None
        if self.index < len(self.keys) - 1:
            next_key = self.keys[self.index + 1]

        # Refresh view
        # Refresh view
        if mode == "move":
            self.scan()

            # Restore UI/filter state
            self.filter_edit.setText(saved_filter)
            self.only_missing_chk.setChecked(saved_only_missing)
            self.apply_filter()

            # Jump to the next item if possible
            if next_key:
                try:
                    self.index = self.keys.index(next_key)
                except ValueError:
                    self.index = min(self.index, max(0, len(self.keys) - 1))

            self.render_current()
        else:
            self.mark_ok()


        QMessageBox.information(
            self,
            "Sorted",
            f"Sorted files for {k.gender} {k.category} p{k.part_num}\ninto:\n{part_folder}"
        )


def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
