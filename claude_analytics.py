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

totals = {
    "input":              0,	# Fresh input tokens
    "cache_creation_5m":  0,	# Tokens written to ephemeral 5m cache
    "cache_creation_1h":  0,	# Tokens written to ephemeral 1h cache
    "cache_read":         0,	# Tokens read from cache
    "output":             0,	# Output tokens
}

for project_dir in sorted(projects_dir.iterdir()):
    if not project_dir.is_dir():
        continue
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
                totals["input"]     += usage.get("input_tokens", 0)
                totals["cache_read"] += usage.get("cache_read_input_tokens", 0)
                totals["output"]    += usage.get("output_tokens", 0)

                # cache_creation is a nested object broken down by cache lifetime (5m vs 1h)
                cc = usage.get("cache_creation", {})
                totals["cache_creation_5m"] += cc.get("ephemeral_5m_input_tokens", 0)
                totals["cache_creation_1h"] += cc.get("ephemeral_1h_input_tokens", 0)

for key, value in totals.items():
    print(f"{key}: {value:,}")
