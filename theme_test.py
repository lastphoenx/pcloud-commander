#!/usr/bin/env python3
"""Minimal theme test for Textual theme activation on the target host."""

from textual.app import App, ComposeResult
from textual.theme import Theme
from textual.widgets import Header, Footer, Static, Tree


class ThemeTest(App):
    CSS = """
    #info {
        height: 3;
        background: $primary;
        color: $background;
        padding: 1;
        text-style: bold;
    }
    #box {
        height: 3;
        background: $panel;
        color: $foreground;
        padding: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.register_theme(
            Theme(
                name="violet-test",
                primary="#7c6af7",
                secondary="#1a6b7c",
                accent="#1a6b7c",
                background="#0f111a",
                surface="#0f111a",
                panel="#1a1b2e",
                foreground="#c5c8d8",
                error="#c0392b",
                success="#26a96c",
                dark=True,
            )
        )
        self.theme = "violet-test"

        # Debug output in stdout for SSH/session logs.
        print(f"[DEBUG] theme after set: {self.theme}")
        print(f"[DEBUG] current_theme.name: {self.current_theme.name}")
        print(f"[DEBUG] current_theme.primary: {self.current_theme.primary}")
        print(f"[DEBUG] available: {list(self.available_themes.keys())}")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Theme: violet-test | Primary should be VIOLET #7c6af7",
            id="info",
        )
        yield Static(
            "If this bar is CYAN, the theme is NOT active.",
            id="box",
        )
        yield Tree("Test Tree", id="tree")
        yield Footer()

    def on_mount(self):
        tree = self.query_one("#tree", Tree)
        tree.root.add("Folder A")
        tree.root.add("Folder B")
        tree.root.add_leaf("file.txt")
        tree.root.expand()


if __name__ == "__main__":
    ThemeTest().run()
