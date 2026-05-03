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
from textual.widgets import Header, Footer, DataTable, Static
from textual.containers import Container
from textual.binding import Binding

class PCloudCommander(App):
    """pCloud Commander TUI."""
    
    TITLE = "pCloud Commander"
    SUB_TITLE = "Interactive File Browser"
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("backspace", "up", "Go Up"),
        Binding("u", "up", "Go Up"),
    ]
    
    CSS = """
    DataTable {
        height: 1fr;
        border: solid $primary;
    }
    #path-bar {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    #status-bar {
        height: 1;
        background: #2c3e50;
        color: #ecf0f1;
        padding: 0 1;
        text-style: italic;
    }
    """

    def __init__(self, cfg_overrides=None):
        super().__init__()
        self.env_file = find_env_file()
        self.cfg = pc.effective_config(env_file=self.env_file, overrides=cfg_overrides)
        self.current_folderid = 0
        self.history: List[tuple[int, str]] = []  # Stack von (folderid, name)
        self.current_path_str = "/"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self.current_path_str, id="path-bar")
        yield Container(
            DataTable(cursor_type="row"),
            id="main-container"
        )
        yield Static(f"Lib: {pc_path} | Env: {self.env_file}", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Name", "Size", "Modified", "ID")
        self.refresh_list()

    def refresh_list(self):
        table = self.query_one(DataTable)
        table.clear()
        
        # Pfad-Anzeige aktualisieren
        path_bar = self.query_one("#path-bar", Static)
        path_bar.update(f"📂 {self.current_path_str}")

        try:
            res = pc.listfolder(self.cfg, folderid=self.current_folderid)
            if res.get("result") == 0:
                metadata = res.get("metadata", {})
                contents = metadata.get("contents", [])
                
                # Verzeichnisse zuerst
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

    def action_up(self):
        """Eine Ebene nach oben gehen."""
        if self.history:
            prev_folderid, _ = self.history.pop()
            self.current_folderid = prev_folderid
            self._update_path_str()
            self.refresh_list()
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
    args = parser.parse_args()
    
    app = PCloudCommander(cfg_overrides={"env_file": args.env_file} if args.env_file else None)
    app.run()
