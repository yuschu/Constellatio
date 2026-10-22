"""纯 Python .po → .mo 编译器（无 gettext 二进制依赖）。

用法：
    python tools/compile_mo.py

规则：
- 只处理 locale/*/LC_MESSAGES/*.po
- header（msgid ""）写入 .mo 的空 msgid，供 gettext 识别 charset
- 跳过 fuzzy、空 msgstr、obsolete（#~）
- 不支持 msgctxt / msgid_plural（v1.4 不需要，遇到直接报错）
- 输出标准 GNU .mo（magic 0x950412de），供 gettext.GNUTranslations 读取
"""

from __future__ import annotations

import ast
import re
import struct
import sys
from pathlib import Path

MAGIC = 0x950412DE
HEADER = 'Content-Type: text/plain; charset=UTF-8\n'


def _parse_quoted(line: str) -> str:
    line = line.strip()
    if not line.startswith('"'):
        raise ValueError(f'不是合法的 PO 字符串: {line!r}')
    return ast.literal_eval(line)


def _blocks(text: str):
    return re.split(r'\n[ \t]*\n', text.replace('\r\n', '\n'))


def parse_po_text(text: str) -> tuple[str, dict[str, str]]:
    header = ''
    entries: dict[str, str] = {}
    for block in _blocks(text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if any(ln.startswith('#~') for ln in lines):
            continue
        fuzzy = any(ln.startswith('#,') and 'fuzzy' in ln for ln in lines)
        msgid = None
        msgstr = None
        field = None
        plural = False
        for line in lines:
            if line.startswith('#'):
                continue
            if line.startswith('msgctxt '):
                raise ValueError('不支持 msgctxt')
            if line.startswith('msgid_plural '):
                plural = True
                continue
            if line.startswith('msgstr['):
                plural = True
                continue
            if line.startswith('msgid '):
                if msgid is not None:
                    raise ValueError('一个块里出现多个 msgid')
                msgid = _parse_quoted(line[6:].strip())
                field = 'msgid'
            elif line.startswith('msgstr '):
                msgstr = _parse_quoted(line[7:].strip())
                field = 'msgstr'
            elif line.startswith('"'):
                value = _parse_quoted(line)
                if field == 'msgid':
                    msgid = (msgid or '') + value
                elif field == 'msgstr':
                    msgstr = (msgstr or '') + value
                else:
                    raise ValueError('悬空字符串')
            else:
                raise ValueError(f'无法解析行 {line!r}')
        if plural:
            raise ValueError('v1.4 不支持 msgid_plural')
        if msgid is None:
            continue
        if msgid == '':
            header = msgstr or ''
            continue
        if fuzzy or not msgstr:
            continue
        entries[msgid] = msgstr
    return header, entries


def parse_po(path: Path) -> tuple[str, dict[str, str]]:
    return parse_po_text(path.read_text(encoding='utf-8-sig'))


def build_mo(header: str, entries: dict[str, str]) -> bytes:
    if 'Content-Type' not in header:
        if header and not header.endswith('\n'):
            header += '\n'
        header += HEADER
    entries = {'': header, **entries}
    keys = sorted(entries, key=lambda s: s.encode('utf-8'))
    n = len(keys)

    key_table_offset = 28
    value_table_offset = key_table_offset + 8 * n
    string_offset = value_table_offset + 8 * n

    key_blob = b''.join(k.encode('utf-8') + b'\x00' for k in keys)
    value_blob = b''.join(entries[k].encode('utf-8') + b'\x00' for k in keys)

    key_offsets = []
    cursor = string_offset
    for key in keys:
        raw = key.encode('utf-8')
        key_offsets.append((len(raw), cursor))
        cursor += len(raw) + 1

    value_offsets = []
    cursor = string_offset + len(key_blob)
    for key in keys:
        raw = entries[key].encode('utf-8')
        value_offsets.append((len(raw), cursor))
        cursor += len(raw) + 1

    out = bytearray()
    out += struct.pack('<7I', MAGIC, 0, n,
                       key_table_offset, value_table_offset, 0, 0)
    for length, offset in key_offsets:
        out += struct.pack('<2I', length, offset)
    for length, offset in value_offsets:
        out += struct.pack('<2I', length, offset)
    out += key_blob
    out += value_blob
    return bytes(out)


def compile_po(po_path: Path, mo_path: Path | None = None) -> Path:
    header, entries = parse_po(po_path)
    mo_path = mo_path or po_path.with_suffix('.mo')
    mo_path.write_bytes(build_mo(header, entries))
    return mo_path


def compile_all(locale_dir: Path | None = None) -> list[Path]:
    root = locale_dir or (Path(__file__).resolve().parent.parent / 'locale')
    compiled = []
    for po in sorted(root.glob('*/LC_MESSAGES/*.po')):
        compiled.append(compile_po(po))
    return compiled


def main() -> int:
    try:
        compiled = compile_all()
    except Exception as exc:  # noqa: BLE001
        print(f'[i18n] compile failed: {exc}', file=sys.stderr)
        return 1
    print(f'[i18n] compiled {len(compiled)} catalog(s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
