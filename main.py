#!/usr/bin/env python3
"""folio: terminal-native epub editor."""

import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen, ModalScreen
from textual.theme import BUILTIN_THEMES
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Rule,
    Static,
)
from textual import work

from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box

from epub_core import EpubEditor, EpubMetadata

THEME_NAMES: list[str] = list(BUILTIN_THEMES.keys())

LOGO = """
[bold cyan]  ╔═╗╔═╗╦  ╦╔═╗[/bold cyan]
[bold cyan]  ╠╣ ║ ║║  ║║ ║[/bold cyan]
[bold cyan]  ╩  ╚═╝╩═╝╩╚═╝[/bold cyan]
[dim]  epub editor · terminal-native[/dim]
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def direction_badge(d: str) -> Text:
    if d == "rtl":
        return Text("⟵ RTL", style="bold magenta")
    return Text("⟶ LTR", style="bold cyan")


# ══════════════════════════════════════════════════════════════════════════════
#  Modal: Confirm dialog
# ══════════════════════════════════════════════════════════════════════════════

class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #dialog Label { margin-bottom: 1; }
    #btn-row { align: center middle; height: auto; }
    #btn-row Button { margin: 0 1; }
    """

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(self.message)
            with Horizontal(id="btn-row"):
                yield Button("Yes", variant="success", id="yes")
                yield Button("No", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


# ══════════════════════════════════════════════════════════════════════════════
#  Modal: Edit metadata
# ══════════════════════════════════════════════════════════════════════════════

class MetadataScreen(ModalScreen[dict | None]):
    CSS = """
    MetadataScreen {
        align: center middle;
    }
    #meta-dialog {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #meta-dialog Label { margin-top: 1; color: $text-muted; }
    #meta-dialog Input { margin-bottom: 0; }
    #meta-btn-row { align: center middle; height: auto; margin-top: 1; }
    #meta-btn-row Button { margin: 0 1; }
    """

    def __init__(self, meta: EpubMetadata):
        super().__init__()
        self.meta = meta

    def compose(self) -> ComposeResult:
        with Container(id="meta-dialog"):
            yield Static("[bold]Edit Metadata[/bold]", markup=True)
            yield Rule()
            yield Label("Title")
            yield Input(value=self.meta.title, id="m-title", placeholder="Book title")
            yield Label("Author")
            yield Input(value=self.meta.author, id="m-author", placeholder="Author name")
            yield Label("Language (BCP-47, e.g. en, ar, he)")
            yield Input(value=self.meta.language, id="m-lang", placeholder="en")
            yield Label("Publisher")
            yield Input(value=self.meta.publisher, id="m-publisher", placeholder="Publisher")
            yield Label("Description")
            yield Input(value=self.meta.description, id="m-desc", placeholder="Short description")
            with Horizontal(id="meta-btn-row"):
                yield Button("Save", variant="success", id="meta-save")
                yield Button("Cancel", variant="default", id="meta-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "meta-save":
            self.dismiss({
                "title": self.query_one("#m-title", Input).value,
                "author": self.query_one("#m-author", Input).value,
                "language": self.query_one("#m-lang", Input).value,
                "publisher": self.query_one("#m-publisher", Input).value,
                "description": self.query_one("#m-desc", Input).value,
            })
        else:
            self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  Modal: File path input
# ══════════════════════════════════════════════════════════════════════════════

class FilePathScreen(ModalScreen[str | None]):
    CSS = """
    FilePathScreen {
        align: center middle;
    }
    #fp-dialog {
        width: 70;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #fp-dialog Label { margin-bottom: 1; }
    #fp-btn-row { align: center middle; height: auto; margin-top: 1; }
    #fp-btn-row Button { margin: 0 1; }
    """

    def __init__(self, title: str, placeholder: str = ""):
        super().__init__()
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Container(id="fp-dialog"):
            yield Static(f"[bold]{self._title}[/bold]", markup=True)
            yield Rule()
            yield Label("Path:")
            yield Input(id="fp-input", placeholder=self._placeholder)
            with Horizontal(id="fp-btn-row"):
                yield Button("OK", variant="success", id="fp-ok")
                yield Button("Cancel", variant="default", id="fp-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "fp-ok":
            val = self.query_one("#fp-input", Input).value.strip()
            self.dismiss(val if val else None)
        else:
            self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  Modal: Theme selector
# ══════════════════════════════════════════════════════════════════════════════

class ThemeScreen(ModalScreen[str | None]):
    CSS = """
    ThemeScreen { align: center middle; }
    #theme-dialog {
        width: 40;
        height: auto;
        max-height: 40;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #theme-list {
        height: auto;
        max-height: 24;
        border: solid $primary-darken-2;
        margin: 1 0 0 0;
        background: $surface-darken-1;
    }
    #theme-list > ListItem { padding: 0 1; }
    #theme-list > ListItem.--highlight { background: $primary; color: $text; }
    #theme-hint {
        color: $text-muted;
        text-align: center;
        height: 1;
        margin-top: 0;
    }
    #theme-btn-row { align: center middle; height: 3; }
    #theme-btn-row Button { margin: 0 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self):
        super().__init__()
        self._original_theme: str = ""

    def compose(self) -> ComposeResult:
        with Container(id="theme-dialog"):
            yield Static("[bold]Select Theme[/bold]", markup=True)
            yield Rule()
            yield ListView(id="theme-list")
            yield Static(
                "[dim]↑↓[/dim]=preview  [dim]Enter[/dim]=confirm  [dim]Esc[/dim]=cancel",
                id="theme-hint",
                markup=True,
            )
            with Horizontal(id="theme-btn-row"):
                yield Button("Confirm", variant="success", id="theme-confirm")
                yield Button("Cancel", variant="default", id="theme-cancel")

    def on_mount(self):
        self._original_theme = self.app.theme
        lv = self.query_one("#theme-list", ListView)
        for name in THEME_NAMES:
            marker = " ✓" if name == self._original_theme else ""
            lv.append(ListItem(Label(name + marker)))

        if self._original_theme in THEME_NAMES:
            idx = THEME_NAMES.index(self._original_theme)
            # Scroll to and highlight current theme after items are mounted
            self.call_after_refresh(lambda: setattr(lv, "index", idx))

    def on_list_view_highlighted(self, event: ListView.Highlighted):
        if event.list_view.id == "theme-list" and event.list_view.index is not None:
            idx = event.list_view.index
            if 0 <= idx < len(THEME_NAMES):
                self.app.theme = THEME_NAMES[idx]

    def on_list_view_selected(self, event: ListView.Selected):
        if event.list_view.id == "theme-list":
            self.dismiss(self.app.theme)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "theme-confirm":
            self.dismiss(self.app.theme)
        elif event.button.id == "theme-cancel":
            self.app.theme = self._original_theme
            self.dismiss(None)

    def action_cancel(self):
        self.app.theme = self._original_theme
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  Modal: File browser
# ══════════════════════════════════════════════════════════════════════════════

class FileBrowserScreen(ModalScreen[str | None]):
    CSS = """
    FileBrowserScreen { align: center middle; }
    #browser-dialog {
        width: 74;
        height: 32;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #browser-path {
        color: $accent;
        text-align: center;
        height: 1;
        margin-bottom: 0;
    }
    #browser-list {
        height: 1fr;
        border: solid $primary-darken-2;
        margin: 1 0 0 0;
        background: $surface-darken-1;
    }
    #browser-list > ListItem { padding: 0 1; }
    #browser-list > ListItem.--highlight { background: $primary; color: $text; }
    #browser-hint {
        color: $text-muted;
        height: 1;
        text-align: center;
        margin-top: 0;
    }
    #br-btn-row { align: center middle; height: 3; }
    #br-btn-row Button { margin: 0 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("backspace", "go_up", "Parent dir"),
        Binding("left", "go_up", "Parent dir", show=False),
    ]

    def __init__(self, start_dir: Path | None = None):
        super().__init__()
        self._cwd: Path = (start_dir or Path.cwd()).resolve()
        self._entries: list[tuple[str, Path]] = []

    def compose(self) -> ComposeResult:
        with Container(id="browser-dialog"):
            yield Static("", id="browser-path")
            yield Rule()
            yield ListView(id="browser-list")
            yield Static(
                "[dim]Enter[/dim]=open  [dim]Backspace/←[/dim]=parent  [dim]Esc[/dim]=cancel",
                id="browser-hint",
                markup=True,
            )
            with Horizontal(id="br-btn-row"):
                yield Button("Open", variant="primary", id="br-open")
                yield Button("Cancel", variant="default", id="br-cancel")

    def on_mount(self):
        self._do_populate(self._cwd)

    @work(exclusive=True)
    async def _do_populate(self, directory: Path):
        self._cwd = directory
        self.query_one("#browser-path", Static).update(f"📁  {directory}")

        lv = self.query_one("#browser-list", ListView)
        await lv.clear()

        self._entries = []
        items: list[ListItem] = []

        # Parent dir entry
        if directory.parent != directory:
            self._entries.append(("up", directory.parent))
            t = Text("↑  ..", style="bold yellow")
            items.append(ListItem(Label(t)))

        try:
            all_children = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
            dirs = [p for p in all_children if p.is_dir() and not p.name.startswith(".")]
            epubs = [p for p in all_children if p.is_file() and p.suffix.lower() == ".epub"]

            for d in dirs:
                self._entries.append(("dir", d))
                t = Text(f"📁  {d.name}/")
                items.append(ListItem(Label(t)))

            for e in epubs:
                size = fmt_size(e.stat().st_size)
                t = Text(f"📖  {e.name}")
                t.append(f"  {size}", style="dim")
                self._entries.append(("epub", e))
                items.append(ListItem(Label(t)))

        except PermissionError:
            items.append(ListItem(Label("[red]  Permission denied[/red]", markup=True)))

        if not items:
            items.append(ListItem(Label("[dim]  (empty directory)[/dim]", markup=True)))

        await lv.mount(*items)

    def on_list_view_selected(self, event: ListView.Selected):
        idx = event.list_view.index
        if idx is None or idx >= len(self._entries):
            return
        kind, path = self._entries[idx]
        if kind in ("up", "dir"):
            self._do_populate(path)
        elif kind == "epub":
            self.dismiss(str(path))

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "br-cancel":
            self.dismiss(None)
        elif event.button.id == "br-open":
            lv = self.query_one("#browser-list", ListView)
            idx = lv.index
            if idx is not None and idx < len(self._entries):
                kind, path = self._entries[idx]
                if kind == "epub":
                    self.dismiss(str(path))

    def action_cancel(self):
        self.dismiss(None)

    def action_go_up(self):
        if self._cwd.parent != self._cwd:
            self._do_populate(self._cwd.parent)


