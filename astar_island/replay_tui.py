"""TUI for stepping through Astar Island replay files.

Usage:
    uv run python -m astar_island.replay_tui astar_island/data/round_16/replay.json

Keys:
    Left/Right or h/l  — step backward/forward
    Home/End            — jump to first/last frame
    +/-                 — zoom in/out
    c                   — toggle changed-cell highlighting
    Click a cell        — show cell detail + history in sidebar
    q                   — quit
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.geometry import Size
from textual.message import Message
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, Header, Static

from astar_island.replay import Replay, Settlement, tile_name

LOG_FILE = Path("replay_tui.log")
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,
)
log = logging.getLogger(__name__)

# Tile colors: background color per raw grid value
TILE_STYLES: dict[int, Style] = {
    11: Style(color="black", bgcolor="#90b050"),      # plains - green
    10: Style(color="white", bgcolor="#2050a0"),       # water - blue
    1: Style(color="white", bgcolor="#d04040"),        # settlement - red
    2: Style(color="white", bgcolor="#d0a020"),        # port - gold
    3: Style(color="white", bgcolor="#707070"),        # ruin - grey
    4: Style(color="white", bgcolor="#206020"),        # forest - dark green
    5: Style(color="white", bgcolor="#a0a0a0"),        # mountain - light grey
}

TILE_CHARS: dict[int, str] = {
    11: "  ",  # plains
    10: "~~",  # water
    1: "##",   # settlement
    2: "@@",   # port
    3: "..",   # ruin
    4: "&&",   # forest
    5: "/\\",  # mountain
}

CHANGED_OVERLAY = Style(color="white", bgcolor="#ff00ff", bold=True)

DEFAULT_STYLE = Style(color="white", bgcolor="black")


class GridWidget(Widget):
    """Renders the 40x40 replay grid with optional change highlighting."""

    class CellClicked(Message):
        def __init__(self, x: int, y: int) -> None:
            super().__init__()
            self.x = x
            self.y = y

    can_focus = True

    frame_index: reactive[int] = reactive(0)
    highlight_changes: reactive[bool] = reactive(False)
    cell_width: reactive[int] = reactive(2)

    def __init__(self, replay: Replay, **kwargs) -> None:
        super().__init__(**kwargs)
        self.replay = replay
        self._changed_set: set[tuple[int, int]] = set()

    def get_content_width(self, container: Size, viewport: Size) -> int:
        return self.replay.width * self.cell_width

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        return self.replay.height

    def watch_frame_index(self, value: int) -> None:
        self._update_changed_set()
        self.refresh()

    def watch_highlight_changes(self, value: bool) -> None:
        self.refresh()

    def watch_cell_width(self, value: int) -> None:
        self.refresh()

    def _update_changed_set(self) -> None:
        transitions = self.replay.transitions_at_step(self.frame_index)
        self._changed_set = {(t.x, t.y) for t in transitions}

    def render_line(self, y: int) -> Strip:
        frame = self.replay.frames[self.frame_index]
        if y >= self.replay.height:
            return Strip.blank(self.size.width)

        segments = []
        cw = self.cell_width
        for x in range(self.replay.width):
            val = int(frame.grid[y, x])
            style = TILE_STYLES.get(val, DEFAULT_STYLE)

            if self.highlight_changes and (x, y) in self._changed_set:
                style = CHANGED_OVERLAY

            char = TILE_CHARS.get(val, "??")
            if cw == 1:
                segments.append(Segment(char[0], style))
            elif cw == 2:
                segments.append(Segment(char[:2], style))
            else:
                segments.append(Segment(char[0] * cw, style))

        return Strip(segments)

    def on_click(self, event) -> None:
        x = event.x // self.cell_width
        y = event.y
        if 0 <= x < self.replay.width and 0 <= y < self.replay.height:
            self.post_message(self.CellClicked(x, y))


class InfoPanel(Static):
    """Shows frame info, selected cell detail, and cell history."""

    def __init__(self, replay: Replay, **kwargs) -> None:
        super().__init__(**kwargs)
        self.replay = replay
        self._frame_index = 0
        self._selected: tuple[int, int] | None = None

    def on_mount(self) -> None:
        log.debug("InfoPanel.on_mount called")
        self._render_content()

    def update_frame(self, index: int) -> None:
        log.debug("InfoPanel.update_frame(%d)", index)
        self._frame_index = index
        self._render_content()

    def update_selection(self, x: int, y: int) -> None:
        log.debug("InfoPanel.update_selection(%d, %d)", x, y)
        self._selected = (x, y)
        self._render_content()

    def _render_content(self) -> None:
        from rich.text import Text

        text = Text()
        frame = self.replay.frames[self._frame_index]
        transitions = self.replay.transitions_at_step(self._frame_index)
        log.debug(
            "InfoPanel._render_content: frame=%d, transitions=%d, selected=%s",
            self._frame_index, len(transitions), self._selected,
        )

        # Frame info
        text.append(f"Step {frame.step}", style="bold #e0e0e0")
        text.append(f" / {self.replay.frames[-1].step}\n", style="#e0e0e0")
        text.append(f"Settlements: {frame.n_settlements} ({frame.n_alive} alive)\n", style="#e0e0e0")
        text.append(f"Changes: {len(transitions)}\n\n", style="#e0e0e0")

        # Changes this step
        if transitions:
            text.append("Changes this step:\n", style="bold #e0e0e0")
            for t in transitions[:20]:
                text.append(f"  ({t.x:2d},{t.y:2d}) {t.old_name} -> {t.new_name}\n", style="#e0e0e0")
            if len(transitions) > 20:
                text.append(f"  ... +{len(transitions) - 20} more\n", style="#e0e0e0")
            text.append("\n")

        # Selected cell
        if self._selected:
            x, y = self._selected
            val = int(frame.grid[y, x])
            text.append(f"Cell ({x}, {y})\n", style="bold #e0e0e0")
            text.append(f"Terrain: {tile_name(val)} (raw={val})\n", style="#e0e0e0")

            settlement = frame.settlement_at(x, y)
            if settlement:
                self._append_settlement(text, settlement)

            history = self.replay.cell_history(x, y)
            if history:
                text.append(f"\nHistory ({len(history)} transitions):\n", style="bold #e0e0e0")
                for t in history:
                    marker = " <<" if t.step == self._frame_index else ""
                    text.append(f"  step {t.step:2d}: {t.old_name} -> {t.new_name}{marker}\n", style="#e0e0e0")
            else:
                text.append("No transitions (static cell)\n", style="dim #e0e0e0")

        log.debug("InfoPanel: updating with %d chars of text", len(text.plain))
        self.update(text)

    def _append_settlement(self, text, s: Settlement) -> None:
        from rich.text import Text

        text.append(f"  Owner: {s.owner_id}", style="#e0e0e0")
        if s.has_port:
            text.append(" PORT", style="bold yellow")
        if not s.alive:
            text.append(" DEAD", style="bold red")
        text.append(f"\n  Pop: {s.population:.3f}  Food: {s.food:.3f}\n", style="#e0e0e0")
        text.append(f"  Wealth: {s.wealth:.3f}  Def: {s.defense:.3f}\n", style="#e0e0e0")


class LegendPanel(Static):
    """Static legend showing tile types."""

    def on_mount(self) -> None:
        from rich.text import Text

        text = Text()
        text.append("Legend\n", style="bold #e0e0e0")
        for val, name in sorted(TILE_CHARS.items(), key=lambda x: x[0]):
            char = TILE_CHARS[val]
            text.append(f"  {char} {tile_name(val)}\n", style="#e0e0e0")
        text.append("\n")
        text.append("Keys\n", style="bold #e0e0e0")
        for line in [
            "  Left/h  prev step",
            "  Right/l next step",
            "  Home    first step",
            "  End     last step",
            "  +/-     zoom in/out",
            "  c       highlight changes",
            "  click   inspect cell",
        ]:
            text.append(f"{line}\n", style="#e0e0e0")
        self.update(text)


class ReplayTUI(App):
    CSS = """
    #main {
        width: 1fr;
        height: 1fr;
    }
    #sidebar {
        width: 36;
        height: 1fr;
        border-left: solid $primary;
        overflow-y: auto;
        background: $surface;
    }
    #grid-container {
        overflow: auto;
        width: 1fr;
        height: 1fr;
    }
    GridWidget {
        width: auto;
        height: auto;
    }
    #info {
        height: auto;
        padding: 0 1;
        color: #e0e0e0;
    }
    #legend {
        height: auto;
        padding: 0 1;
        border-top: solid $primary;
        color: #e0e0e0;
    }
    """

    BINDINGS = [
        Binding("right,l", "step_forward", "Next"),
        Binding("left,h", "step_backward", "Prev"),
        Binding("home", "jump_start", "Start"),
        Binding("end", "jump_end", "End"),
        Binding("plus,equal", "zoom_in", "Zoom+"),
        Binding("minus", "zoom_out", "Zoom-"),
        Binding("c", "toggle_changes", "Changes"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, replay: Replay) -> None:
        super().__init__()
        self.replay = replay
        self._frame_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="grid-container"):
                yield GridWidget(self.replay, id="grid")
            with Vertical(id="sidebar"):
                yield InfoPanel(self.replay, id="info")
                yield LegendPanel(id="legend")
        yield Footer()

    def on_mount(self) -> None:
        log.debug("ReplayTUI.on_mount called")
        self.title = f"Replay: {self.replay.round_id[:12]}..."
        self.sub_title = f"{self.replay.width}x{self.replay.height} | {len(self.replay)} frames"
        self._sync_ui()

    def _sync_ui(self) -> None:
        grid = self.query_one("#grid", GridWidget)
        info = self.query_one("#info", InfoPanel)
        grid.frame_index = self._frame_index
        info.update_frame(self._frame_index)

    def action_step_forward(self) -> None:
        if self._frame_index < len(self.replay) - 1:
            self._frame_index += 1
            self._sync_ui()

    def action_step_backward(self) -> None:
        if self._frame_index > 0:
            self._frame_index -= 1
            self._sync_ui()

    def action_jump_start(self) -> None:
        self._frame_index = 0
        self._sync_ui()

    def action_jump_end(self) -> None:
        self._frame_index = len(self.replay) - 1
        self._sync_ui()

    def action_zoom_in(self) -> None:
        grid = self.query_one("#grid", GridWidget)
        if grid.cell_width < 4:
            grid.cell_width += 1

    def action_zoom_out(self) -> None:
        grid = self.query_one("#grid", GridWidget)
        if grid.cell_width > 1:
            grid.cell_width -= 1

    def action_toggle_changes(self) -> None:
        grid = self.query_one("#grid", GridWidget)
        grid.highlight_changes = not grid.highlight_changes

    @on(GridWidget.CellClicked)
    def on_cell_clicked(self, event: GridWidget.CellClicked) -> None:
        info = self.query_one("#info", InfoPanel)
        info.update_selection(event.x, event.y)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python -m astar_island.replay_tui <replay.json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    replay = Replay.from_file(path)
    app = ReplayTUI(replay)
    app.run()


if __name__ == "__main__":
    main()
