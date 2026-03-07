import json
from collections import defaultdict
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, ListView, ListItem, Label, DataTable
from textual.containers import Horizontal, Vertical

# ~/.claude/projects/ contains a subdirectory per Claude Code project. Each
# directory is name by taking the absolute project path and replacing every /
# with a -. (/home/michael/myproject becomes -home-michael-myproject). Each
# directory holds one or more jsonl files (one per conversation session). Each
# line in the jsonl file is a JSON record representing a single message. Each
# message may be a user turn or an assistant turn. User turns may include a
# tool call result as content blocks, and assitant turns may include tool calls
# as content blocks. Assistant turns include a "usage" object with token counts.
projects_dir = Path.home() / ".claude" / "projects"


def empty_totals():
    return {
        "input":             0,  # Fresh input tokens
        "cache_creation_5m": 0,  # Tokens written to ephemeral 5m cache
        "cache_creation_1h": 0,  # Tokens written to ephemeral 1h cache
        "cache_read":        0,  # Tokens read from cache
        "output":            0,  # Output tokens
    }


def get_project_name(project_dir):
    # The cwd (current working directory) contains the projects path. We'll
    # use the first recorded cwd for each project as the display name.
    for jsonl_file in sorted(project_dir.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cwd = record.get("cwd")
                if cwd:
                    return Path(cwd).name
    # Fall back to the full directory name if no cwd field is found
    return project_dir.name


COLUMNS = ["input", "cache_creation_5m", "cache_creation_1h", "cache_read", "output"]


def project_total(by_model):
    """Sum all token counts across all models for a project."""
    totals = empty_totals()
    for model_totals in by_model.values():
        for col in COLUMNS:
            totals[col] += model_totals[col]
    return totals


def load_projects():
    # projects[project_name][model] = token totals
    projects = {}

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue

        project_name = get_project_name(project_dir)
        by_model = defaultdict(empty_totals)

        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if record.get("type") != "assistant":
                        continue

                    model = record.get("message", {}).get("model", "unknown")
                    if model == "<synthetic>":
                        continue
                    usage = record.get("message", {}).get("usage", {})

                    by_model[model]["input"]      += usage.get("input_tokens", 0)
                    by_model[model]["cache_read"] += usage.get("cache_read_input_tokens", 0)
                    by_model[model]["output"]     += usage.get("output_tokens", 0)

                    cc = usage.get("cache_creation", {})
                    by_model[model]["cache_creation_5m"] += cc.get("ephemeral_5m_input_tokens", 0)
                    by_model[model]["cache_creation_1h"] += cc.get("ephemeral_1h_input_tokens", 0)

        projects[project_name] = dict(by_model)

    return dict(sorted(projects.items(), key=lambda item: sum(project_total(item[1]).values()), reverse=True))


def _bold(text: str) -> Text:
    return Text(text, style="bold")


def _total_input(totals: dict) -> int:
    return (
        totals["input"]
        + totals["cache_creation_5m"]
        + totals["cache_creation_1h"]
        + totals["cache_read"]
    )


DETAIL_FIELDS = [
    ("Fresh Input",    "input"),
    ("Cache Write 5m", "cache_creation_5m"),
    ("Cache Write 1h", "cache_creation_1h"),
    ("Cache Read",     "cache_read"),
    ("Total Input",    None),
    ("Output",         "output"),
]


class ClaudeAnalyticsApp(App):
    CSS = """
    Horizontal {
        height: 1fr;
    }
    #projects-pane {
        width: 30;
        border: solid $primary-darken-2;
    }
    #projects-pane ListView {
        height: 1fr;
    }
    #model-pane {
        width: 50;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    #breakdown-pane {
        width: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """
    BINDINGS = [
        ("n", "sort_name", "Sort: Name"),
        ("t", "sort_tokens", "Sort: Tokens"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="projects-pane"):
                yield Label(" Projects", id="projects-label")
                yield ListView(id="project-list")
            with Vertical(id="model-pane"):
                yield DataTable(id="model-table")
            with Vertical(id="breakdown-pane"):
                yield DataTable(id="breakdown-table")
        yield Footer()

    def on_mount(self) -> None:
        self.projects = load_projects()
        self._sort = "name"
        self._current_by_model: dict = {}

        model_table = self.query_one("#model-table", DataTable)
        model_table.add_columns("Model", "Input", "Output", "Cost")
        model_table.cursor_type = "row"

        breakdown_table = self.query_one("#breakdown-table", DataTable)
        breakdown_table.add_columns("Field", "Tokens")
        breakdown_table.cursor_type = "none"
        breakdown_table.show_header = True

        self._rebuild_list()

    def _sorted_names(self) -> list[str]:
        if self._sort == "name":
            return sorted(self.projects.keys())
        return sorted(
            self.projects.keys(),
            key=lambda n: sum(project_total(self.projects[n]).values()),
            reverse=True,
        )

    def _rebuild_list(self, keep_selected: str | None = None) -> None:
        self.project_names = self._sorted_names()
        project_list = self.query_one("#project-list", ListView)
        project_list.clear()
        for name in self.project_names:
            project_list.append(ListItem(Label(name)))

        if keep_selected and keep_selected in self.project_names:
            idx = self.project_names.index(keep_selected)
            project_list.index = idx
            self._show_project(keep_selected)
        elif self.project_names:
            self._show_project(self.project_names[0])

    def action_sort_name(self) -> None:
        if self._sort != "name":
            current = self._current_project()
            self._sort = "name"
            self._rebuild_list(keep_selected=current)

    def action_sort_tokens(self) -> None:
        if self._sort != "tokens":
            current = self._current_project()
            self._sort = "tokens"
            self._rebuild_list(keep_selected=current)

    def _current_project(self) -> str | None:
        idx = self.query_one("#project-list", ListView).index
        if idx is not None and idx < len(self.project_names):
            return self.project_names[idx]
        return None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and idx < len(self.project_names):
            self._show_project(self.project_names[idx])

    def _show_project(self, project_name: str) -> None:
        table = self.query_one("#model-table", DataTable)
        table.clear()
        self.title = f"Claude Analytics — {project_name}"

        by_model = self.projects[project_name]
        self._current_by_model = by_model

        for model, totals in sorted(by_model.items()):
            table.add_row(
                model,
                f"{_total_input(totals):,}",
                f"{totals['output']:,}",
                "$0.00",
                key=model,
            )

        if len(by_model) > 1:
            table.add_row(
                _bold("TOTAL"),
                f"{_total_input(project_total(by_model)):,}",
                f"{project_total(by_model)['output']:,}",
                "$0.00",
                key="__total__",
            )

        self.query_one("#breakdown-table", DataTable).clear()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "model-table":
            return
        key = event.row_key.value if event.row_key else None
        if key is None:
            return

        if key == "__total__":
            totals = project_total(self._current_by_model)
        else:
            totals = self._current_by_model.get(key)

        if totals:
            self._show_breakdown(totals)

    def _show_breakdown(self, totals: dict) -> None:
        table = self.query_one("#breakdown-table", DataTable)
        table.clear()
        for label, field in DETAIL_FIELDS:
            value = _total_input(totals) if field is None else totals[field]
            table.add_row(label, f"{value:,}")


def main():
    ClaudeAnalyticsApp().run()


if __name__ == "__main__":
    main()