# ══════════════════════════════════════════════════════════════════════════════
#  Welcome screen
# ══════════════════════════════════════════════════════════════════════════════

class WelcomeScreen(Screen):
    CSS = """
    WelcomeScreen {
        align: center middle;
        background: $background;
    }
    #welcome-box {
        width: 66;
        height: auto;
        border: double $primary;
        background: $surface;
        padding: 1 2;
    }
    #logo { text-align: center; margin-bottom: 1; }
    #local-label { color: $text-muted; margin-top: 1; margin-bottom: 0; height: 1; }
    #local-list {
        height: auto;
        max-height: 7;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
        margin-bottom: 1;
    }
    #local-list > ListItem { padding: 0 1; }
    #local-list > ListItem.--highlight { background: $primary; color: $text; }
    #manual-label { color: $text-muted; margin-top: 0; margin-bottom: 0; height: 1; }
    #path-row { height: 3; margin-top: 0; }
    #path-input { width: 1fr; }
    #browse-btn { width: 12; margin-left: 1; }
    #open-btn { margin-top: 1; width: 100%; }
    #err-label { color: $error; height: 1; margin-top: 0; }
    """

    BINDINGS = [
        Binding("escape", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._local_epubs: list[str] = []

    def compose(self) -> ComposeResult:
        with Container(id="welcome-box"):
            yield Static(LOGO, id="logo", markup=True)
            yield Rule()
            yield Label("", id="local-label")
            yield ListView(id="local-list")
            yield Rule()
            yield Label("Or enter path manually:", id="manual-label")
            with Horizontal(id="path-row"):
                yield Input(id="path-input", placeholder="/path/to/book.epub")
                yield Button("Browse…", id="browse-btn")
            yield Button("Open", variant="primary", id="open-btn")
            yield Label("", id="err-label")
        yield Footer()

    def on_mount(self):
        self._scan_local_epubs()

    def _scan_local_epubs(self):
        cwd = Path.cwd()
        epubs = sorted(cwd.glob("*.epub"), key=lambda p: p.name.lower())
        label = self.query_one("#local-label", Label)
        lv = self.query_one("#local-list", ListView)

        if epubs:
            label.update(f"EPUBs in [cyan]{cwd}[/cyan]:")
            self._local_epubs = [str(e) for e in epubs]
            for epub in epubs:
                size = fmt_size(epub.stat().st_size)
                t = Text(f"📖  {epub.name}")
                t.append(f"  {size}", style="dim")
                lv.append(ListItem(Label(t)))
        else:
            label.update(f"No EPUBs found in [cyan]{cwd}[/cyan]")
            lv.append(ListItem(Label(Text("  (none)", style="dim"))))
            self._local_epubs = []

    def on_list_view_selected(self, event: ListView.Selected):
        if event.list_view.id == "local-list":
            idx = event.list_view.index
            if idx is not None and 0 <= idx < len(self._local_epubs):
                self._open_epub(self._local_epubs[idx])

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "open-btn":
            self._try_open_manual()
        elif event.button.id == "browse-btn":
            self.app.push_screen(FileBrowserScreen(), self._on_browse_result)

    def _on_browse_result(self, path: str | None):
        if path:
            self._open_epub(path)

    def on_input_submitted(self, event: Input.Submitted):
        self._try_open_manual()

    def _try_open_manual(self):
        path = self.query_one("#path-input", Input).value.strip()
        err = self.query_one("#err-label", Label)
        if not path:
            err.update("[red]Please enter a file path.[/red]")
            return
        p = Path(path).expanduser().resolve()
        if not p.exists():
            err.update(f"[red]File not found: {p}[/red]")
            return
        if p.suffix.lower() != ".epub":
            err.update("[red]File does not appear to be an EPUB.[/red]")
            return
        err.update("")
        self._open_epub(str(p))

    def _open_epub(self, path: str):
        self.app.push_screen(EditorScreen(path))

    def action_quit(self):
        self.app.exit()


# ══════════════════════════════════════════════════════════════════════════════
#  Main editor screen
# ══════════════════════════════════════════════════════════════════════════════

class InfoPanel(Static):
    """Displays EPUB metadata and stats."""

    def update_meta(self, editor: EpubEditor):
        m = editor.metadata
        t = Table.grid(padding=(0, 1))
        t.add_column(style="bold cyan", min_width=14)
        t.add_column()

        def row(label, val):
            t.add_row(label, str(val) if val else "[dim]—[/dim]")

        # Title: display RTL with bidi mark + right-align when direction is RTL
        raw_title = m.title or "Unknown"
        if m.direction == "rtl":
            title_text = Text("\u202b" + raw_title, justify="right")
        else:
            title_text = Text(raw_title)
        t.add_row("Title:", title_text)

        row("Author:", m.author or "Unknown")
        row("Language:", m.language or "Unknown")
        row("Publisher:", m.publisher)
        row("Identifier:", m.identifier[:40] + "…" if len(m.identifier) > 40 else m.identifier)
        row("Direction:", direction_badge(m.direction))
        row("Chapters:", str(editor.get_spine_count()))
        row("File size:", fmt_size(editor.get_file_size()))
        row("Cover:", "✓ Present" if m.cover_path else "[dim]None[/dim]")

        self.update(Panel(t, title="[bold]Book Info[/bold]", border_style="cyan", box=box.ROUNDED))


class ActionMenu(ListView):
    """Sidebar action list."""

    ACTIONS = [
        ("direction", "↔  Reading Direction"),
        ("cover", "🖼  Set Cover Image"),
        ("metadata", "✏  Edit Metadata"),
        ("theme", "🎨  Theme"),
        ("save", "💾  Save EPUB"),
        ("save-as", "📁  Save As…"),
        ("close", "✗  Close File"),
    ]

    def compose(self) -> ComposeResult:
        for key, label in self.ACTIONS:
            yield ListItem(Label(label), id=f"action-{key}")


class LogPanel(RichLog):
    """Activity log at the bottom."""
    pass


class EditorScreen(Screen):
    CSS = """
    EditorScreen {
        background: $background;
    }
    /* Layout */
    #body { height: 1fr; }
    #sidebar {
        width: 28;
        background: $surface;
        border-right: solid $primary-darken-2;
        padding: 0;
    }
    #sidebar-title {
        background: $primary-darken-2;
        color: $text;
        text-align: center;
        padding: 0 1;
        height: 3;
        content-align: center middle;
    }
    #main-area { width: 1fr; }
    #info-panel { margin: 1 1 0 1; }
    #log-panel {
        height: 10;
        border-top: solid $primary-darken-2;
        margin: 0 1 0 1;
        background: $surface-darken-1;
    }
    #log-title {
        color: $text-muted;
        text-align: center;
        background: $surface-darken-2;
        height: 1;
    }
    ActionMenu {
        background: $surface;
        border: none;
    }
    ActionMenu > ListItem {
        padding: 0 1;
        border-bottom: solid $primary-darken-3;
    }
    ActionMenu > ListItem:hover {
        background: $primary-darken-1;
    }
    ActionMenu > ListItem.--highlight {
        background: $primary;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("d", "direction", "Direction"),
        Binding("c", "cover", "Cover"),
        Binding("m", "metadata", "Metadata"),
        Binding("t", "theme", "Theme"),
        Binding("s", "save", "Save"),
        Binding("S", "save_as", "Save As"),
        Binding("q", "close", "Close"),
        Binding("escape", "close", "Close", show=False),
    ]

    def __init__(self, epub_path: str):
        super().__init__()
        self.epub_path = epub_path
        self.editor: EpubEditor | None = None
        self._dirty = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static(" ACTIONS ", id="sidebar-title")
                yield ActionMenu(id="action-menu")
            with Vertical(id="main-area"):
                yield InfoPanel(id="info-panel")
                yield Static("[dim]Log[/dim]", id="log-title")
                yield LogPanel(id="log-panel", highlight=True, markup=True)
        yield Footer()

    def on_mount(self):
        self.title = f"folio — {Path(self.epub_path).name}"
        self._load_epub()

    def _log(self, msg: str):
        self.query_one("#log-panel", LogPanel).write(msg)

    def _refresh_info(self):
        if self.editor:
            self.query_one("#info-panel", InfoPanel).update_meta(self.editor)

    @work(thread=True)
    def _load_epub(self):
        self.app.call_from_thread(self._log, f"[cyan]Loading:[/cyan] {self.epub_path}")
        editor = EpubEditor(self.epub_path)
        warnings = editor.load()
        self.editor = editor
        for w in warnings:
            self.app.call_from_thread(self._log, f"[yellow]Warning:[/yellow] {w}")
        self.app.call_from_thread(self._log, "[green]✓ EPUB loaded successfully[/green]")
        self.app.call_from_thread(self._refresh_info)

    # ── List item selection ────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected):
        action_map = {
            "action-direction": self.action_direction,
            "action-cover": self.action_cover,
            "action-metadata": self.action_metadata,
            "action-theme": self.action_theme,
            "action-save": self.action_save,
            "action-save-as": self.action_save_as,
            "action-close": self.action_close,
        }
        handler = action_map.get(event.item.id)
        if handler:
            handler()

    # ── Actions ────────────────────────────────────────────────────────────

    def _require_editor(self) -> bool:
        if not self.editor or not self.editor._is_loaded:
            self._log("[red]EPUB not loaded yet. Please wait.[/red]")
            return False
        return True

    def action_direction(self):
        if not self._require_editor():
            return
        cur = self.editor.metadata.direction
        new_dir = "ltr" if cur == "rtl" else "rtl"
        msg = f"Switch reading direction from [bold]{cur.upper()}[/bold] to [bold]{new_dir.upper()}[/bold]?"
        self.app.push_screen(ConfirmScreen(msg), self._on_direction_confirm(new_dir))

    def _on_direction_confirm(self, new_dir: str):
        def callback(confirmed: bool):
            if confirmed:
                self.editor.set_direction(new_dir)
                self._dirty = True
                self._refresh_info()
                self._log(f"[green]✓ Direction changed to [bold]{new_dir.upper()}[/bold][/green]")
        return callback

    def action_cover(self):
        if not self._require_editor():
            return
        self.app.push_screen(
            FilePathScreen("Set Cover Image", "e.g. /Users/me/cover.jpg"),
            self._on_cover_path,
        )

    def _on_cover_path(self, path: str | None):
        if not path:
            return
        path = str(Path(path).expanduser().resolve())
        try:
            internal = self.editor.set_cover(path)
            self._dirty = True
            self._refresh_info()
            self._log(f"[green]✓ Cover set:[/green] {internal}")
        except FileNotFoundError as e:
            self._log(f"[red]Error:[/red] {e}")
        except Exception as e:
            self._log(f"[red]Error setting cover:[/red] {e}")

    def action_metadata(self):
        if not self._require_editor():
            return
        self.app.push_screen(MetadataScreen(self.editor.metadata), self._on_metadata_saved)

    def _on_metadata_saved(self, result: dict | None):
        if result is None:
            return
        self.editor.update_metadata(**result)
        self._dirty = True
        self._refresh_info()
        self._log("[green]✓ Metadata updated[/green]")

    def action_theme(self):
        self.app.push_screen(ThemeScreen(), self._on_theme_selected)

    def _on_theme_selected(self, theme: str | None):
        if theme:
            self.app.theme = theme
            self._log(f"[green]✓ Theme set to [bold]{theme}[/bold][/green]")

    def action_save(self):
        if not self._require_editor():
            return
        self._do_save(None)

    def action_save_as(self):
        if not self._require_editor():
            return
        self.app.push_screen(
            FilePathScreen("Save As", f"{Path(self.epub_path).stem}_edited.epub"),
            self._do_save,
        )

    def _do_save(self, dest: str | None):
        if dest:
            dest = str(Path(dest).expanduser().resolve())
        try:
            out = self.editor.save(dest)
            self._dirty = False
            self._log(f"[green]✓ Saved:[/green] {out}")
            self.title = f"folio — {out.name}"
        except Exception as e:
            self._log(f"[red]Save failed:[/red] {e}")

    def action_close(self):
        def do_close(confirmed: bool):
            if confirmed:
                if self.editor:
                    self.editor.cleanup()
                self.app.pop_screen()

        if self._dirty:
            self.app.push_screen(
                ConfirmScreen("Unsaved changes. Close anyway?"),
                do_close,
            )
        else:
            if self.editor:
                self.editor.cleanup()
            self.app.pop_screen()


# ══════════════════════════════════════════════════════════════════════════════
#  App
# ══════════════════════════════════════════════════════════════════════════════

class EpubEditApp(App):
    TITLE = "folio"
    CSS = """
    Screen { background: #0d1117; }
    Header { background: $primary-darken-2; }
    Footer { background: $primary-darken-3; }
    """
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
    ]

    def __init__(self, initial_epub: str | None = None):
        super().__init__()
        self._initial_epub = initial_epub

    def on_mount(self):
        self.push_screen(WelcomeScreen())
        if self._initial_epub:
            self.push_screen(EditorScreen(self._initial_epub))


def main():
    initial_epub: str | None = None

    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser().resolve()
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        if path.suffix.lower() != ".epub":
            print(f"Error: Not an EPUB file: {path}", file=sys.stderr)
            sys.exit(1)
        initial_epub = str(path)

    EpubEditApp(initial_epub).run()


if __name__ == "__main__":
    main()
