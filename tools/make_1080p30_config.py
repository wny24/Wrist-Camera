"""Generate a candidate RKIPC INI locally; never write to a camera automatically."""

import argparse
import json
from pathlib import Path
import re

from settings import ROOT


def patch_ini(text, changes):
    remaining = {section: dict(values) for section, values in changes.items()}
    section, output = None, []

    def flush():
        for key, value in remaining.get(section, {}).items():
            output.append(f"{key} = {value}\n")
        if section in remaining:
            remaining[section].clear()

    for line in text.splitlines(keepends=True):
        header = re.match(r"^\s*\[([^]]+)\]\s*$", line)
        if header:
            flush()
            section = header.group(1)
        match = re.match(r"^\s*([^;#=]+?)\s*=", line)
        key = match.group(1).strip() if match else None
        if key in remaining.get(section, {}):
            line = f"{key} = {remaining[section].pop(key)}\n"
        output.append(line if line.endswith("\n") else line + "\n")
    flush()
    for section, values in remaining.items():
        if values:
            output.append(f"\n[{section}]\n")
            output.extend(f"{key} = {value}\n" for key, value in values.items())
    return "".join(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    changes = json.loads((ROOT / "configs/luckfox_1080p30.json").read_text())
    result = patch_ini(args.input.read_text(), changes)
    with args.output.open("x") as file:
        file.write(result)
    print(f"Candidate written to {args.output}; review, back up and deploy separately.")
