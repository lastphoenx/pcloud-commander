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
from dataclasses import dataclass
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

# ==================== Theme System ====================

@dataclass
class Palette:
    """Central color palette. All CSS is derived from these tokens."""
    name: str
    # Backgrounds
    bg: str           # screen background
    surface: str      # pane / widget background (same as bg or slightly lighter)
    panel: str        # header/footer/label strips
    overlay: str      # modal dialog background
    # Borders
    border: str       # inactive pane border
    border_active: str  # active pane + modal border (accent color)
    # Text
    text: str         # primary readable text
    text_muted: str   # inactive labels, hints
    text_dim: str     # guides, status bar, very dimmed
    # Cursor / selection
    accent: str       # cursor/selection background (focused)
    accent_fg: str    # text ON accent background
    accent_dim: str   # cursor background when tree is NOT focused
    # Semantic item colors
    folder: str       # folder nodes
    file: str         # file nodes
    # Button semantics
    success: str      # Run / Yes button background
    error: str        # Cancel / No / Delete button background


PALETTES: dict[str, Palette] = {
    # ── Posting-like: calm teal on near-black ──────────────────────────────
    "posting": Palette(
        name="posting",
        bg="#0d0d0d", surface="#0d0d0d", panel="#1a1a1a", overlay="#111111",
        border="#2d2d2d", border_active="#00b5cc",
        text="#d0d0d0", text_muted="#666666", text_dim="#3a3a3a",
        accent="#f1c40f", accent_fg="#000000", accent_dim="#a88900",
        folder="#9d84c7", file="#7ec8a0",
        success="#27ae60", error="#c0392b",
    ),
    # ── Hacker: terminal green on black ────────────────────────────────────
    "hacker": Palette(
        name="hacker",
        bg="#000000", surface="#000000", panel="#0a0a0a", overlay="#050505",
        border="#1a3a1a", border_active="#00ff41",
        text="#00cc33", text_muted="#006614", text_dim="#003308",
        accent="#00ff41", accent_fg="#000000", accent_dim="#00aa2b",
        folder="#00cc33", file="#009922",
        success="#00ff41", error="#ff0000",
    ),
    # ── Calm: muted blue-grey ──────────────────────────────────────────────
    "calm": Palette(
        name="calm",
        bg="#1c1e26", surface="#232530", panel="#2a2c3a", overlay="#1c1e26",
        border="#3a3c4e", border_active="#6c91bf",
        text="#a8aebb", text_muted="#5c6270", text_dim="#3a3c4e",
        accent="#6c91bf", accent_fg="#1c1e26", accent_dim="#3d5a80",
        folder="#b083ea", file="#59c6ab",
        success="#3fc56b", error="#fc4b5f",
    ),
}

DEFAULT_PALETTE = "posting"


def build_css(p: Palette) -> str:
    """Generate full app CSS from a single Palette — one source of truth."""
    return f"""
    /* ── Screen ─────────────────────────────────────────────────── */
    Screen {{
        background: {p.bg};
        color: {p.text};
    }}

    /* ── Panes ───────────────────────────────────────────────────── */
    #left-pane, #right-pane {{
        width: 1fr;
        height: 1fr;
        border: solid {p.border};
        background: {p.surface};
    }}
    #left-pane.active-pane, #right-pane.active-pane {{
        border: double {p.border_active};
    }}

    /* ── Panel labels (pane headers) ─────────────────────────────── */
    .panel-label {{
        height: 1;
        background: {p.panel};
        color: {p.text_muted};
        padding: 0 1;
        text-style: bold;
    }}
    .active-pane .panel-label {{
        color: {p.border_active};
    }}

    /* ── Trees: local (DirectoryTree) AND pCloud (Tree) ──────────── */
    /*   Both trees share the same rules — same look left and right.  */
    DirectoryTree, #pcloud-tree {{
        height: 1fr;
        background: {p.surface};
        color: {p.text};
    }}
    /* Guide lines */
    DirectoryTree .tree--guides,
    #pcloud-tree .tree--guides {{
        color: {p.text_dim};
    }}
    /* Folder / file node colors (DirectoryTree-specific classes) */
    DirectoryTree .directory-tree--folder {{
        color: {p.folder};
        text-style: bold;
    }}
    DirectoryTree .directory-tree--file {{
        color: {p.file};
    }}
    /* Cursor: focused tree (same selector for both widget types) */
    DirectoryTree .tree--cursor,
    #pcloud-tree .tree--cursor {{
        background: {p.accent};
        color: {p.accent_fg};
        text-style: bold;
    }}
    /* Cursor: unfocused tree — MUST be styled or Textual uses its default blue */
    DirectoryTree .tree--highlight,
    #pcloud-tree .tree--highlight {{
        background: {p.accent_dim};
        color: {p.accent_fg};
    }}

    /* ── Path bar ─────────────────────────────────────────────────── */
    #path-bar {{
        height: 1;
        background: {p.panel};
        color: {p.border_active};
        padding: 0 1;
        text-style: bold;
    }}

    /* ── Status bar ───────────────────────────────────────────────── */
    #status-bar {{
        height: 1;
        background: {p.panel};
        color: {p.text_dim};
        padding: 0 1;
    }}

    /* ── Modals (ActionMenu + ConfirmModal) ───────────────────────── */
    ActionMenu, ConfirmModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }}
    #menu-box, #confirm-box {{
        width: 60;
        height: auto;
        border: double {p.border_active};
        background: {p.overlay};
        padding: 1 2;
    }}
    #menu-title, #confirm-msg {{
        color: {p.text};
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }}

    /* ── OptionList ───────────────────────────────────────────────── */
    OptionList {{
        background: {p.overlay};
        color: {p.text};
        border: solid {p.border};
    }}
    OptionList > .option-list--option-highlighted {{
        background: {p.accent};
        color: {p.accent_fg};
        text-style: bold;
    }}

    /* ── Buttons ──────────────────────────────────────────────────── */
    #menu-buttons, #confirm-buttons {{
        align: center middle;
        height: 3;
        margin-top: 1;
    }}
    Button {{
        margin: 0 2;
        text-style: bold;
    }}
    #btn-run, #btn-yes {{
        background: {p.success};
        color: {p.accent_fg};
    }}
    #btn-cancel, #btn-no {{
        background: {p.error};
        color: #ffffff;
    }}
    """

