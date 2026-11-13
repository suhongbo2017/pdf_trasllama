"""PDF 拆分：把多页 PDF 拆成若干个小文件。

三种模式：
  each    每页一个文件
  every   每 N 页一个文件
  ranges  按自定义范围（如 1-3,7,10-12）

只做 `insert_pdf` 页拷贝，不重新光栅化 —— 拆分后画质与原文件一致、体积也不会膨胀。
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class SplitResult:
    files: list[Path]
    zip_path: Path | None
    total_pages: int
    plan: list[tuple[int, int]]  # 每个输出文件对应的页范围（1-based，闭区间）


def parse_ranges(spec: str, total: int) -> list[tuple[int, int]]:
    """把 "1-3,7,10-" 解析成 [(1,3),(7,7),(10,total)]，越界自动裁剪。"""
    out: list[tuple[int, int]] = []
    for raw in spec.replace('，', ',').split(','):
        part = raw.strip()
        if not part:
            continue
        try:
            if '-' in part.lstrip('-'):
                a, _, b = part.partition('-')
                start = int(a) if a.strip() else 1
                end = int(b) if b.strip() else total
            else:
                start = end = int(part)
        except ValueError:
            continue  # "abc" 这类无效片段直接忽略，不要因为一行手误整单失败
        start = max(1, start)
        end = min(total, end)
        if start > end:
            continue
        out.append((start, end))
    # 合并重叠/相邻，避免重复拆分同一页
    out.sort()
    merged: list[tuple[int, int]] = []
    for s, e in out:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def build_plan(total: int, mode: str = 'each', every: int = 1, ranges: str = '') -> list[tuple[int, int]]:
    if mode == 'ranges':
        plan = parse_ranges(ranges, total)
        if not plan:
            raise ValueError('页码范围无效，示例：1-3,7,10-')
        return plan
    if mode == 'every':
        step = max(1, int(every or 1))
        return [(i, min(total, i + step - 1)) for i in range(1, total + 1, step)]
    if mode == 'each':
        return [(i, i) for i in range(1, total + 1)]
    raise ValueError(f'未知的拆分模式：{mode}')


def _output_name(stem: str, start: int, end: int, single: bool) -> str:
    if single:
        return f'{stem}_p{start:03d}.pdf'
    return f'{stem}_p{start:03d}-{end:03d}.pdf'


def split_pdf(
    src: Path,
    out_dir: Path,
    mode: str = 'each',
    every: int = 1,
    ranges: str = '',
    make_zip: bool = True,
) -> SplitResult:
    if not src.exists():
        raise FileNotFoundError(f'找不到文件：{src}')

    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    with pymupdf.open(src) as doc:
        total = doc.page_count
        plan = build_plan(total, mode=mode, every=every, ranges=ranges)

        for start, end in plan:
            target = out_dir / _output_name(src.stem, start, end, start == end)
            with pymupdf.open() as part:
                part.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
                part.save(target, garbage=3, deflate=True)
            files.append(target)

    zip_path: Path | None = None
    if make_zip and len(files) > 1:
        zip_path = out_dir / f'{src.stem}_split.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, arcname=f.name)

    return SplitResult(files=files, zip_path=zip_path, total_pages=total, plan=plan)


if __name__ == "__main__":
    from .split_cli import main

    raise SystemExit(main())
