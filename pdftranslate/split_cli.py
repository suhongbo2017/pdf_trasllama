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
            '切分页写法：填的页 = 在这一页之后切开（逗号分隔）。' + chr(10) +
            chr(10) +
            '  10 页文件填 1,3,7-9 → 切成 6 份：' + chr(10) +
            '    第 1 页 | 第 2-3 页 | 第 4-7 页 | 第 8 页 | 第 9 页 | 第 10 页' + chr(10) +
            chr(10) +
            '  1,3     第 1 页、第 3 页之后各切一刀  → 1 | 2-3 | 4-末页' + chr(10) +
            '  5       只在第 5 页之后切一刀        → 1-5 | 6-末页' + chr(10) +
            '  7-9     第 7、8、9 页之后各切一刀    → 这三页各自成份' + chr(10) +
            chr(10) +
            '规则：范围展开成逐页；超出页数自动裁剪；中文逗号也认；' + chr(10) +
            '      无法解析的片段忽略。' + chr(10)
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('input', type=Path, help='输入 PDF（也可以是目录）')
    ap.add_argument('-o', '--out', type=Path, default=Path('out') / 'split', help='输出目录')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--each', action='store_true', help='每页一个文件（默认）')
    mode.add_argument('--every', type=int, metavar='N', help='每 N 页一个文件')
    mode.add_argument('--cuts', metavar='SPEC', help='切分页：在这几页之后切开，如 1,3,7-9')
    mode.add_argument('--ranges', metavar='SPEC', help='（旧名，等同于 --cuts）')
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

    cuts_spec = args.cuts or args.ranges or ''
    if args.every:
        mode_name, every, cuts_spec = 'every', args.every, ''
    elif cuts_spec:
        mode_name, every = 'cuts', 1
    else:
        mode_name, every = 'each', 1

    exit_code = 0
    for src in targets:
        try:
            res = split_pdf(
                src,
                args.out / src.stem if len(targets) > 1 else args.out,
                mode=mode_name,
                every=every,
                cuts=cuts_spec,
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
