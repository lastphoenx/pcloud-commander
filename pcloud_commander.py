#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pCloud Commander - Interactive TUI File Browser
================================================
Based on pcloud_bin_lib.py and Textual.

Theme-System: Uses Textual's native register_theme() API so that
all built-in widgets (Tree cursor, Header, Footer, OptionList, …)
pick up the palette automatically.  Custom CSS is minimal — only
for our own widgets (#path-bar, .panel-label, modals).
"""

import os
import sys
import argparse
import threading
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Any, Dict

try:
    import yaml
    YAML_IMPORT_ERROR = ""
except Exception as e:
    yaml = None
    YAML_IMPORT_ERROR = str(e)

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
        os.path.join(script_dir, "..", "pcloud-tools", "main", "pcloud_bin_lib.py"),
        os.path.join(script_dir, "..", "pcloud-tools", "pcloud_bin_lib.py"),
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
from textual.theme import Theme
from textual.widgets import Header, Footer, Static, DirectoryTree, Label, Tree, OptionList
from textual.widgets.option_list import Option
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button
from rich.text import Text


DEFAULT_DOWNLOAD_DIR = "/srv/nas/restore"


class RobustDirectoryTree(DirectoryTree):
    """DirectoryTree that follows symlinks and never silently skips paths."""

    def filter_paths(self, paths):
        return paths

    def _get_entries(self, location):
        try:
            entries = sorted(location.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for entry in entries:
            try:
                entry.stat()
                yield entry
            except OSError:
                continue


# ==================== Theme System ====================

@dataclass
class Palette:
    """Central color palette.  Feeds Textual's Theme + our minimal custom CSS."""
    name: str
    # Core semantic colors (→ Theme fields)
    primary: str          # accent/highlight color (borders, active elements)
    secondary: str        # secondary accent
    accent: str           # cursor / selection accent
    background: str       # screen background
    surface: str          # widget background
    panel: str            # header/footer/label strips
    foreground: str       # primary text
    error: str
    success: str
    # Extended tokens (→ Theme.variables + custom CSS)
    text_muted: str       # inactive labels
    text_dim: str         # guide lines, status bar
    accent_fg: str        # text ON accent/cursor background
    accent_dim: str       # cursor when tree NOT focused
    border: str           # inactive pane border
    overlay: str          # modal background
    folder: str           # folder name color
    file: str             # file name color


PALETTES: dict[str, Palette] = {
    # ── Posting: dark navy, violet accents, teal cursor ──────────
    "posting": Palette(
        name="posting",
        primary="#7c6af7",
        secondary="#1a6b7c",
        accent="#1a6b7c",
        background="#0f111a",
        surface="#0f111a",
        panel="#1a1b2e",
        foreground="#c5c8d8",
        error="#c0392b",
        success="#26a96c",
        text_muted="#555873",
        text_dim="#30334a",
        accent_fg="#e0f4f8",
        accent_dim="#0d3d47",
        border="#2a2c40",
        overlay="#141626",
        folder="#7c6af7",
        file="#c5c8d8",
    ),
    # ── Hacker: terminal green on black ──────────────────────────
    "hacker": Palette(
        name="hacker",
        primary="#00ff41",
        secondary="#00cc33",
        accent="#00ff41",
        background="#000000",
        surface="#000000",
        panel="#0a0a0a",
        foreground="#00cc33",
        error="#ff0000",
        success="#00ff41",
        text_muted="#006614",
        text_dim="#003308",
        accent_fg="#000000",
        accent_dim="#00aa2b",
        border="#1a3a1a",
        overlay="#050505",
        folder="#00cc33",
        file="#009922",
    ),
    # ── Calm: muted blue-grey ────────────────────────────────────
    "calm": Palette(
        name="calm",
        primary="#6c91bf",
        secondary="#b083ea",
        accent="#6c91bf",
        background="#1c1e26",
        surface="#232530",
        panel="#2a2c3a",
        foreground="#a8aebb",
        error="#fc4b5f",
        success="#3fc56b",
        text_muted="#5c6270",
        text_dim="#3a3c4e",
        accent_fg="#1c1e26",
        accent_dim="#3d5a80",
        border="#3a3c4e",
        overlay="#1c1e26",
        folder="#b083ea",
        file="#59c6ab",
    ),
    # ── Amber: warm terminal (amber + rust) ─────────────────────
    "amber": Palette(
        name="amber",
        primary="#ffb347",
        secondary="#d27d2d",
        accent="#ffb347",
        background="#17120b",
        surface="#1f170f",
        panel="#2a1f14",
        foreground="#f6e1c6",
        error="#d1492e",
        success="#4aa564",
        text_muted="#b48f6a",
        text_dim="#7f6248",
        accent_fg="#2a1b0f",
        accent_dim="#7b5a35",
        border="#5c432e",
        overlay="#23180f",
        folder="#ffb347",
        file="#f6e1c6",
    ),
    # ── Ocean: deep blue with cyan highlights ───────────────────
    "ocean": Palette(
        name="ocean",
        primary="#4db6ff",
        secondary="#2b7fb9",
        accent="#2ea8c9",
        background="#0c1a24",
        surface="#102231",
        panel="#163043",
        foreground="#cbe5f7",
        error="#d85d67",
        success="#36b37e",
        text_muted="#7aa0bc",
        text_dim="#4f6d84",
        accent_fg="#e8f7ff",
        accent_dim="#1d4f67",
        border="#2a4e67",
        overlay="#132838",
        folder="#63c8ff",
        file="#cbe5f7",
    ),
    # ── Graphite: neutral monochrome focus theme ─────────────────
    "graphite": Palette(
        name="graphite",
        primary="#9aa3ad",
        secondary="#6f7b86",
        accent="#7f8b96",
        background="#14171b",
        surface="#1a1f24",
        panel="#20262d",
        foreground="#d6dde5",
        error="#c45757",
        success="#66a97a",
        text_muted="#8e99a4",
        text_dim="#5e6872",
        accent_fg="#f4f7fa",
        accent_dim="#3b454f",
        border="#3e4954",
        overlay="#1b2026",
        folder="#b8c0c8",
        file="#d6dde5",
    ),
}

DEFAULT_PALETTE = "posting"


def build_theme(p: Palette) -> Theme:
    """Create a Textual Theme from our Palette.

    The `variables` dict lets us override the auto-generated CSS
    variables for cursor, hover, scrollbar, etc.
    """
    return Theme(
        name=p.name,
        primary=p.primary,
        secondary=p.secondary,
        accent=p.accent,
        background=p.background,
        surface=p.surface,
        panel=p.panel,
        foreground=p.foreground,
        error=p.error,
        success=p.success,
        dark=True,
        luminosity_spread=0.15,
        text_alpha=0.95,
        variables={
            # Cursor (focused)
            "block-cursor-foreground": p.accent_fg,
            "block-cursor-background": p.accent,
            "block-cursor-text-style": "bold",
            # Cursor (blurred / unfocused pane)
            "block-cursor-blurred-foreground": p.accent_fg,
            "block-cursor-blurred-background": p.accent_dim,
            "block-cursor-blurred-text-style": "none",
            # Hover
            "block-hover-background": p.panel,
            # Border
            "border": p.border,
            "border-blurred": p.border,
            # Footer
            "footer-background": p.panel,
            "footer-foreground": p.foreground,
            "footer-key-background": p.primary,
            "footer-key-foreground": p.accent_fg,
            # Scrollbar
            "scrollbar": p.text_dim,
            "scrollbar-background": p.surface,
            "scrollbar-hover": p.text_muted,
            "scrollbar-active": p.primary,
        },
    )


CUSTOM_CSS = """
    /* ── Panes ───────────────────────────────────────────────────── */
    #left-pane, #right-pane {
        width: 1fr;
        height: 1fr;
        border: solid $border-blurred;
    }
    #left-pane.active-pane, #right-pane.active-pane {
        border: double $primary;
    }

    /* ── Panel labels (pane headers) ─────────────────────────────── */
    .panel-label {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
        text-style: bold;
    }
    .active-pane .panel-label {
        color: $primary;
    }

    /* ── Folder/file colors in DirectoryTree ──────────────────────── */
    DirectoryTree .directory-tree--folder {
        color: $primary;
        text-style: bold;
    }
    DirectoryTree .directory-tree--file {
        color: $foreground;
    }

    /* ── Path bar ─────────────────────────────────────────────────── */
    #path-bar {
        height: 1;
        background: $panel;
        color: $primary;
        padding: 0 1;
        text-style: bold;
    }

    /* ── Status bar ───────────────────────────────────────────────── */
    #status-bar {
        height: 1;
        background: $panel;
        color: $text-disabled;
        padding: 0 1;
    }

    /* ── Modals ───────────────────────────────────────────────────── */
    ActionMenu, ConfirmModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }
    #menu-box, #confirm-box {
        width: 60;
        height: auto;
        border: double $primary;
        background: $surface;
        padding: 1 2;
    }
    #menu-title, #confirm-msg {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    /* ── Buttons ──────────────────────────────────────────────────── */
    #menu-buttons, #confirm-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }
    Button {
        margin: 0 2;
        text-style: bold;
    }
    #btn-run, #btn-yes {
        background: $success;
    }
    #btn-cancel, #btn-no {
        background: $error;
    }
    """


# ==================== Modal Screens ====================

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
        self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
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


# ==================== Main App ====================

class PCloudCommander(App):
    """pCloud Commander TUI."""

    TITLE = "pCloud Commander"
    SUB_TITLE = "Interactive Dual-Pane Browser"

    CSS = CUSTOM_CSS

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

    def __init__(self, cfg_overrides=None, local_root: str = "/srv",
                 palette_name: str = DEFAULT_PALETTE):
        super().__init__()
        self.env_file = find_env_file()
        self.cfg = pc.effective_config(env_file=self.env_file, overrides=cfg_overrides)
        self.local_root = local_root if Path(local_root).exists() else "/"
        self.active_pane = "right"
        self.download_dir = DEFAULT_DOWNLOAD_DIR
        self._palette_name = palette_name
        self.palette = PALETTES.get(palette_name, PALETTES[DEFAULT_PALETTE])
        self.script_catalog_error = ""
        self.script_catalog = self._load_external_script_catalog()

        # Register ALL palettes and activate the selected one immediately
        for name, pal in PALETTES.items():
            self.register_theme(build_theme(pal))
        # KEY FIX: Set theme in __init__, not on_mount — ensures CSS
        # variables are resolved from OUR theme before first render.
        self.theme = self._palette_name

    def on_mount(self) -> None:
        if self.script_catalog_error:
            self.notify(f"scripts.yaml unavailable: {self.script_catalog_error}", severity="warning", timeout=8)
        self._apply_pane_focus()
        self.call_after_refresh(self._init_pcloud_tree)

    # ── Compose ──────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="path-bar")
        yield Horizontal(
            Vertical(
                Label(f"📁 Local: {self.local_root}", classes="panel-label"),
                RobustDirectoryTree(self.local_root),
                id="left-pane",
            ),
            Vertical(
                Label("☁  pCloud: /", classes="panel-label", id="pcloud-label"),
                Tree(self._folder_label("/"), id="pcloud-tree"),
                id="right-pane",
            ),
        )
        yield Static(f"Lib: {pc_path} | Env: {self.env_file}", id="status-bar")
        yield Footer()

    # ── pCloud tree ──────────────────────────────────────────────

    def _init_pcloud_tree(self) -> None:
        tree = self.query_one("#pcloud-tree", Tree)
        tree.root.set_label(self._folder_label("/"))
        tree.root.data = {"id": 0, "is_folder": True, "name": "", "loaded": False}
        self._load_tree_node(tree.root, 0)
        tree.root.expand()

    def _folder_label(self, name: str) -> Text:
        label = Text("📁 ", style=f"bold {self.palette.folder}")
        label.append(name, style=f"bold {self.palette.folder}")
        return label

    def _file_label(self, name: str, size_str: str) -> Text:
        label = Text("📄 ", style=self.palette.file)
        label.append(name, style=self.palette.file)
        label.append(f"  [{size_str}]", style=self.palette.text_muted)
        return label

    def _load_tree_node(self, node, folderid: int) -> None:
        try:
            res = pc.listfolder(self.cfg, folderid=folderid)
            if res.get("result") == 0:
                contents = res.get("metadata", {}).get("contents", [])
                for item in sorted(contents, key=lambda x: (not x["isfolder"], x["name"].lower())):
                    if item["isfolder"]:
                        child = node.add(
                            self._folder_label(item["name"]),
                            data={"id": item["folderid"], "is_folder": True,
                                  "name": item["name"], "loaded": False},
                        )
                        child.add_leaf("⋯", data=None)
                    else:
                        size_str = self._format_size(item["size"])
                        node.add_leaf(
                            self._file_label(item["name"], size_str),
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
        parts = []
        n = node
        while n and n.parent is not None:
            if n.data and n.data.get("name"):
                parts.append(n.data["name"])
            n = n.parent
        return "/" if not parts else "/" + "/".join(reversed(parts)) + "/"

    # ── Pane focus ───────────────────────────────────────────────

    def _apply_pane_focus(self) -> None:
        left = self.query_one("#left-pane")
        right = self.query_one("#right-pane")
        if self.active_pane == "left":
            left.add_class("active-pane")
            right.remove_class("active-pane")
            self.query_one(RobustDirectoryTree).focus()
        else:
            right.add_class("active-pane")
            left.remove_class("active-pane")
            self.query_one("#pcloud-tree", Tree).focus()

    def action_switch_pane(self) -> None:
        self.active_pane = "left" if self.active_pane == "right" else "right"
        self._apply_pane_focus()

    # ── Refresh ──────────────────────────────────────────────────

    def refresh_list(self):
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

    # ── Tree events ──────────────────────────────────────────────

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        if node.data and not node.data.get("loaded") and node.data.get("is_folder"):
            node.remove_children()
            self._load_tree_node(node, node.data["id"])

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if event.control.id == "pcloud-tree":
            node = event.node
            if node and node.data and isinstance(node.data, dict):
                p_str = self._node_path_str(node)
                self.query_one("#path-bar", Static).update(f"pCloud: {p_str}")
                self.query_one("#pcloud-label", Label).update(f"☁  pCloud: {p_str}")
        elif isinstance(event.control, RobustDirectoryTree):
            if event.node and event.node.data:
                p_obj = getattr(event.node.data, "path", event.node.data)
                self.query_one("#path-bar", Static).update(f"Local: {p_obj}")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.notify(f"📄 {event.path.name}  │  a=actions", severity="information")

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self.query_one("#path-bar", Static).update(f"Local: {event.path}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        if node.data and not node.data.get("is_folder"):
            name = node.data.get("name", "")
            size = self._format_size(node.data.get("size", 0))
            self.notify(f"📄 {name}  {size}  │  d=download  F8=delete", severity="information")

    # ── Actions ──────────────────────────────────────────────────

    def _load_external_script_catalog(self) -> List[Dict[str, Any]]:
        """Load script definitions from script-manager-ui YAML in read-only mode."""
        if yaml is None:
            self.script_catalog_error = f"PyYAML missing ({YAML_IMPORT_ERROR or 'import failed'})"
            return []

        script_dir = Path(__file__).resolve().parent
        candidates = [
            script_dir.parent / "script-manager-ui" / "scripts.yaml",
            Path("/opt/apps/script-manager-ui/scripts.yaml"),
        ]

        for path in candidates:
            try:
                if not path.exists():
                    continue
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                scripts = data.get("scripts", [])
                if isinstance(scripts, list):
                    if not scripts:
                        self.script_catalog_error = f"{path}: no scripts entries"
                        return []
                    self.script_catalog_error = ""
                    return [s for s in scripts if isinstance(s, dict) and s.get("name") and s.get("cmd")]
            except Exception as e:
                self.script_catalog_error = f"{path}: {e}"
                continue
        if not self.script_catalog_error:
            self.script_catalog_error = "scripts.yaml not found"
        return []

    def _load_env_file_vars(self, env_file_path: Path) -> Dict[str, str]:
        vars_out: Dict[str, str] = {}
        try:
            for raw in env_file_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                vars_out[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            return {}
        return vars_out

    def _current_pcloud_target(self) -> tuple[int, str]:
        """Return currently selected pCloud folder id + path string for autofill."""
        tree = self.query_one("#pcloud-tree", Tree)
        node = tree.cursor_node or tree.root
        if node and node.data:
            if node.data.get("is_folder"):
                return node.data.get("id", 0), self._node_path_str(node)
            if node.parent and node.parent.data:
                return node.parent.data.get("id", 0), self._node_path_str(node.parent)
        return 0, "/"

    def _build_script_command(
        self,
        script: Dict[str, Any],
        local_sel: Optional[str],
        pcloud_folderid: int,
        pcloud_path: str,
    ) -> List[str]:
        def flag_for(name: str) -> str:
            """Map YAML param names to argparse-style CLI flags."""
            return f"--{name.replace('_', '-')}"

        cmd = [str(script.get("cmd"))] + [str(a) for a in script.get("args", [])]
        params = script.get("params", []) or []

        for param in params:
            if not isinstance(param, dict) or param.get("ui_only"):
                continue

            name = str(param.get("name", "")).strip()
            if not name:
                continue

            p_type = str(param.get("type", "string"))
            arg_mode = str(param.get("arg_mode", "flag"))
            value = param.get("default")
            lname = name.lower()

            # Local path autofill for common source-like parameter names.
            if p_type in {"path", "string"}:
                if any(k in lname for k in ["local", "source", "src"]) and local_sel:
                    value = local_sel
                elif lname in {"src", "source", "local_path", "local-path"} and not value:
                    value = local_sel or self.local_root

            # pCloud autofill for common remote-like parameter names.
            if p_type in {"path", "string", "int"}:
                if any(k in lname for k in ["folderid", "dst-id", "dst_id", "remote_id"]):
                    value = pcloud_folderid
                elif any(k in lname for k in ["remote_path", "pcloud_path", "dst_path", "target_path", "destination"]) and not value:
                    value = pcloud_path

            if p_type == "bool":
                if bool(value):
                    cmd.append(flag_for(name))
                continue

            if value in (None, ""):
                continue

            if arg_mode == "positional":
                cmd.append(str(value))
            else:
                cmd.extend([flag_for(name), str(value)])

        return cmd

    def _run_catalog_script(
        self,
        script: Dict[str, Any],
        local_sel: Optional[str],
        pcloud_folderid: int,
        pcloud_path: str,
    ) -> None:
        script_name = str(script.get("name", "Unnamed Script"))
        cwd = str(script.get("cwd") or ".")

        try:
            cmd = self._build_script_command(script, local_sel, pcloud_folderid, pcloud_path)
        except Exception as e:
            self.notify(f"Cannot build command for {script_name}: {e}", severity="error")
            return

        env = os.environ.copy()

        env_file = script.get("env_file")
        if env_file:
            env_path = Path(cwd) / str(env_file)
            env_vars = self._load_env_file_vars(env_path)
            if "PATH" in env_vars:
                env_vars["PATH"] = f"{env_vars['PATH']}:{env.get('PATH', '')}"
            if "PYTHONPATH" in env_vars:
                env_vars["PYTHONPATH"] = f"{env_vars['PYTHONPATH']}:{env.get('PYTHONPATH', '')}"
            env.update(env_vars)

        inline_env = script.get("env", {}) or {}
        if isinstance(inline_env, dict):
            if "PATH" in inline_env:
                inline_env["PATH"] = f"{inline_env['PATH']}:{env.get('PATH', '')}"
            if "PYTHONPATH" in inline_env:
                inline_env["PYTHONPATH"] = f"{inline_env['PYTHONPATH']}:{env.get('PYTHONPATH', '')}"
            env.update({str(k): str(v) for k, v in inline_env.items()})

        def run_in_suspend():
            with self.suspend():
                print(f"\n>>> Running catalog script: {script_name}\n")
                print(f">>> CWD: {cwd}\n")
                print(f">>> CMD: {' '.join(cmd)}\n")
                subprocess.run(cmd, cwd=cwd, env=env)
                input("\nPress Enter to return to Commander...")
            self.refresh_list()

        run_in_suspend()

    def _get_selected_row(self):
        tree = self.query_one("#pcloud-tree", Tree)
        node = tree.cursor_node
        if node is None or node.data is None:
            return None, None, None
        d = node.data
        return d.get("name"), d.get("id"), d.get("is_folder", False)

    def action_launch(self) -> None:
        actions = []

        local_sel = None
        if self.active_pane == "left":
            tree = self.query_one(RobustDirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                local_sel = str(tree.cursor_node.data.path)

        pcloud_name, pcloud_id, pcloud_is_folder = self._get_selected_row()

        target_folderid = 0
        tree = self.query_one("#pcloud-tree", Tree)
        if tree.cursor_node and tree.cursor_node.data:
            if pcloud_is_folder:
                target_folderid = pcloud_id
            elif tree.cursor_node.parent and tree.cursor_node.parent.data:
                target_folderid = tree.cursor_node.parent.data.get("id", 0)

        actions.append(("Refresh pCloud List", "refresh"))

        if local_sel:
            path_obj = Path(local_sel)
            if path_obj.is_file():
                actions.append((f"Upload to pCloud: {path_obj.name}", f"upload_file:{local_sel}:{target_folderid}"))
            elif path_obj.is_dir():
                actions.append((f"Sync Folder to pCloud: {path_obj.name}", f"sync_dir:{local_sel}:{target_folderid}"))

        if pcloud_name and not pcloud_is_folder:
            actions.append((f"Download from pCloud: {pcloud_name}", "download"))

        pcloud_target_id, pcloud_target_path = self._current_pcloud_target()

        if self.script_catalog:
            for idx, script in enumerate(self.script_catalog):
                script_name = script.get("name") or f"Script {idx + 1}"
                label = f"Run Script: {script_name}"
                actions.append((label, f"yaml_script:{idx}"))
        else:
            detail = self.script_catalog_error or "no catalog"
            actions.append((f"(No scripts catalog: {detail[:36]})", "noop"))

        def _on_action(cmd_key: Optional[str]) -> None:
            if not cmd_key:
                return
            if cmd_key == "refresh":
                self.refresh_list()
            elif cmd_key == "download":
                self.action_download()
            elif cmd_key == "noop":
                self.notify(
                    f"No external scripts catalog available: {self.script_catalog_error or 'unknown reason'}",
                    severity="warning",
                    timeout=8,
                )
            elif cmd_key.startswith("upload_file:"):
                _, local_path, fid = cmd_key.split(":", 2)
                self._run_tool("pcloud_simple_upload.py", [local_path, fid])
            elif cmd_key.startswith("sync_dir:"):
                _, local_path, fid = cmd_key.split(":", 2)
                self._run_tool("pcloud_quick_delta.py", ["--src", local_path, "--dst-id", fid])
            elif cmd_key.startswith("yaml_script:"):
                _, idx_text = cmd_key.split(":", 1)
                idx = int(idx_text)
                if 0 <= idx < len(self.script_catalog):
                    self._run_catalog_script(
                        self.script_catalog[idx],
                        local_sel=local_sel,
                        pcloud_folderid=pcloud_target_id,
                        pcloud_path=pcloud_target_path,
                    )
                else:
                    self.notify("Invalid script selection.", severity="error")

        self.push_screen(ActionMenu(actions), _on_action)

    def _run_tool(self, script_name: str, args: List[str]):
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
        if self.active_pane == "right":
            tree = self.query_one("#pcloud-tree", Tree)
            node = tree.cursor_node
            if node and node.parent is not None and node.parent.parent is not None:
                if node.is_expanded:
                    node.collapse()
                tree.move_cursor(node.parent)
            elif node and node.parent is not None and node.parent.parent is None:
                self.notify("Already at root.", severity="warning")

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
    parser.add_argument("--local-root", default="/srv",
                        help="Local directory to browse (default: /srv)")
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