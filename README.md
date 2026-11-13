# 扫描件 / PDF / 截图 翻译

用视觉大模型把**扫描件、手写件、图片型 PDF、截图**转写并翻译成中文。
不做传统 OCR —— 直接把整页图交给视觉模型，一次完成「转写 + 理解版式 + 翻译」。

> 传统 OCR 对手写体基本无解。样本里那封 1970 年的手写信，Adobe 自带的文本层
> 识别成了 `Eagiaaerins School`（正确是 Engineering School），而视觉模型能整段读通。

---

## 能做什么

| 输入 | 输出 |
|---|---|
| 扫描版 / 图片型 PDF | **双语 PDF**（原页 + 译文页，表格渲染成真表格） |
| | **覆盖式 HTML**（原页做底图、译文按原位置贴回，最接近原件观感） |
| | **译文 Markdown**（逐块中英对照） |
| 单张截图 / 图片 | 同上（也可被浏览器扩展调用来做「截图翻译」） |
| 多页 PDF | **拆分**成多个小文件（每页一个 / 每 N 页 / 自定义范围） |

脚本、表格、印章、涂黑、手写批注都能处理；涂黑处输出 `[涂黑 (b)(6)]` 而不是猜内容。

---

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # 填一个视觉模型的 Key
```

### 图形界面

```cmd
start-server.cmd            :: 打开 http://127.0.0.1:8765/
```

拖 PDF 进左侧 → 选模型/页码 → 开始翻译 → 右侧出三个结果链接。

### 命令行

```bash
# 先不花钱，验证排版（内置示例数据）
.venv\Scripts\python.exe -m pdftranslate samples/xxx.pdf --mock -o out

# 真实翻译
.venv\Scripts\python.exe -m pdftranslate samples/xxx.pdf -o out

# 只翻第 1-3 页，手写件提高渲染精度
.venv\Scripts\python.exe -m pdftranslate samples/xxx.pdf --pages 1-3 --dpi 300

# 整个目录（递归）
.venv\Scripts\python.exe -m pdftranslate samples -o out --concurrency 3

# 先看会处理哪些文件、共多少页（不渲染、不花钱）
.venv\Scripts\python.exe -m pdftranslate samples --dry-run

# 断点续跑：已翻过的页走缓存
.venv\Scripts\python.exe -m pdftranslate samples --skip-done

# 只要覆盖式 HTML / 只要双语 PDF
.venv\Scripts\python.exe -m pdftranslate x.pdf --html --only html
.venv\Scripts\python.exe -m pdftranslate x.pdf --only pdf
```

常用参数：`--pages` `--dpi` `--concurrency` `--target` `--provider` `--force`
`--skip-done` `--no-original` `--only` `--dry-run` `--mock`

### 拆分 PDF（不翻译，只拆）

```bash
# 每页一个文件（默认）
.venv\Scripts\python.exe -m pdftranslate.split samples/xxx.pdf --each -o out/split

# 每 5 页一个文件
.venv\Scripts\python.exe -m pdftranslate.split samples/xxx.pdf --every 5

# 自定义范围：第 1 页、第 3-4 页、第 10 页到末尾
.venv\Scripts\python.exe -m pdftranslate.split samples/xxx.pdf --ranges 1,3-4,10-

