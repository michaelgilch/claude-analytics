import json
from collections import defaultdict
from pathlib import Path

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


COL_LABELS = {
    "input":             "Input",
    "cache_creation_5m": "Cache Write 5m",
    "cache_creation_1h": "Cache Write 1h",
    "cache_read":        "Cache Read",
    "output":            "Output",
}


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
    #detail-pane {
        width: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="projects-pane"):
                yield Label(" Projects", id="projects-label")
                yield ListView(id="project-list")
            with Vertical(id="detail-pane"):
                yield DataTable(id="model-table")
        yield Footer()

    def on_mount(self) -> None:
        self.projects = load_projects()
        self.project_names = list(self.projects.keys())

        project_list = self.query_one("#project-list", ListView)
        for name in self.project_names:
            project_list.append(ListItem(Label(name)))

        table = self.query_one("#model-table", DataTable)
        table.add_columns("Model", *COL_LABELS.values())
        table.cursor_type = "row"

        if self.project_names:
            self._show_project(self.project_names[0])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and idx < len(self.project_names):
            self._show_project(self.project_names[idx])

    def _show_project(self, project_name: str) -> None:
        table = self.query_one("#model-table", DataTable)
        table.clear()
        self.title = f"Claude Analytics — {project_name}"

        by_model = self.projects[project_name]
        for model, totals in sorted(by_model.items()):
            table.add_row(model, *[f"{totals[col]:,}" for col in COLUMNS])

        if len(by_model) > 1:
            proj_total = project_total(by_model)
            table.add_row("TOTAL", *[f"{proj_total[col]:,}" for col in COLUMNS])


def main():
    ClaudeAnalyticsApp().run()


if __name__ == "__main__":
    main()