class ConfirmModal(ModalScreen):
    """Einfaches Ja/Nein-Popup."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self.message, id="confirm-msg")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes [F8]", id="btn-yes")
                yield Button("No  [Esc]", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "f8":
            self.dismiss(True)



class ActionMenu(ModalScreen):
    """Menü zur Auswahl von pcloud-tools Kommandos."""

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
        """Auswahl per Enter oder Klick auf Option."""
        self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Auswahl per Run-Button."""
        if event.button.id == "btn-run":
            option_list = self.query_one(OptionList)
            if option_list.highlighted is not None:
                option = option_list.get_option_at_index(option_list.highlighted)
                self.dismiss(option.id)
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            option_list = self.query_one(OptionList)
            if option_list.highlighted is not None:
                option = option_list.get_option_at_index(option_list.highlighted)
                self.dismiss(option.id)


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

    # CSS is set dynamically in __init__ via build_css(palette)
    CSS = build_css(PALETTES[DEFAULT_PALETTE])

    def __init__(self, cfg_overrides=None, local_root: str = "/srv",
                 palette_name: str = DEFAULT_PALETTE):
        super().__init__()
        self.env_file = find_env_file()
        self.cfg = pc.effective_config(env_file=self.env_file, overrides=cfg_overrides)
        self.local_root = local_root if Path(local_root).exists() else "/"
        self.active_pane = "right"
        self.download_dir = DEFAULT_DOWNLOAD_DIR
        # Apply selected palette
        palette = PALETTES.get(palette_name, PALETTES[DEFAULT_PALETTE])
        PCloudCommander.CSS = build_css(palette)

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
        """Pfad-Bar beim Cursor-Bewegen aktualisieren (pCloud & Local)."""
        if event.control.id == "pcloud-tree":
            node = event.node
            if node and node.data and isinstance(node.data, dict):
                p_str = self._node_path_str(node)
                self.query_one("#path-bar", Static).update(f"pCloud: {p_str}")
                self.query_one("#pcloud-label", Label).update(f"☁  pCloud: {p_str}")
        elif isinstance(event.control, DirectoryTree):
            if event.node and event.node.data:
                # Robust path detection for local files
                p_obj = getattr(event.node.data, "path", event.node.data)
                self.query_one("#path-bar", Static).update(f"Local: {p_obj}")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Lokale Datei ausgewählt: Feedback geben."""
        self.notify(f"📄 {event.path.name}  │  a=actions", severity="information")

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Lokaler Ordner ausgewählt: Pfad-Bar aktualisieren."""
        self.query_one("#path-bar", Static).update(f"Local: {event.path}")

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
    parser.add_argument("--theme", default=DEFAULT_PALETTE,
                        choices=list(PALETTES.keys()),
                        help=f"Color theme: {', '.join(PALETTES.keys())} (default: {DEFAULT_PALETTE})")
    args = parser.parse_args()

    app = PCloudCommander(
        cfg_overrides={"env_file": args.env_file} if args.env_file else None,
        local_root=args.local_root,
        palette_name=args.theme,
    )
    app.download_dir = args.download_dir
    app.run()
