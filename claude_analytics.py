import json
from collections import defaultdict
from pathlib import Path

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


def main():
    projects = load_projects()

    grand_total = empty_totals()
    for by_model in projects.values():
        for model_totals in by_model.values():
            for col in COLUMNS:
                grand_total[col] += model_totals[col]

    all_value_rows = [grand_total] + [t for by_model in projects.values() for t in by_model.values()]
    all_name_rows = list(projects.keys()) + [m for by_model in projects.values() for m in by_model.keys()] + ["total"]
    name_width = max(len("project"), max(len(n) for n in all_name_rows))
    col_widths = {col: max(len(col), max(len(f"{t[col]:,}") for t in all_value_rows)) for col in COLUMNS}

    header = f"{'project':<{name_width}}  " + "  ".join(f"{col:>{col_widths[col]}}" for col in COLUMNS)
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for project_name, by_model in projects.items():
        proj_total = project_total(by_model)
        print(f"{project_name:<{name_width}}  " + "  ".join(f"{proj_total[col]:>{col_widths[col]},}" for col in COLUMNS))
        for model, totals in sorted(by_model.items()):
            label = f"  {model}"
            print(f"{label:<{name_width}}  " + "  ".join(f"{totals[col]:>{col_widths[col]},}" for col in COLUMNS))

    print(sep)
    print(f"{'total':<{name_width}}  " + "  ".join(f"{grand_total[col]:>{col_widths[col]},}" for col in COLUMNS))
    print(sep)


if __name__ == "__main__":
    main()
