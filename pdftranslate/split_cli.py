"""CLI：拆分 PDF。

    python -m pdftranslate.split 文件.pdf --each
    python -m pdftranslate.split 文件.pdf --every 5
    python -m pdftranslate.split 文件.pdf --ranges 1-3,7,10-
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .split import split_pdf


def _normalize_argv(argv: list[str]) -> list[str]:
    """把 `--ranges -5` 这种以 - 开头的取值改写成 `--ranges=-5`。

    argparse 会把 `-5` 当成选项而不是参数值，导致
    "argument --ranges: expected one argument"。
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        cur = argv[i]
        if cur == '--ranges' and i + 1 < len(argv):
            nxt = argv[i + 1]
            if nxt.startswith('-') and not nxt.startswith('--'):
                out.append(f'--ranges={nxt}')
                i += 2
                continue
        out.append(cur)
        i += 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog='pdftranslate.split',
        description='把多页 PDF 拆成多个小文件',
        epilog=(
            '页码范围写法（用逗号分隔，每段产出一个文件）：' + chr(10) +
            '  1-3        第 1 到 3 页合成一个文件' + chr(10) +
            '  7          只取第 7 页，单独一个文件' + chr(10) +
            '  10-        第 10 页一直到最后一页' + chr(10) +
            '  -5         第 1 页到第 5 页' + chr(10) +
            '  1-3,7,10-  产出 3 个文件：p001-003、p007、p010-末页' + chr(10) +
            '  （以 - 开头时也可写 --ranges=-5）' + chr(10) +
            chr(10) +
            '规则：超出页数自动裁剪；重叠或相邻范围合并（1-3,2-5 → 1-5）；' + chr(10) +
            '      无法解析的片段忽略；中文逗号也认。' + chr(10)
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('input', type=Path, help='输入 PDF（也可以是目录）')
    ap.add_argument('-o', '--out', type=Path, default=Path('out') / 'split', help='输出目录')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--each', action='store_true', help='每页一个文件（默认）')
    mode.add_argument('--every', type=int, metavar='N', help='每 N 页一个文件')
    mode.add_argument('--ranges', metavar='SPEC', help='自定义范围，如 1-3,7,10-')
    ap.add_argument('--no-zip', action='store_true', help='不生成 zip 打包')
    args = ap.parse_args(_normalize_argv(list(argv if argv is not None else sys.argv[1:])))

    targets = (
        [args.input]
        if args.input.is_file()
        else sorted(p for p in args.input.rglob('*.pdf') if p.is_file())
    )
    if not targets:
        print(f'没有找到 PDF：{args.input}', file=sys.stderr)
        return 1

    if args.every:
        mode_name, every, ranges = 'every', args.every, ''
    elif args.ranges:
        mode_name, every, ranges = 'ranges', 1, args.ranges
    else:
        mode_name, every, ranges = 'each', 1, ''

    exit_code = 0
    for src in targets:
        try:
            res = split_pdf(
                src,
                args.out / src.stem if len(targets) > 1 else args.out,
                mode=mode_name,
                every=every,
                ranges=ranges,
                make_zip=not args.no_zip,
            )
        except Exception as exc:  # noqa: BLE001
            print(f'✗ {src.name}: {exc}', file=sys.stderr)
            exit_code = 2
            continue

        out_dir = res.files[0].parent if res.files else args.out
        print(f'✓ {src.name}（{res.total_pages} 页）→ {len(res.files)} 个文件')
        if len(res.files) <= 6:
            for (s, e), f in zip(res.plan, res.files):
                print(f'    {f.name}  ({e - s + 1} 页)')
        else:
            for (s, e), f in list(zip(res.plan, res.files))[:3]:
                print(f'    {f.name}  ({e - s + 1} 页)')
            print(f'    … 共 {len(res.files)} 个')
        if res.zip_path:
            print(f'    打包：{res.zip_path}')
        print(f'    目录：{out_dir}')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