# 整个目录，每个文件拆到自己子目录
.venv\Scripts\python.exe -m pdftranslate.split samples -o out/split --each
```

也可以在 Web 界面右侧「PDF 拆分」面板里操作（选文件 → 选方式 → 开始拆分 → 下载 zip）。

- 用 `insert_pdf` 做页拷贝，**不重新光栅化**：拆分后画质与原文件一致
- 多个输出自动打包 `<原名>_split.zip`
- 范围写法容错：`1-99` 会裁剪到实际页数，`1-3,2-5` 自动合并，`abc` 这类无效片段忽略

---

## 模型

内置四个预设，`--provider` 或 `.env` 的 `VISION_PROVIDER` 切换：

| provider | 模型 | Key 变量 | 网络 |
|---|---|---|---|
| `qwen`（默认） | qwen3-vl-plus | `DASHSCOPE_API_KEY` | 国内直连 |
| `gemini` | gemini-2.5-flash | `GEMINI_API_KEY` | 需代理 |
| `openai` | gpt-4.1-mini | `OPENAI_API_KEY` | 需代理 |
| `glm` | glm-4.5v | `ZHIPU_API_KEY` | 国内直连 |

也可以在 Web UI 的「模型管理」里**增删改**（存 `models.json`），填 Key（存 `secrets.json`），
并做连通性测试。任意 OpenAI 兼容的视觉端点都能接。

**实测对比**（同一页 6 行表格）：qwen 42.7s / gemini 163.9s，都正确抽出表格结构。
gemini 在文档页上慢 4 倍，所以默认超时设到 300s。

---

## 三种输出的取舍

| 输出 | 适合 | 说明 |
|---|---|---|
| **双语 PDF** | 打印、归档 | 原页用 `insert_pdf` 无损拷贝（体积≈原文件），译文页附浅灰原文 |
| **覆盖式 HTML** | 对着原件读 | 译文按原坐标叠在原图上，可调底图浓度/字号，可打印；表格是真 `<table>` |
| **译文 MD** | 二次编辑 | 逐块中英对照，方便复制到笔记 |

---

## 怎么保证坐标准

视觉模型给的 bbox 在密集文档上**并不可靠**（靠近页面原点准、越远越偏）。
所以有文本层时以文本层为准：

1. **逐行归属**：文本层每一行去找它最可能属于哪个块（不是整块匹配 ——
   公文常是"标签在左、值在右"，整块匹配会因阅读顺序不同而错位），再合并成块框
2. **可信度门槛**：匹配 ≥3 块且占比 ≥40% 才采信，否则判定文本层是垃圾 OCR，退回模型坐标
3. **顺排降级**：校准可信时，没匹配上的块不再硬贴（会压住别人），渲染到页面下方；
   整页坐标明显异常（过扁/重叠/面积离谱）则整页改为「原图 + 顺排译文」

改排版、修坐标**不需要重新调模型** —— 逐页结果都缓存在 `out/.cache/<name>/page-N.json`。

---

## 给浏览器扩展调用

服务暴露两个给"截图翻译"用的接口：

```
POST /api/screen   {"image":"data:image/png;base64,...","target":"简体中文"}
                → {"ok":true,"blocks":[{"bbox":[l,t,r,b],"original":"...","translation":"..."}]}
GET  /api/config   模型列表与当前默认
```

坐标是归一化的 `[左, 上, 右, 下]`（0–1），调用方按图片宽高换算即可。

---

## 测试

```bash
# 冒烟测试 34 项：坐标归一化 / 表格结构 / CJK 断行 / 列宽 / 坐标质量 /
# 模型注册表 / PDF 拆分 plan / 端到端 mock 管线（不联网、不花钱）
.venv\Scripts\python.exe tests\smoke.py
```

---

## 已知限制

1. **无文本层的纯扫描件**只能依赖模型 bbox，覆盖式 HTML 可能错位（双语 PDF 不受影响）
2. **表格**：跨页表、合并单元格会散；极宽表格在 PDF 里会挤，建议看 HTML
3. **手写体**逐页效果不一，个别页不准可只重跑那几页
4. 每页一次模型调用，费用按页计（qwen 约 0.01–0.03 元/页）

## 目录

```
pdftranslate/
  render.py      PDF → PNG（按页懒加载，长边压到 1800px）
  vision.py      视觉模型调用 + JSON 解析 + bbox 归一化
  snap.py        文本层逐行校准坐标
  build.py       双语 PDF（真表格）+ Markdown
  build_html.py  覆盖式 HTML（真表格、顺排降级）
  screen.py      截图翻译
  pipeline.py    CLI 与 Web UI 共用流水线
  server.py      本地 Web 界面（:8765）+ /api/screen + /api/split
  split.py       PDF 拆分（页拷贝，无损）
  split_cli.py   拆分命令行
  models.py      模型注册表（models.json / secrets.json）
```
