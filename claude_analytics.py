import json
from pathlib import Path

# ~/.claude/projects/ contains a subdirectory per Claude Code project. 
# Each directory is name by taking the absolute project path and replacing 
# every / with a -. (/home/michael/myproject becomes -home-michael-myproject)
# Each directory holds one or more jsonl files (one per conversation session).
# Each line in the jsonl file is a JSON record representing a single message.
# Each message may be a user turn or an assistant turn. User turns may include
# a tool call result as content blocks, and assitant turns may include tool
# calls as content blocks. 
# Assistant turns include a "usage" object with token counts.
projects_dir = Path.home() / ".claude" / "projects"

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
                print(record)
