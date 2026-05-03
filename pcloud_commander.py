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
from pathlib import Path
from typing import Optional, Dict, Any

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
from textual.widgets import Header, Footer, DataTable, Static, Label
from textual.containers import Container, Vertical

class PCloudCommander(App):
    """pCloud Commander TUI."""
    
    TITLE = "pCloud Commander"
    SUB_TITLE = "Interactive File Browser"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]
    CSS = """
    DataTable {
        height: 1fr;
        border: solid green;
    }
    #status-bar {
        height: 1;
        background: $accent;
        color: white;
        padding: 0 1;
    }
    """

    def __init__(self, cfg_overrides=None):
        super().__init__()
        self.env_file = find_env_file()
        self.cfg = pc.effective_config(env_file=self.env_file, overrides=cfg_overrides)
        self.current_folderid = 0
        self.history = []

    def compose(self) -> ComposeResult:
        yield Header()
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
                    table.add_row(name, size, mtime, str(item_id))
            else:
                self.notify(f"API Error: {res.get('error')}", severity="error")
        except Exception as e:
            self.notify(f"Connection Error: {str(e)}", severity="error")

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
