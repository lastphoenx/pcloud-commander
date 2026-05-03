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
import subprocess
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
from textual.widgets import Header, Footer, Static, DirectoryTree, Label, Tree, OptionList
from textual.widgets.option_list import Option
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
        background: rgba(0, 0, 0, 0.7);
    }
    #confirm-box {
        width: 60;
        height: 11;
        border: double #ff00ff;
        background: #1a1a1a;
        padding: 1 2;
    }
    #confirm-msg {
        height: 4;
        color: #ffffff;
        text-align: center;
        text-style: bold;
    }
    #confirm-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }
    Button {
        margin: 0 2;
    }
    #btn-yes {
        background: #ff00ff;
        color: #000000;
    }
    #btn-no {
        background: #333333;
        color: #ffffff;
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



class ActionMenu(ModalScreen):
    """Menü zur Auswahl von pcloud-tools Kommandos."""

    CSS = """
    ActionMenu {
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }
    #menu-box {
        width: 70;
        height: auto;
        max-height: 25;
        border: double #ff79c6; /* Neon Magenta */
        background: #1e1e1e;
        padding: 1 2;
    }
    #menu-title {
        height: 1;
        margin-bottom: 1;
        color: #f1c40f; /* Yellow */
        text-align: center;
        text-style: bold;
    }
    OptionList {
        background: #1e1e1e;
        color: #a9b1d6;
        border: solid #333333;
    }
    OptionList > .option-list--cursor {
        background: #f1c40f;
        color: #000000;
        text-style: bold;
    }
    #menu-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }
    Button {
        margin: 0 2;
        border: none;
    }
    #btn-run {
        background: #50fa7b; /* Green */
        color: #000000;
    }
    #btn-cancel {
        background: #ff5555; /* Red */
        color: #000000;
    }
    """

    def __init__(self, actions: List[tuple[str, str]]) -> None:
        super().__init__()
        self.actions = actions

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-box"):
            yield Label("Select Action to Run", id="menu-title")
            yield OptionList(
                *[Option(label, id=cmd) for label, cmd in self.actions]
            )
            with Horizontal(id="menu-buttons"):
                yield Button("Run [Enter]", id="btn-run")
                yield Button("Cancel [Esc]", id="btn-cancel")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            selected = self.query_one(OptionList).highlighted
            if selected is not None:
                self.dismiss(self.actions[selected][1])
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            selected = self.query_one(OptionList).highlighted
            if selected is not None:
                self.dismiss(self.actions[selected][1])


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
        Binding("a", "launch", "Actions", show=True),
    ]
    
    CSS = """
    Screen {
        background: #000000;
        color: #ffffff;
    }

    #left-pane, #right-pane {
        width: 1fr;
        height: 1fr;
        border: solid #333333;
        background: #000000;
    }
    #left-pane.active-pane, #right-pane.active-pane {
        border: double #00ffff; /* Neon Cyan for active pane */
    }
    
    /* Panel Headers */
    .panel-label {
        height: 1;
        background: #1a1a1a;
        color: #aaaaaa;
        padding: 0 1;
        text-style: bold;
    }
    .active-pane .panel-label {
        background: #f1c40f; /* Yellow for active header */
        color: #000000;
    }

    /* DirectoryTree (Local) */
    DirectoryTree {
        height: 1fr;
        background: #000000;
        color: #ffffff;
    }
    DirectoryTree > .directory-tree--cursor {
        background: #f1c40f; /* Yellow cursor */
        color: #000000;
        text-style: bold;
    }
    DirectoryTree > .directory-tree--file {
        color: #50fa7b; /* Neon Green for Files */
    }
    DirectoryTree > .directory-tree--folder {
        color: #bd93f9; /* Purple for Folders */
        text-style: bold;
    }

    /* pCloud Tree (right pane) */
    #pcloud-tree {
        height: 1fr;
        background: #000000;
        color: #ffffff;
    }
    #pcloud-tree > .tree--cursor {
        background: #f1c40f; /* Yellow cursor */
        color: #000000;
        text-style: bold;
    }
    #pcloud-tree .tree--guides {
        color: #444444;
    }
    #pcloud-tree .tree--label {
        color: #ffffff;
    }

    /* Path & Status Bars */
    #path-bar {
        height: 1;
        background: #f1c40f; /* Solid Yellow bar */
        color: #000000;
        padding: 0 1;
        text-style: bold;
    }
    #status-bar {
        height: 1;
        background: #1a1a1a;
        color: #ff79c6; /* Neon Pink */
        padding: 0 1;
        text-style: italic;
    }

    /* ActionMenu Style Fixes */
    #menu-box {
        border: double #00ffff;
        background: #000000;
    }
    OptionList {
        background: #000000;
        color: #ffffff;
    }
    OptionList > .option-list--cursor {
        background: #f1c40f;
        color: #000000;
        text-style: bold;
    }
    """

    def __init__(self, cfg_overrides=None, local_root: str = "/srv"):
        super().__init__()
        self.env_file = find_env_file()
        self.cfg = pc.effective_config(env_file=self.env_file, overrides=cfg_overrides)
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
                Tree("/", id="pcloud-tree"),
                id="right-pane",
            ),
        )
        yield Static(f"Lib: {pc_path} | Env: {self.env_file}", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._apply_pane_focus()
        self.call_after_refresh(self._init_pcloud_tree)

    def _init_pcloud_tree(self) -> None:
        """Root-Ebene des pCloud-Baums laden."""
        tree = self.query_one("#pcloud-tree", Tree)
        tree.root.data = {"id": 0, "is_folder": True, "name": "", "loaded": False}
        self._load_tree_node(tree.root, 0)
        tree.root.expand()

    def _load_tree_node(self, node, folderid: int) -> None:
        """pCloud-Ordner-Inhalt lazy in einen Tree-Knoten laden."""
        try:
            res = pc.listfolder(self.cfg, folderid=folderid)
            if res.get("result") == 0:
                contents = res.get("metadata", {}).get("contents", [])
                for item in sorted(contents, key=lambda x: (not x["isfolder"], x["name"].lower())):
                    if item["isfolder"]:
                        child = node.add(
                            f"📁 {item['name']}",
                            data={"id": item["folderid"], "is_folder": True,
                                  "name": item["name"], "loaded": False},
                        )
                        child.add_leaf("⋯", data=None)  # Platzhalter für expandierbaren Pfeil
                    else:
                        size_str = self._format_size(item["size"])
                        node.add_leaf(
                            f"📄 {item['name']}  [{size_str}]",
                            data={"id": item["fileid"], "is_folder": False,
                                  "name": item["name"], "size": item["size"],
                                  "mtime": item.get("modified", "")},
                        )
            else:
                self.notify(f"API Error: {res.get('error')}", severity="error")
        except Exception as e:
            self.notify(f"Connection Error: {e}", severity="error")
        if node.data:
            node.data["loaded"] = True

    def _node_path_str(self, node) -> str:
        """Baut den pCloud-Pfad-String aus der Node-Hierarchie."""
        parts = []
        n = node
        while n and n.parent is not None:  # Root-Node hat parent=None
            if n.data and n.data.get("name"):
                parts.append(n.data["name"])
            n = n.parent
        return "/" if not parts else "/" + "/".join(reversed(parts)) + "/"

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
            self.query_one("#pcloud-tree", Tree).focus()

    def action_switch_pane(self) -> None:
        self.active_pane = "left" if self.active_pane == "right" else "right"
        self._apply_pane_focus()

    def refresh_list(self):
        """Baut den pCloud-Baum komplett neu auf (Root-Ebene)."""
        tree = self.query_one("#pcloud-tree", Tree)
        tree.root.remove_children()
        if tree.root.data:
            tree.root.data["loaded"] = False
        else:
            tree.root.data = {"id": 0, "is_folder": True, "name": "", "loaded": False}
        self._load_tree_node(tree.root, 0)
        tree.root.expand()
        self.query_one("#path-bar", Static).update("pCloud: /")
        self.query_one("#pcloud-label", Label).update("☁  pCloud: /")

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Lazy-Load: Ordner-Inhalt beim ersten Aufklappen laden."""
        node = event.node
        if node.data and not node.data.get("loaded") and node.data.get("is_folder"):
            node.remove_children()
            self._load_tree_node(node, node.data["id"])

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Pfad-Bar beim Cursor-Bewegen aktualisieren."""
        node = event.node
        if node and node.data:
            path = self._node_path_str(node)
            self.query_one("#path-bar", Static).update(f"pCloud: {path}")
            self.query_one("#pcloud-label", Label).update(f"☁  pCloud: {path}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Enter auf Datei: kurze Info + Tastenbelegung anzeigen."""
        node = event.node
        if node.data and not node.data.get("is_folder"):
            name = node.data.get("name", "")
            size = self._format_size(node.data.get("size", 0))
            self.notify(f"📄 {name}  {size}  │  d=download  F8=delete", severity="information")

    def _get_selected_row(self):
        """Gibt (name_raw, item_id, is_folder) des aktuell markierten Tree-Knotens zurück."""
        tree = self.query_one("#pcloud-tree", Tree)
        node = tree.cursor_node
        if node is None or node.data is None:
            return None, None, None
        d = node.data
        return d.get("name"), d.get("id"), d.get("is_folder", False)

    def action_launch(self) -> None:
        """A — Menü mit pcloud-tools Kommandos öffnen."""
        actions = []
        
        # Lokale Datei ausgewählt?
        local_sel = None
        if self.active_pane == "left":
            tree = self.query_one(DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                local_sel = str(tree.cursor_node.data.path)
        
        # pCloud Datei ausgewählt?
        pcloud_name, pcloud_id, pcloud_is_folder = self._get_selected_row()
        
        # Bestimme Ziel-Ordner ID in pCloud
        target_folderid = 0
        tree = self.query_one("#pcloud-tree", Tree)
        if tree.cursor_node and tree.cursor_node.data:
            if pcloud_is_folder:
                target_folderid = pcloud_id
            elif tree.cursor_node.parent and tree.cursor_node.parent.data:
                target_folderid = tree.cursor_node.parent.data.get("id", 0)

        # Generische Aktionen
        actions.append(("Refresh pCloud List", "refresh"))
        
        if local_sel:
            path_obj = Path(local_sel)
            if path_obj.is_file():
                actions.append((f"Upload to pCloud: {path_obj.name}", f"upload_file:{local_sel}:{target_folderid}"))
            elif path_obj.is_dir():
                actions.append((f"Sync Folder to pCloud: {path_obj.name}", f"sync_dir:{local_sel}:{target_folderid}"))

        if pcloud_name and not pcloud_is_folder:
             actions.append((f"Download from pCloud: {pcloud_name}", "download"))

        def _on_action(cmd_key: Optional[str]) -> None:
            if not cmd_key:
                return
            
            if cmd_key == "refresh":
                self.refresh_list()
            elif cmd_key == "download":
                self.action_download()
            elif cmd_key.startswith("upload_file:"):
                _, local_path, fid = cmd_key.split(":", 2)
                self._run_tool("pcloud_simple_upload.py", [local_path, fid])
            elif cmd_key.startswith("sync_dir:"):
                _, local_path, fid = cmd_key.split(":", 2)
                # Beispiel für pcloud_quick_delta.py
                self._run_tool("pcloud_quick_delta.py", ["--src", local_path, "--dst-id", fid])

        self.push_screen(ActionMenu(actions), _on_action)

    def _run_tool(self, script_name: str, args: List[str]):
        """Führt ein pcloud-tools Skript aus (suspendiert TUI)."""
        # Pfad zum Skript finden (im gleichen Verzeichnis wie pcloud_bin_lib.py)
        script_path = os.path.join(os.path.dirname(pc_path), script_name)
        if not os.path.exists(script_path):
            self.notify(f"Script not found: {script_name}", severity="error")
            return

        cmd = [sys.executable, script_path] + args
        
        def run_in_suspend():
            with self.suspend():
                print(f"\n>>> Running: {' '.join(cmd)}\n")
                subprocess.run(cmd)
                input("\nPress Enter to return to Commander...")
            self.refresh_list()

        run_in_suspend()

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
        """Eine Ebene nach oben: im pCloud-Tree zum Eltern-Knoten."""
        if self.active_pane == "right":
            tree = self.query_one("#pcloud-tree", Tree)
            node = tree.cursor_node
            if node and node.parent is not None and node.parent.parent is not None:
                # Aktuellen Knoten einklappen (falls Ordner und geöffnet)
                if node.is_expanded:
                    node.collapse()
                tree.move_cursor(node.parent)
            elif node and node.parent is not None and node.parent.parent is None:
                # Wir sind bereits auf Root-Ebene
                self.notify("Already at root.", severity="warning")
        else:
            pass  # DirectoryTree hat eigene Navigation

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
