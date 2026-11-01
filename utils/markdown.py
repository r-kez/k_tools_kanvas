"""Dependency-free Markdown subset for Kanvas text cards.

The model is line based: every source line is its own paragraph, so a newline
is always a visible line break (what people expect from a notes card). Only a
few things carry over between lines: code fences and list nesting/numbering.

    _parse(lines)  -> blocks, independent of width and font (cached)
    layout(...)    -> wrapped rows for blf: (runs, height, meta)

A run is (text, style, url). `style` is a space separated set of flags taken
from: plain, bold, italic, strike, code, link, quote. `meta` is a dict a
renderer can use for decorations (quote bars, rules, code background, task
boxes); a renderer that ignores it still shows readable text.

Supported: headings #..######, **bold**, *italic*, ***both***, ~~strike~~,
`code`, [links](url), ![images](url) as links, <autolinks>, bare URLs,
backslash escapes, bullet / ordered / nested / task lists, > quotes (nested),
``` fenced code, horizontal rules.
Not supported (yet): setext headings, HTML, reference links.
"""

import re
from collections import namedtuple
from functools import lru_cache
from urllib.parse import urlsplit


HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$')
RULE = re.compile(r'^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$')
FENCE = re.compile(r'^\s*(`{3,}|~{3,})(.*)$')
QUOTE = re.compile(r'^ {0,3}>[ ]?')
LIST = re.compile(r'^([ \t]*)([-*+]|\d{1,9}[.)])[ \t]+(.*)$')
TASK = re.compile(r'^\[([ xX])\][ \t]+(.*)$')
AUTOLINK = re.compile(r'<(https?://[^\s<>]+)>')
BARE_URL = re.compile(r'https?://[^\s<>]+')
LINK_TARGET = re.compile(
    r'\(\s*<?((?:[^\s()<>]|\([^\s()<>]*\))+)>?(?:\s+(?:"[^"]*"|\'[^\']*\'))?\s*\)')

PUNCT = frozenset('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')
EMPHASIS = {
    ('*', 1): frozenset({'italic'}), ('_', 1): frozenset({'italic'}),
    ('*', 2): frozenset({'bold'}), ('_', 2): frozenset({'bold'}),
    ('*', 3): frozenset({'bold', 'italic'}), ('_', 3): frozenset({'bold', 'italic'}),
    ('~', 2): frozenset({'strike'}),
}
MAX_DEPTH = 6

BULLETS = ('•', '–')
SIZES = {'h1': 1.45, 'h2': 1.25, 'h3': 1.1}
INDENT = 1.6        # em per list nesting level
QUOTE_STEP = 1.1    # em per quote bar

Block = namedtuple('Block', 'kind runs quote level marker cells align',
                   defaults=(None, None))


