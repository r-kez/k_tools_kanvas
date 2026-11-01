"""Regression cases for the Kanvas Markdown parser; runs without Blender."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'utils'))
from markdown import _parse, layout, parse_inline, parse_line


def fake_measure(char, size):
    return size * 0.5


def text(rows):
    return [''.join(t for t, _, _ in runs) for runs, _, _ in rows]


def styles(source):
    return [(t, s, u) for t, s, u in parse_inline(source)]


def test_inline():
    assert styles('a **b** c') == [('a ', 'plain', None), ('b', 'bold', None), (' c', 'plain', None)]
    assert styles('*i* and _j_') == [('i', 'italic', None), (' and ', 'plain', None), ('j', 'italic', None)]
    assert styles('***x***') == [('x', 'bold italic', None)]
    assert styles('~~x~~') == [('x', 'strike', None)]
    assert styles('**a *b* c**') == [('a ', 'bold', None), ('b', 'bold italic', None), (' c', 'bold', None)]
    assert styles('snake_case_name') == [('snake_case_name', 'plain', None)]
    assert styles('2 * 3 * 4') == [('2 * 3 * 4', 'plain', None)]
    assert styles('`a **b**`') == [('a **b**', 'code', None)]
    assert styles(r'\*lit\*') == [('*lit*', 'plain', None)]
    assert styles('**aberto') == [('**aberto', 'plain', None)]


def test_links():
    assert styles('[**x**](https://a.com)') == [('x', 'bold link', 'https://a.com')]
    assert styles('[x](javascript:alert(1))') == [('x', 'plain', None)]
    assert styles('<https://a.com>') == [('https://a.com', 'link', 'https://a.com')]
    assert styles('veja https://a.com/x.') == [
        ('veja ', 'plain', None), ('https://a.com/x', 'link', 'https://a.com/x'), ('.', 'plain', None)]
    assert styles('[w](https://a.com/f_(b)) fim')[0][2] == 'https://a.com/f_(b)'


def test_blocks():
    blocks = _parse(('# T', '#### h4', '---', '> q', '> > q2', '- a', '  - b', '- c',
                     '1. x', '1. y', '- [x] ok', '```', '**no**', '```', 'fim'))
    kinds = [(b.kind, b.quote, b.level, b.marker) for b in blocks]
    assert kinds[0] == ('h1', 0, 0, '')
    assert kinds[1][0] == 'h4' and blocks[1].runs[0][1] == 'bold'
    assert kinds[2][0] == 'rule'
    assert kinds[3][:2] == ('text', 1) and kinds[4][:2] == ('text', 2)
    assert kinds[5] == ('list', 0, 0, '•') and kinds[6] == ('list', 0, 1, '–')
    assert kinds[7] == ('list', 0, 0, '•')
    assert kinds[8][3] == '1.' and kinds[9][3] == '2.'
    assert kinds[10][3] == '[x]'
    assert kinds[11] == ('code', 0, 0, '') and blocks[11].runs == [('**no**', 'code', None)]
    assert kinds[12][0] == 'text'


def test_layout():
    rows = layout(['- um item bem comprido que precisa quebrar'], 200, 20, fake_measure)
    lines = text(rows)
    assert len(lines) > 1
    assert lines[0].startswith('•  um')
    indent = len(lines[1]) - len(lines[1].lstrip())
    assert indent == len('•  ')
    assert all(len(line) * 10 <= 200 for line in lines)
    long = layout(['x' * 100], 100, 20, fake_measure)
    assert all(len(line) * 10 <= 100 for line in text(long)) and len(long) > 1
    h = layout(['# T', 'p'], 400, 20, fake_measure)
    assert round(h[0][1] / 1.3) == 29 and round(h[1][1] / 1.3) == 20
    assert text(layout(['', 'a'], 400, 20, fake_measure)) == ['', 'a']
    rows = text(layout(['aaaa bbbb cccc'], 90, 20, fake_measure))
    assert rows == ['aaaa', 'bbbb', 'cccc'][:len(rows)] or all(' ' not in row or len(row) <= 9 for row in rows)


def test_compat():
    assert parse_line('## x') == ('h2', [('x', 'plain', None)])


def test_tables():
    source = ('| Tables | Are | Cool |', '| --- | :---: | ---: |',
              '| col 3 is | right-aligned | $1600 |',
              '| zebra stripes | are neat | $1 |')
    blocks = _parse(source)
    assert [block.kind for block in blocks] == ['table'] * 3
    assert blocks[0].align == ('left', 'center', 'right')
    rows = layout(source, 320, 20, fake_measure)
    assert rows[0][2]['table_header']
    assert rows[-1][2]['table_align'][2] == 'right'
    assert all(sum(row[2]['table_widths']) <= 320.001 for row in rows)

    no_edges = ('Markdown | Less | Pretty', '--- | --- | ---',
                'Still | renders | nicely', '1 | 2 | 3')
    assert len(_parse(no_edges)) == 3
    escaped = (r'Name | A\|B', '--- | ---', r'part | red\|blue')
    assert _parse(escaped)[1].cells[1] == [('red|blue', 'plain', None)]
    assert _parse(('A | B', '-- | ---'))[0].kind == 'text'
    narrow = layout(('Name | Description', '--- | ---',
                     'Item | a very long description that wraps within its cell'),
                    140, 20, fake_measure)
    assert len(narrow) > 2
    assert all(sum(row[2]['table_widths']) <= 140.001 for row in narrow)


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
