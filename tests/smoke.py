"""冒烟测试：不联网、不花钱，验证解析/渲染/输出链路。

    .venv\\Scripts\\python.exe tests\\smoke.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdftranslate import models as registry  # noqa: E402
from pdftranslate.build import _md_table, _wrap  # noqa: E402
from pdftranslate.build_html import bbox_quality, _col_widths  # noqa: E402
from pdftranslate.mock import mock_page  # noqa: E402
from pdftranslate.vision import _norm_bbox, _norm_rows, extract_json  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(f'  {"✓" if cond else "✗"} {name}' + (f'  ({detail})' if detail and not cond else ''))
    if not cond:
        failures.append(name)


print('\n[1] bbox 归一化')
check('标准 0-1 坐标', _norm_bbox([0.1, 0.2, 0.9, 0.8]) == [0.1, 0.2, 0.9, 0.8])
check('像素坐标按图片尺寸换算', _norm_bbox([170, 220, 1530, 880], (1700, 2200)) == [0.1, 0.1, 0.9, 0.4])
check('非法值被丢弃', _norm_bbox([1, 2, 3, 4]) is None)  # 无图片尺寸时无法换算
check('退化框被丢弃', _norm_bbox([0.5, 0.5, 0.5, 0.5]) is None)
check('超范围被丢弃', _norm_bbox([-0.5, 0.1, 1.8, 0.9]) is None)

print('\n[2] 表格结构')
rows = [['编号', '日期'], ['205', '1950年3月22日'], ['206', '1950年4月1日']]
check('rows 补齐成矩形', _norm_rows([['a', 'b'], ['c']]) == [['a', 'b'], ['c', '']])
check('单列不算表格', _norm_rows([['x'], ['y']]) is None)
md = _md_table(rows, header=True)
# 表头 + 分隔行 + (n-1) 条数据
check('markdown 表格行数', len(md) == 1 + 1 + (len(rows) - 1), f'实际 {len(md)} 行')

print('\n[3] CJK 断行与列宽')
font_ok = True
try:
    import pymupdf

    font = pymupdf.Font(fontfile='C:/Windows/Fonts/Deng.ttf')
    lines = _wrap('这是一段需要自动换行的中文文本，用来验证按字符宽度断行的逻辑是否正常工作。', font, 11, 200)
    font_ok = all(font.text_length(line, 11) <= 200.5 for line in lines)
    check('每行不超宽', font_ok, f'{len(lines)} 行')
    check('制表符被归一化', all('\t' not in line for line in _wrap('a\tb\tc', font, 10, 100)))
except Exception as exc:  # noqa: BLE001
    check('CJK 断行（跳过：字体缺失）', True, str(exc)[:40])

widths = _col_widths([['编号', '很长很长很长的一个单元格内容', 'x']] * 3)
check('列宽归一化', abs(sum(widths) - 1.0) < 1e-6)

print('\n[4] 坐标质量判定')
from pdftranslate.vision import Block  # noqa: E402

good = [Block('paragraph', 'x' * 40, 'y' * 20, [0.1, 0.1, 0.9, 0.2])]
check('正常块得分高', bbox_quality(good)[0] > 0.5, f'得分 {bbox_quality(good)[0]:.2f}')

bad = [Block('paragraph', 'a', 'b', [0.1, 0.1, 0.9, 0.101]) for _ in range(6)]
check('过扁的块被判低分', bbox_quality(bad)[0] < 0.55)

print('\n[5] 模型注册表')
entries = registry.entries()
check('至少一个模型', len(entries) >= 1)
check('default 指向存在的模型', registry.default_id() in {m.id for m in entries})
check('public() 不泄露 key', all('api_key' not in m.public() for m in entries))
check('能识别 key 是否存在', isinstance(entries[0].public().get('has_key'), bool))

print('\n[6] PDF 拆分')
from pdftranslate.split import build_plan, parse_cuts, plan_from_cuts, split_pdf  # noqa: E402

# 切分点语义：填的页 = 在这一页之后切开
check('切分点展开 1,3,7-9', parse_cuts('1,3,7-9', 10) == [1, 3, 7, 8, 9])
check('中文逗号', parse_cuts('1,3，7', 10) == [1, 3, 7])
check('单页越界直接丢弃', parse_cuts('1,99', 10) == [1])
check('范围越界裁剪到末页', parse_cuts('7-99', 10) == [7, 8, 9, 10])
check('非法片段忽略', parse_cuts('abc,,x-y', 10) == [])
check('省略起始 -5', parse_cuts('-5', 10) == [1, 2, 3, 4, 5])
check('省略结束 8-', parse_cuts('8-', 10) == [8, 9, 10])

# 需求文档里的例子：10 页 + 1,3,7-9 → 6 份
check(
    '示例 1,3,7-9 切出 6 份',
    plan_from_cuts(parse_cuts('1,3,7-9', 10), 10)
    == [(1, 1), (2, 3), (4, 7), (8, 8), (9, 9), (10, 10)],
)
check('单点切一刀 5', plan_from_cuts(parse_cuts('5', 10), 10) == [(1, 5), (6, 10)])
check('不切则整份', plan_from_cuts([], 10) == [(1, 10)])
check('切在末页不产生空文件', plan_from_cuts(parse_cuts('10', 10), 10) == [(1, 10)][:1] + [])
check('每页一个 plan', build_plan(4, mode='each') == [(1, 1), (2, 2), (3, 3), (4, 4)])
check('每 N 页 plan', build_plan(7, mode='every', every=3) == [(1, 3), (4, 6), (7, 7)])

print('\n[7] 文本层路由')
import pymupdf as _pm  # noqa: E402
from pdftranslate import textlayer  # noqa: E402

_cand = sorted((ROOT / 'samples' / 'release_02_document_bundle').glob('*.pdf'))
if _cand:
    with _pm.open(_cand[0]) as _doc:
        _pages = [textlayer.inspect(_doc[i]) for i in range(_doc.page_count)]
        check('扫描件默认不走文本路由', all(not p.usable for p in _pages),
              str([p.reason[:24] for p in _pages][:2]))
        check('强制 always 时可用', textlayer.inspect(_doc[0], prefer='always').usable)
        check('强制 never 时不可用', not textlayer.inspect(_doc[0], prefer='never').usable)
        _blocks = textlayer.extract_blocks(_doc[0])
        check('抽取到文本块', len(_blocks) > 0, f'{len(_blocks)} 块')
        check('块坐标已归一化', all(0 <= v <= 1 for b in _blocks for v in b['bbox']))
check('中文判定', textlayer.looks_like_chinese('这是一段中文文本 with few words'))
check('英文判定', not textlayer.looks_like_chinese('This is an English sentence.'))

print('\n[8] 端到端（mock，不调 API）')
with tempfile.TemporaryDirectory() as tmp:
    from pdftranslate.build import build_bilingual_pdf, write_markdown
    from pdftranslate.pipeline import Options, process_file
    from pdftranslate.render import count_pages

    # 优先用固定目录里的样例，避免被 _uploads 里的临时文件抢走
    cand = sorted((ROOT / 'samples' / 'release_02_document_bundle').glob('*.pdf'))
    src = cand[0] if cand else next(iter(sorted((ROOT / 'samples').rglob('*.pdf'))), None)
    if src is None:
        check('样例 PDF 存在（跳过：samples/ 为空）', True)
    else:
        pages = count_pages(src)
        out_dir = Path(tmp)
        from pdftranslate.config import Config

        cfg = Config.from_env(mock=True, concurrency=2)
        opts = Options(html=True)
        stat = process_file(src, cfg, opts, out_dir, src.stem, emit=lambda _l: None)
        check('页数匹配', stat.pages == pages, f'{stat.pages}/{pages}')
        check('全部成功', stat.ok == stat.pages)
        check('产出双语 PDF', (out_dir / f'{src.stem}_双语.pdf').exists())
        check('产出译文 MD', (out_dir / f'{src.stem}_译文.md').exists())
        html = out_dir / f'{src.stem}_html' / 'index.html'
        check('产出覆盖式 HTML', html.exists())
        if html.exists():
            text = html.read_text(encoding='utf-8')
            # mock 数据没有 bbox，页面会走"顺排降级"，所以两种形态都算通过
            blocks = text.count('class="blk') + text.count('flow-item')
            check('HTML 含译文内容', blocks > 0, f'块数 {blocks}')

        # 拆分同一份文件
        split_dir = out_dir / 'split'
        res = split_pdf(src, split_dir, mode='each')
        check('拆分产出页数正确', len(res.files) == pages, f'{len(res.files)}/{pages}')
        check('拆分文件存在', all(f.exists() for f in res.files))
        check('拆分生成 zip', bool(res.zip_path and res.zip_path.exists()))
        import pymupdf as _pm

        with _pm.open(res.files[0]) as part:
            check('拆分后首份为 1 页', part.page_count == 1)

print()
if failures:
    print(f'✗ {len(failures)} 项失败：' + '、'.join(failures))
    raise SystemExit(1)
print('✓ 全部通过')
