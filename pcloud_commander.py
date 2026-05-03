#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pCloud Commander - Interactive TUI File Browser
================================================
Based on pcloud_bin_lib.py and Textual.
"""

import os
import sys
import argparse
import threading
from pathlib import Path
from typing import Optional, List

# ==================== Library Loading ====================

def load_pcloud_lib(lib_path: Optional[str] = None):
    """
    Lädt pcloud_bin_lib.py mit flexibler Pfad-Auflösung.
    Priorität wie in pcloud_simple_upload.py
    """
    search_paths = []
    if lib_path:
        search_paths.append(lib_path)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths.extend([
        os.path.join(script_dir, "pcloud_bin_lib.py"),
        os.path.join(script_dir, "..", "pcloud-tools", "main", "pcloud_bin_lib.py"), # Server structure
        os.path.join(script_dir, "..", "pcloud-tools", "pcloud_bin_lib.py"),        # Local structure
        "/opt/apps/pcloud-tools/main/pcloud_bin_lib.py",
    ])
    
    for path in search_paths:
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.exists(path):
            lib_dir = os.path.dirname(path)
            if lib_dir not in sys.path:
                sys.path.insert(0, lib_dir)
            try:
                import pcloud_bin_lib as pc
                return pc, path
            except ImportError:
                continue
    return None, None

def find_env_file(env_path: Optional[str] = None):
    """Sucht die .env Datei der pcloud-tools."""
    if env_path and os.path.exists(env_path):
        return env_path
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, ".env"),
        os.path.join(script_dir, "..", "pcloud-tools", "main", ".env"),
        os.path.join(script_dir, "..", "pcloud-tools", ".env"),
        "/opt/apps/pcloud-tools/main/.env",
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return None

# Initialisiere Library
pc, pc_path = load_pcloud_lib()
if not pc:
    print("Error: pcloud_bin_lib.py not found.")
    sys.exit(1)

# ==================== Textual UI ====================

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, DirectoryTree, Label
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button


DEFAULT_DOWNLOAD_DIR = "/srv/nas/restore"


class ConfirmModal(ModalScreen):
    """Einfaches Ja/Nein-Popup."""

    CSS = """
    ConfirmModal {
        align: center middle;
    }
    #confirm-box {
        width: 60;
        height: 9;
        border: double #f1c40f;
        background: #1a1a2e;
        padding: 1 2;
    }
    #confirm-msg {
        height: 3;
        color: #ffffff;
        text-align: center;
    }
    #confirm-buttons {
        align: center middle;
        height: 3;
    }
    Button {
        margin: 0 2;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self.message, id="confirm-msg")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes [F8]", variant="error", id="btn-yes")
                yield Button("No  [Esc]", variant="primary", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "f8":
            self.dismiss(True)


class PCloudCommander(App):
    """pCloud Commander TUI."""
    
    TITLE = "pCloud Commander"
    SUB_TITLE = "Interactive Dual-Pane Browser"
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("backspace", "up", "Go Up"),
        Binding("u", "up", "Go Up"),
        Binding("tab", "switch_pane", "Switch Pane"),
        Binding("d", "download", "Download", show=True),
        Binding("f8", "delete", "Delete", show=True),
    ]
    
    CSS = """
    #left-pane, #right-pane {
        width: 1fr;
        height: 1fr;
        border: solid #34495e;
    }
    #left-pane.active-pane, #right-pane.active-pane {
        border: thick #f1c40f;
    }
    
    /* Panel Headers */
    .panel-label {
        height: 1;
        background: #34495e;
        color: #ffffff;
        padding: 0 1;
        text-style: bold;
    }
    .active-pane .panel-label {
        background: #f1c40f;
        color: #000000;
    }

    /* DirectoryTree (Local) */
    DirectoryTree {
        height: 1fr;
        background: $surface;
    }
    DirectoryTree > .directory-tree--cursor {
        background: #f1c40f;
        color: #000000;
        text-style: bold;
    }

    /* DataTable (pCloud) */
    DataTable {
        height: 1fr;
    }
    DataTable > .datatable--cursor {
        background: #f1c40f;
        color: #000000;
        text-style: bold;
    }

    /* Path & Status Bars */
    #path-bar {
        height: 1;
        background: #f1c40f;
        color: #000000;
        padding: 0 1;
        text-style: bold;
    }
    #status-bar {
        height: 1;
        background: #2c3e50;
        color: #bdc3c7;
        padding: 0 1;
        text-style: italic;
    }
    """

    def __init__(self, cfg_overrides=None, local_root: str = "/srv"):
        super().__init__()
        self.env_file = find_env_file()
        self.cfg = pc.effective_config(env_file=self.env_file, overrides=cfg_overrides)
        self.current_folderid = 0
        self.history: List[tuple[int, str]] = []
        self.current_path_str = "/"
        # Fallback auf / falls /srv nicht existiert (lokale Entwicklung)
        self.local_root = local_root if Path(local_root).exists() else "/"
        self.active_pane = "right"  # Startfokus auf pCloud
        self.download_dir = DEFAULT_DOWNLOAD_DIR

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="path-bar")
        yield Horizontal(
            Vertical(
                Label(f"📁 Local: {self.local_root}", classes="panel-label"),
                DirectoryTree(self.local_root),
                id="left-pane",
            ),
            Vertical(
                Label("☁  pCloud: /", classes="panel-label", id="pcloud-label"),
                DataTable(cursor_type="row"),
                id="right-pane",
            ),
        )
        yield Static(f"Lib: {pc_path} | Env: {self.env_file}", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Name", "Size", "Modified", "ID")
        self._apply_pane_focus()
        self.refresh_list()

    def _apply_pane_focus(self) -> None:
        left = self.query_one("#left-pane")
        right = self.query_one("#right-pane")
        if self.active_pane == "left":
            left.add_class("active-pane")
            right.remove_class("active-pane")
            self.query_one(DirectoryTree).focus()
        else:
            right.add_class("active-pane")
            left.remove_class("active-pane")
            self.query_one(DataTable).focus()

    def action_switch_pane(self) -> None:
        self.active_pane = "left" if self.active_pane == "right" else "right"
        self._apply_pane_focus()

    def refresh_list(self):
        table = self.query_one(DataTable)
        table.clear()
        
        # Pfad-Anzeige aktualisieren
        path_bar = self.query_one("#path-bar", Static)
        path_bar.update(f"Current Path: {self.current_path_str}")
        
        pcloud_label = self.query_one("#pcloud-label", Label)
        pcloud_label.update(f"☁  pCloud: {self.current_path_str}")

        try:
            res = pc.listfolder(self.cfg, folderid=self.current_folderid)
            if res.get("result") == 0:
                metadata = res.get("metadata", {})
                contents = metadata.get("contents", [])
                
                for item in sorted(contents, key=lambda x: (not x["isfolder"], x["name"].lower())):
                    name = item["name"]
                    if item["isfolder"]:
                        name = f"📁 {name}/"
                        size = "-"
                        item_id = item["folderid"]
                    else:
                        name = f"📄 {name}"
                        size = self._format_size(item["size"])
                        item_id = item["fileid"]
                    
                    mtime = item.get("modified", "")
                    table.add_row(name, size, mtime, str(item_id), key=str(item_id))
            else:
                self.notify(f"API Error: {res.get('error')}", severity="error")
        except Exception as e:
            self.notify(f"Connection Error: {str(e)}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Navigation beim Drücken von Enter."""
        row_data = self.query_one(DataTable).get_row(event.row_key)
        name_with_icon = str(row_data[0])
        item_id = int(row_data[3])
        
        if "📁" in name_with_icon:
            # Es ist ein Ordner
            folder_name = name_with_icon.replace("📁 ", "").rstrip("/")
            self.history.append((self.current_folderid, folder_name))
            self.current_folderid = item_id
            self._update_path_str()
            self.refresh_list()
        else:
            # Es ist eine Datei
            self.notify(f"File selected: {name_with_icon}", severity="information")

    def _get_selected_row(self):
        """Gibt (name_raw, item_id, is_folder) der aktuell markierten Zeile zurück."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None, None, None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        row_data = table.get_row(row_key)
        name_with_icon = str(row_data[0])
        item_id = int(row_data[3])
        is_folder = "📁" in name_with_icon
        name_raw = name_with_icon.replace("📁 ", "").replace("📄 ", "").rstrip("/")
        return name_raw, item_id, is_folder

    def action_download(self) -> None:
        """d — Markierte Datei nach DEFAULT_DOWNLOAD_DIR herunterladen."""
        if self.active_pane != "right":
            self.notify("Switch to pCloud pane to download.", severity="warning")
            return
        name_raw, item_id, is_folder = self._get_selected_row()
        if name_raw is None:
            self.notify("No file selected.", severity="warning")
            return
        if is_folder:
            self.notify("Cannot download a folder (select a file).", severity="warning")
            return

        dest_dir = Path(self.download_dir)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.notify(f"Cannot create download dir: {e}", severity="error")
            return

        local_path = str(dest_dir / name_raw)
        self.notify(f"⬇ Downloading {name_raw} …", timeout=10)

        def _run():
            try:
                pc.download_binaryfile_to(self.cfg, fileid=item_id, local_path=local_path)
                self.call_from_thread(
                    self.notify, f"✓ Saved to {local_path}", severity="information", timeout=8
                )
            except Exception as e:
                self.call_from_thread(
                    self.notify, f"✗ Download failed: {e}", severity="error", timeout=10
                )

        threading.Thread(target=_run, daemon=True).start()

    def action_delete(self) -> None:
        """F8 — Markiertes Element nach Bestätigung löschen."""
        if self.active_pane != "right":
            self.notify("Switch to pCloud pane to delete.", severity="warning")
            return
        name_raw, item_id, is_folder = self._get_selected_row()
        if name_raw is None:
            self.notify("No item selected.", severity="warning")
            return

        kind = "folder (recursive)" if is_folder else "file"
        msg = f"Delete {kind}:\n{name_raw}?"

        def _on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            try:
                if is_folder:
                    pc.deletefolder_recursive(self.cfg, folderid=item_id)
                else:
                    pc.deletefile(self.cfg, fileid=item_id)
                self.notify(f"✓ Deleted: {name_raw}", severity="information")
                self.refresh_list()
            except Exception as e:
                self.notify(f"✗ Delete failed: {e}", severity="error", timeout=10)

        self.push_screen(ConfirmModal(msg), _on_confirm)


    def action_up(self):
        """Eine Ebene nach oben gehen."""
        if self.active_pane == "right" and self.history:
            prev_folderid, _ = self.history.pop()
            self.current_folderid = prev_folderid
            self._update_path_str()
            self.refresh_list()
        elif self.active_pane == "left":
            # DirectoryTree hat eigene Navigation, aber wir könnten hier '..' Logik einbauen
            pass
        else:
            self.notify("Already at root.", severity="warning")

    def _update_path_str(self):
        """Baut den Pfad-String aus der History."""
        if not self.history:
            self.current_path_str = "/"
        else:
            names = [h[1] for h in self.history]
            self.current_path_str = "/" + "/".join(names) + "/"

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def action_refresh(self):
        self.refresh_list()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", help="Path to .env file")
    parser.add_argument("--local-root", default="/srv", help="Local directory to browse (default: /srv)")
    parser.add_argument("--download-dir", default=DEFAULT_DOWNLOAD_DIR,
                        help=f"Local download target (default: {DEFAULT_DOWNLOAD_DIR})")
    args = parser.parse_args()
    
    app = PCloudCommander(
        cfg_overrides={"env_file": args.env_file} if args.env_file else None,
        local_root=args.local_root,
    )
    app.download_dir = args.download_dir
    app.run()
