"""文本层路由：判断一页能不能"直接抽文字"，不走视觉模型。

判据只有一条是可靠的：**页面有没有整页图像**。
  - 没有整页图 → 原生电子版 PDF，文字是原始排版结果，可信
  - 有整页图   → 扫描件，文本层是 OCR 产物。实测有的 OCR 层看着像英文
                 （正常词率 0.87）其实全是垃圾（"HEt\\DQUARTEP..S"），
                 所以默认不信，继续用视觉模型（文本层仅用于校准坐标）
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

# 整页图覆盖超过这个比例，就认定这页是扫描件
SCAN_COVERAGE = 0.35
MIN_CHARS = 40


@dataclass
class TextLayerPage:
    usable: bool
    reason: str
    chars: int
    coverage: float


def _image_coverage(page: pymupdf.Page) -> float:
    """页面被图像覆盖的最大比例。"""
    area = page.rect.width * page.rect.height
    if area <= 0:
        return 0.0
    best = 0.0
    for info in page.get_images(full=True):
        try:
            for rect in page.get_image_rects(info[0]):
                best = max(best, (rect.width * rect.height) / area)
        except Exception:  # noqa: BLE001 - 个别图片解码不了就跳过
            continue
    return min(best, 1.0)


def inspect(page: pymupdf.Page, prefer: str = 'auto') -> TextLayerPage:
    """判断这页能否走文本路由。

    prefer:
      auto   仅原生电子版走文本（默认，最稳）
      always 只要文本层不是空就用（OCR 层也信，用户自担质量）
      never  一律走视觉模型
    """
    chars = len(page.get_text().strip())
    coverage = _image_coverage(page)

    if prefer == 'never':
        return TextLayerPage(False, '已关闭文本层优先', chars, coverage)
    if chars < MIN_CHARS:
        return TextLayerPage(False, f'文本层太短（{chars} 字）', chars, coverage)
    if prefer == 'always':
        return TextLayerPage(True, '强制使用文本层', chars, coverage)
    if coverage > SCAN_COVERAGE:
        return TextLayerPage(
            False, f'扫描页（整页图 {coverage:.0%}），OCR 层不可信', chars, coverage
        )
    return TextLayerPage(True, f'原生电子版（无整页图，{chars} 字）', chars, coverage)


_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def looks_like_chinese(text: str) -> bool:
    cjk = len(_CJK.findall(text))
    letters = len(_LATIN_WORD.findall(text))
    return cjk > 0 and cjk >= letters


def extract_blocks(page: pymupdf.Page) -> list[dict]:
    """按 PyMuPDF 的文本块抽取，坐标归一化，供下游排版直接使用。"""
    width, height = page.rect.width, page.rect.height
    out: list[dict] = []
    for block in page.get_text('dict').get('blocks', []):
        if block.get('type') != 0:
            continue
        lines = []
        sizes: list[float] = []
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            text = ''.join(s.get('text', '') for s in spans)
            if text.strip():
                lines.append(text)
                sizes.extend(s.get('size', 0) for s in spans)
        body = '\n'.join(lines).strip()
        if not body:
            continue
        x0, y0, x1, y1 = block['bbox']
        out.append(
            {
                'text': body,
                'bbox': [x0 / width, y0 / height, x1 / width, y1 / height],
                'size': max(sizes) if sizes else 0.0,
            }
        )
    out.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))
    return out


def classify(block: dict, page_height_ratio: float) -> str:
    """粗分块类型，只为排版时字号/颜色略有区别。"""
    top = block['bbox'][1]
    size = block.get('size') or 0
    if top < 0.12 and size >= 12:
        return 'header'
    if size >= 14:
        return 'subject'
    return 'paragraph'
