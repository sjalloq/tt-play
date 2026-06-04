#!/usr/bin/env python3
"""Re-align markdown table columns in-place."""
import re
import sys
from pathlib import Path


def is_separator(line: str) -> bool:
    s = line.strip()
    if not (s.startswith('|') and s.endswith('|')):
        return False
    inner = s[1:-1]
    cells = inner.split('|')
    return len(cells) > 0 and all(re.match(r'^\s*:?-+:?\s*$', c) for c in cells)


def split_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    return [c.strip() for c in s.split('|')]


def get_alignments(sep_line: str) -> list[str]:
    out = []
    for c in split_cells(sep_line):
        left = c.startswith(':')
        right = c.endswith(':')
        if left and right:
            out.append('center')
        elif right:
            out.append('right')
        else:
            out.append('left')
    return out


def format_table(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    indent = re.match(r'^(\s*)', lines[0]).group(1)

    sep_idx = None
    for idx, line in enumerate(lines):
        if is_separator(line):
            sep_idx = idx
            break
    if sep_idx is None:
        return lines

    aligns = get_alignments(lines[sep_idx])
    num_cols = len(aligns)

    rows = [split_cells(line) for line in lines]
    for row in rows:
        while len(row) < num_cols:
            row.append('')
        while len(row) > num_cols:
            row.pop()

    col_widths = [0] * num_cols
    for idx, row in enumerate(rows):
        if idx == sep_idx:
            continue
        for c, cell in enumerate(row):
            col_widths[c] = max(col_widths[c], len(cell))

    for c in range(num_cols):
        if aligns[c] == 'center':
            min_content = 3  # :---:
            col_widths[c] = max(col_widths[c], min_content)
        elif aligns[c] == 'right':
            min_content = 2  # room for ---: after +1 dash
            col_widths[c] = max(col_widths[c], min_content)
        else:
            min_content = 1
            col_widths[c] = max(col_widths[c], min_content)

    out = []
    for idx, row in enumerate(rows):
        parts = []
        for c in range(num_cols):
            w = col_widths[c]
            if idx == sep_idx:
                if aligns[c] == 'center':
                    parts.append(':' + '-' * w + ':')
                elif aligns[c] == 'right':
                    parts.append('-' * (w + 1) + ':')
                else:
                    parts.append('-' * (w + 2))
            else:
                cell = row[c]
                if aligns[c] == 'right':
                    parts.append(' ' + cell.rjust(w) + ' ')
                elif aligns[c] == 'center':
                    parts.append(' ' + cell.center(w) + ' ')
                else:
                    parts.append(' ' + cell.ljust(w) + ' ')
        out.append(indent + '|' + '|'.join(parts) + '|')
    return out


def realign(text: str) -> str:
    lines = text.split('\n')
    out = []
    i = 0
    in_code_fence = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_fence = not in_code_fence
            out.append(line)
            i += 1
            continue
        if (not in_code_fence
                and line.lstrip().startswith('|')
                and i + 1 < len(lines)
                and is_separator(lines[i + 1])):
            start = i
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                i += 1
            out.extend(format_table(lines[start:i]))
        else:
            out.append(line)
            i += 1
    return '\n'.join(out)


if __name__ == '__main__':
    for path in sys.argv[1:]:
        p = Path(path)
        orig = p.read_text()
        new = realign(orig)
        if new != orig:
            p.write_text(new)
            print(f'rewrote {path}')
        else:
            print(f'no change {path}')