def safe_link(url):
    """Only browser URLs with a host can become clickable."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    return url if parts.scheme in {'http', 'https'} and parts.hostname else None


# ── inline ────────────────────────────────────────────────────────────────

def _style(flags):
    return ' '.join(sorted(flags)) or 'plain'


def _with_flag(style, flag):
    flags = set(style.split())
    flags.discard('plain')
    flags.add(flag)
    return ' '.join(sorted(flags))


def _code_span(text, i):
    """For a backtick run at i return (body_start, body_end, end) or None."""
    n = 1
    while i + n < len(text) and text[i + n] == '`':
        n += 1
    close = text.find('`' * n, i + n)
    while close != -1:
        end = close + n
        if text[close - 1] != '`' and (end >= len(text) or text[end] != '`'):
            return i + n, close, end
        close = text.find('`' * n, close + 1)
    return None


def _find_closer(text, start, char, count):
    """Index of a closing delimiter run of exactly `count` chars, or -1."""
    j = start
    while j < len(text):
        c = text[j]
        if c == '\\':
            j += 2
        elif c == '`':
            span = _code_span(text, j)
            if span:
                j = span[2]
            else:
                while j < len(text) and text[j] == '`':
                    j += 1
        elif c == char:
            k = j
            while k < len(text) and text[k] == char:
                k += 1
            if (k - j == count and j > start and not text[j - 1].isspace()
                    and not (char == '_' and k < len(text) and text[k].isalnum())):
                return j
            j = k
        else:
            j += 1
    return -1


def _match_link(text, i):
    """Match [label](url) or ![alt](url) at i -> (end, label, url) or None."""
    start = i + 1 if text[i] == '!' else i
    if start >= len(text) or text[start] != '[':
        return None
    depth, j = 0, start
    while j < len(text):
        c = text[j]
        if c == '\\':
            j += 2
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                break
        j += 1
    else:
        return None
    target = LINK_TARGET.match(text, j + 1)
    if not target:
        return None
    return target.end(), text[start + 1:j], target.group(1)


def parse_inline(text, flags=frozenset(), url=None, depth=0):
    """Return merged runs [(text, style, url)] for one line of inline Markdown."""
    runs, buf = [], []

    def flush():
        if buf:
            runs.append((''.join(buf), _style(flags), url))
            buf.clear()

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '\\' and i + 1 < n and text[i + 1] in PUNCT:
            buf.append(text[i + 1])
            i += 2
        elif c == '`':
            span = _code_span(text, i)
            if span:
                flush()
                body = text[span[0]:span[1]]
                if len(body) > 2 and body[0] == ' ' and body[-1] == ' ' and body.strip():
                    body = body[1:-1]
                runs.append((body, _style(flags | {'code'}), url))
                i = span[2]
            else:
                j = i
                while j < n and text[j] == '`':
                    j += 1
                buf.append(text[i:j])
                i = j
        elif c in '![' and depth < MAX_DEPTH and (link := _match_link(text, i)):
            end, label, target = link
            flush()
            safe = safe_link(target)
            label = label or target
            if safe:
                runs.extend(parse_inline(label, flags | {'link'}, safe, depth + 1))
            else:
                runs.extend(parse_inline(label, flags, url, depth + 1))
            i = end
        elif c == '<' and (auto := AUTOLINK.match(text, i)) and safe_link(auto.group(1)):
            flush()
            runs.append((auto.group(1), _style(flags | {'link'}), auto.group(1)))
            i = auto.end()
        elif (c == 'h' and url is None and (i == 0 or not text[i - 1].isalnum())
              and (bare := BARE_URL.match(text, i))):
            target = bare.group(0)
            while target and target[-1] in '.,;:!?\'"':
                target = target[:-1]
            if target.endswith(')') and target.count(')') > target.count('('):
                target = target[:-1]
            if safe_link(target):
                flush()
                runs.append((target, _style(flags | {'link'}), target))
                i += len(target)
            else:
                buf.append(c)
                i += 1
        elif c in '*_~' and depth < MAX_DEPTH:
            j = i
            while j < n and text[j] == c:
                j += 1
            count = j - i
            style = EMPHASIS.get((c, count))
            after = text[j] if j < n else ''
            if (style and after and not after.isspace()
                    and not (c == '_' and i > 0 and text[i - 1].isalnum())):
                close = _find_closer(text, j, c, count)
                if close != -1:
                    flush()
                    runs.extend(parse_inline(text[j:close], flags | style, url, depth + 1))
                    i = close + count
                    continue
            buf.append(text[i:j])
            i = j
        else:
            buf.append(c)
            i += 1
    flush()

    merged = []
    for run in runs:
        if merged and merged[-1][1:] == run[1:]:
            merged[-1] = (merged[-1][0] + run[0], run[1], run[2])
        else:
            merged.append(run)
    return merged


# ── blocks ────────────────────────────────────────────────────────────────

def _table_cells(line):
    """Split unescaped pipes outside inline code; edge pipes are optional."""
    source = line.strip()
    cells = []
    cell = []
    ticks = 0
    index = 0
    while index < len(source):
        char = source[index]
        if char == '\\' and index + 1 < len(source):
            cell.extend((char, source[index + 1]))
            index += 2
            continue
        if char == '`':
            end = index
            while end < len(source) and source[end] == '`':
                end += 1
            count = end - index
            ticks = 0 if ticks == count else count if not ticks else ticks
            cell.append(source[index:end])
            index = end
            continue
        if char == '|' and not ticks:
            cells.append(''.join(cell).strip())
            cell = []
        else:
            cell.append(char)
        index += 1
    cells.append(''.join(cell).strip())
    if source.startswith('|'):
        cells.pop(0)
    if source.endswith('|') and (len(source) < 2 or source[-2] != '\\'):
        cells.pop()
    return cells


def _table_alignments(line):
    if '|' not in line:
        return None
    cells = _table_cells(line)
    if len(cells) < 2 or any(not re.fullmatch(r':?-{3,}:?', cell) for cell in cells):
        return None
    return tuple('center' if cell.startswith(':') and cell.endswith(':')
                 else 'right' if cell.endswith(':') else 'left' for cell in cells)


@lru_cache(maxsize=512)
def _parse(lines):
    """Turn a tuple of source lines into Blocks. Pure, so it is cached."""
    blocks = []
    fence = None
    stack = []       # indent width of each open list level
    counters = {}    # level -> next ordered number
    kinds = {}       # level -> 'ul' | 'ol'

    def reset_lists():
        stack.clear()
        counters.clear()
        kinds.clear()

    index = 0
    while index < len(lines):
        raw = lines[index]
        index += 1
        source = raw.rstrip('\r\n').expandtabs(4)

        if fence:
            m = FENCE.match(source)
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            else:
                blocks.append(Block('code', [(source, 'code', None)], 0, 0, ''))
            continue
        m = FENCE.match(source)
        if m and not (m.group(1)[0] == '`' and '`' in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            reset_lists()
            continue

        quote = 0
        while (m := QUOTE.match(source)):
            quote += 1
            source = source[m.end():]

        if index < len(lines) and '|' in source:
            delimiter = lines[index].rstrip('\r\n').expandtabs(4)
            delimiter_quote = 0
            while (m := QUOTE.match(delimiter)):
                delimiter_quote += 1
                delimiter = delimiter[m.end():]
            align = _table_alignments(delimiter) if delimiter_quote == quote else None
            header_cells = _table_cells(source)
            if align and len(header_cells) == len(align):
                reset_lists()
                blocks.append(Block('table', [], quote, 0, '',
                                    tuple(parse_inline(cell) for cell in header_cells), align))
                index += 1
                while index < len(lines):
                    row_source = lines[index].rstrip('\r\n').expandtabs(4)
                    row_quote = 0
                    while (m := QUOTE.match(row_source)):
                        row_quote += 1
                        row_source = row_source[m.end():]
                    if row_quote != quote or '|' not in row_source or not row_source.strip():
                        break
                    cells = _table_cells(row_source)
                    cells = (cells + [''] * len(align))[:len(align)]
                    blocks.append(Block('table', [], quote, 1, '',
                                        tuple(parse_inline(cell) for cell in cells), align))
                    index += 1
                continue

        heading = HEADING.match(source)
        if heading:
            reset_lists()
            level = len(heading.group(1))
            flags = frozenset({'bold'}) if level >= 4 else frozenset()
            blocks.append(Block(f'h{level}', parse_inline(heading.group(2), flags),
                                quote, 0, ''))
        elif RULE.match(source):
            reset_lists()
            blocks.append(Block('rule', [], quote, 0, ''))
        elif (item := LIST.match(source)):
            indent, marker, body = len(item.group(1)), item.group(2), item.group(3)
            while stack and indent < stack[-1]:
                stack.pop()
                counters.pop(len(stack), None)
                kinds.pop(len(stack), None)
            if not stack or indent >= stack[-1] + 2:
                stack.append(indent)
            level = len(stack) - 1
            ordered = marker[0].isdigit()
            kind = 'ol' if ordered else 'ul'
            if kinds.get(level) != kind:
                counters.pop(level, None)
            kinds[level] = kind
            if ordered:
                number = counters.get(level)
                number = int(marker[:-1]) if number is None else number
                counters[level] = number + 1
                label = f'{number}.'
            else:
                label = BULLETS[level % len(BULLETS)]
            task = TASK.match(body)
            if task:
                label = '[x]' if task.group(1) in 'xX' else '[ ]'
                body = task.group(2)
            blocks.append(Block('list', parse_inline(body), quote, level, label))
        else:
            if source.strip():
                reset_lists()
            blocks.append(Block('text', parse_inline(source), quote, 0, ''))
    return blocks


def parse_line(source):
    """Compatibility helper: (kind, runs) for a single line."""
    blocks = _parse((source,))
    return (blocks[0].kind, blocks[0].runs) if blocks else ('text', [])


# ── layout ────────────────────────────────────────────────────────────────

def _wrap(first, rest, runs, width, size, advance):
    """Greedy word wrap. Words wider than a row are split by character."""
    tokens = []      # (is_space, [(char, style, url), ...])
    for text, style, url in runs:
        for char in text:
            space = char.isspace()
            if tokens and tokens[-1][0] == space:
                tokens[-1][1].append((char, style, url))
            else:
                tokens.append((space, [(char, style, url)]))

    rows = []
    row, used, fresh = [], 0.0, True

    def begin(prefix):
        nonlocal row, used, fresh
        row = list(prefix)
        used = sum(advance(c, size) for text, _, _ in prefix for c in text)
        fresh = True

    def add(cells):
        nonlocal used, fresh
        for char, style, url in cells:
            if row and row[-1][1] == style and row[-1][2] == url:
                row[-1] = (row[-1][0] + char, style, url)
            else:
                row.append((char, style, url))
            used += advance(char, size)
        fresh = False

    def flush():
        while row:
            text = row[-1][0].rstrip()
            if text:
                row[-1] = (text, row[-1][1], row[-1][2])
                break
            row.pop()
        rows.append(row or [('', 'plain', None)])
        begin(rest)

    begin(first)
    for space, cells in tokens:
        w = sum(advance(c, size) for c, _, _ in cells)
        if space:
            if fresh and rows:
                continue                    # no leading blanks after a soft wrap
            if used + w > width:
                flush()
                continue
            add(cells)
            continue
        if used + w > width and not fresh:
            flush()
        if used + w <= width:
            add(cells)
            continue
        for cell in cells:                  # a single word wider than the card
            if used + advance(cell[0], size) > width and not fresh:
                flush()
            add([cell])
    flush()
    return rows


def layout_inline(source, width, font_size, measure):
    """Wrap inline styles without treating checklist text as Markdown blocks."""
    return _wrap([], [], parse_inline(source), width, font_size, measure)


def _table_layout(group, width, font_size, advance):
    """Allocate columns once and expand wrapped cells into visual rows."""
    columns = len(group[0].align)
    size = round(font_size)
    height = size * 1.3
    quote_offset = min(group[0].quote * size * QUOTE_STEP, width * 0.3)
    table_width = max(1.0, width - quote_offset)
    padding = min(max(3.0, size * 0.35), table_width / max(2, columns * 4))
    desired = []
    for column in range(columns):
        desired.append(max(size * 1.5, *(
            sum(advance(char, size) for value, _, _ in row.cells[column]
                for char in value) for row in group)))
    total = sum(desired)
    inner_total = max(1.0, table_width - 2 * padding * columns)
    widths = tuple(inner_total * value / total + 2 * padding for value in desired)
    starts = [quote_offset]
    for column_width in widths[:-1]:
        starts.append(starts[-1] + column_width)

    rows = []
    for block in group:
        wrapped = [
            _wrap([], [], block.cells[column],
                  max(1.0, widths[column] - 2 * padding), size, advance)
            for column in range(columns)
        ]
        count = max(len(cell_rows) for cell_rows in wrapped)
        for line in range(count):
            cells = tuple(cell_rows[line] if line < len(cell_rows)
                          else [('', 'plain', None)] for cell_rows in wrapped)
            fallback = []
            for column, cell in enumerate(cells):
                if column:
                    fallback.append((' | ', 'plain', None))
                fallback.extend(cell)
            rows.append((fallback, height, {
                'kind': 'table', 'quote': block.quote,
                'quote_step': size * QUOTE_STEP,
                'table_cells': cells, 'table_starts': tuple(starts),
                'table_widths': widths, 'table_align': block.align,
                'table_padding': padding, 'table_header': block.level == 0,
                'table_first': line == 0, 'table_last': line == count - 1,
            }))
    return rows


def layout(lines, width, font_size, measure):
    """Wrap parsed blocks into rows: [(runs, height, meta)].

    `measure(char, size)` is supplied by the caller (blf). Row height is
    size * 1.3, so `size` can still be recovered as round(height / 1.3).
    """
    blocks = _parse(tuple(lines))
    cache = {}

    def advance(char, size):
        key = (char, size)
        if key not in cache:
            cache[key] = measure(char, size)
        return cache[key]

    rows = []
    block_index = 0
    while block_index < len(blocks):
        block = blocks[block_index]
        if block.kind == 'table':
            end = block_index + 1
            while (end < len(blocks) and blocks[end].kind == 'table'
                   and blocks[end].quote == block.quote
                   and blocks[end].align == block.align):
                end += 1
            rows.extend(_table_layout(blocks[block_index:end], width,
                                      font_size, advance))
            block_index = end
            continue
        block_index += 1
        size = round(font_size * SIZES.get(block.kind, 1))
        height = size * 1.3
        space = max(advance(' ', size), 0.1)

        def pad(px):
            return ' ' * round(px / space) if px > 0 else ''

        quote_step = size * QUOTE_STEP
        base = min(block.quote * quote_step + block.level * size * INDENT, width * 0.5)
        first = [(pad(base), 'plain', None)] if pad(base) else []
        content_px = base
        if block.marker:
            marker = block.marker + '  '
            first.append((marker, 'plain', None))
            content_px = min(base + sum(advance(c, size) for c in marker), width * 0.6)
        rest = [(pad(content_px), 'plain', None)] if pad(content_px) else []

        meta = {'kind': block.kind, 'quote': block.quote,
                'quote_step': quote_step, 'indent': content_px}
        if block.kind == 'rule':
            rows.append(([('', 'plain', None)], height, meta))
            continue
        runs = block.runs
        if block.quote:
            runs = [(t, _with_flag(s, 'quote'), u) for t, s, u in runs]
        for index, row in enumerate(_wrap(first, rest, runs, width, size, advance)):
            rows.append((row, height,
                         dict(meta, marker=block.marker) if index == 0 else meta))
    return rows
