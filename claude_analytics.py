import json
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


projects = {}

for project_dir in sorted(projects_dir.iterdir()):
    if not project_dir.is_dir():
        continue

    project_name = get_project_name(project_dir)
    totals = empty_totals()

    for jsonl_file in sorted(project_dir.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                # Strip whitespace
                line = line.strip()
                # Skip blank lines
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue

                # Only assistant turns have token usage
                if record.get("type") != "assistant":
                    continue

                usage = record.get("message", {}).get("usage", {})
                totals["input"]            += usage.get("input_tokens", 0)
                totals["cache_read"]       += usage.get("cache_read_input_tokens", 0)
                totals["output"]           += usage.get("output_tokens", 0)

                # cache_creation is a nested object broken down by cache lifetime (5m vs 1h)
                cc = usage.get("cache_creation", {})
                totals["cache_creation_5m"] += cc.get("ephemeral_5m_input_tokens", 0)
                totals["cache_creation_1h"] += cc.get("ephemeral_1h_input_tokens", 0)

    projects[project_name] = totals

COLUMNS = ["input", "cache_creation_5m", "cache_creation_1h", "cache_read", "output"]

# Sort by total tokens, highest first
projects = dict(sorted(projects.items(), key=lambda item: sum(item[1].values()), reverse=True))

# Compute totals row
grand_total = {col: sum(t[col] for t in projects.values()) for col in COLUMNS}

# Calculate column widths based on content (including totals row)
all_rows = list(projects.values()) + [grand_total]
name_width = max(len("project"), max(len(n) for n in projects), len("total"))
col_widths = {col: max(len(col), max(len(f"{t[col]:,}") for t in all_rows)) for col in COLUMNS}

# Header
header = f"{'project':<{name_width}}  " + "  ".join(f"{col:>{col_widths[col]}}" for col in COLUMNS)
sep = "-" * len(header)
print(sep)
print(header)
print(sep)

for name, totals in projects.items():
    row = f"{name:<{name_width}}  " + "  ".join(f"{totals[col]:>{col_widths[col]},}" for col in COLUMNS)
    print(row)

print(sep)
totals_row = f"{'total':<{name_width}}  " + "  ".join(f"{grand_total[col]:>{col_widths[col]},}" for col in COLUMNS)
print(totals_row)
print(sep)
