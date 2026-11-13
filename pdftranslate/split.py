"""PDF 拆分：把多页 PDF 拆成若干个小文件。

三种模式：
  each    每页一个文件
  every   每 N 页一个文件
  cuts    按切分点切开（如 1,3,7-9 表示在第 1、3、7、8、9 页之后各切一刀）

只做 `insert_pdf` 页拷贝，不重新光栅化 —— 拆分后画质与原文件一致、体积也不会膨胀。
"""

from __future__ import annotations

import re
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


def parse_cuts(spec: str, total: int) -> list[int]:
    """解析「切分点」：在这几页之后切开。

    "1,3,7-9" 表示在第 1、3、7、8、9 页之后各切一刀。
    范围会被展开成逐页（7-9 → 7,8,9），越界自动裁剪，无效片段忽略。
    """
    pts: set[int] = set()
    for raw in spec.replace(chr(65292), ',').split(','):
        part = raw.strip()
        if not part:
            continue
        m = re.fullmatch(r'(\d*)-(\d*)', part)
        try:
            if m and (m.group(1) or m.group(2)):
                start = int(m.group(1)) if m.group(1) else 1
                end = int(m.group(2)) if m.group(2) else total
            elif part.isdigit():
                start = end = int(part)
            else:
                continue
        except ValueError:
            continue
        for page in range(max(1, start), min(total, end) + 1):
            pts.add(page)
    return sorted(pts)


def plan_from_cuts(cuts: list[int], total: int) -> list[tuple[int, int]]:
    """按切分点生成每份文件的页范围（1-based 闭区间）。"""
    plan: list[tuple[int, int]] = []
    start = 1
    for cut in cuts:
        if cut < start:
            continue
        plan.append((start, cut))
        start = cut + 1
    if start <= total:
        plan.append((start, total))
    return plan


def build_plan(
    total: int,
    mode: str = 'each',
    every: int = 1,
    cuts: str = '',
) -> list[tuple[int, int]]:
    if mode == 'cuts':
        points = parse_cuts(cuts, total)
        if not points:
            raise ValueError('没有解析出有效切分页，示例：1,3,7-9')
        return plan_from_cuts(points, total)
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
    cuts: str = '',
    make_zip: bool = True,
) -> SplitResult:
    if not src.exists():
        raise FileNotFoundError(f'找不到文件：{src}')

    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    with pymupdf.open(src) as doc:
        total = doc.page_count
        plan = build_plan(total, mode=mode, every=every, cuts=cuts)

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
