"""纯文本翻译（不依赖视觉模型）：给文本层路由使用。

优先用配置好的 OpenAI 兼容端点（qwen / gemini / 任意 LLM，纯文本请求更快更便宜），
没有 key 时退回 Google 免费端点（需要能访问 clients5.google.com）。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .config import Config

BATCH = 20

SYSTEM = (
    '你是专业的文档翻译引擎。用户给出一段 JSON {{"lines":["...","..."]}}，'
    '把每一行翻译成{target}，逐行一一对应，行数必须完全一致。'
    '保留原文的数字、编号、专有名词（人名/机构/型号首次出现可加中文括注）。'
    '只输出 JSON：{{"lines":["..."]}}，不要解释。'
)


def _post(cfg: Config, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        cfg.endpoint,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cfg.api_key}',
        },
        method='POST',
    )
    opener = urllib.request.build_opener()
    if cfg.proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': cfg.proxy, 'https': cfg.proxy})
        )
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _extract(content: str, expected: int) -> list[str]:
    start, end = content.find('['), content.rfind(']')
    if start >= 0 and end > start:
        try:
            arr = json.loads(content[start : end + 1])
            if isinstance(arr, list) and len(arr) == expected:
                return [str(x or '').strip() for x in arr]
        except json.JSONDecodeError:
            pass
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if len(lines) == expected:
        return lines
    raise ValueError('行数与输入不一致')


def _google_one(text: str, target: str, proxy: str) -> str:
    url = (
        'https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=auto'
        f'&tl={urllib.parse.quote(target)}&q={urllib.parse.quote(text)}'
    )
    opener = urllib.request.build_opener()
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': proxy, 'https': proxy})
        )
    with opener.open(urllib.request.Request(url), timeout=20) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    rows = data if isinstance(data, list) and data and isinstance(data[0], list) else [data]
    return str(rows[0][0] if rows and rows[0] else '').strip()


def translate_texts(texts: list[str], cfg: Config) -> list[str]:
    """把若干段文本翻译成目标语言；失败的行返回空串。"""
    out = [''] * len(texts)
    has_key = bool(cfg.api_key)

    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        if has_key:
            body = {
                'model': cfg.text_model or cfg.model,
                'temperature': 0.1,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {'role': 'system', 'content': SYSTEM.format(target=cfg.target_lang)},
                    {'role': 'user', 'content': json.dumps({'lines': batch}, ensure_ascii=False)},
                ],
            }
            try:
                data = _post(cfg, body)
                content = data['choices'][0]['message']['content']
                if isinstance(content, list):
                    content = ''.join(p.get('text', '') for p in content)
                for k, t in enumerate(_extract(str(content), len(batch))):
                    out[i + k] = t
                continue
            except (urllib.error.HTTPError, KeyError, ValueError, urllib.error.URLError):
                pass  # 落到 Google

        for k, text in enumerate(batch):
            try:
                out[i + k] = _google_one(text, cfg.target_lang or 'zh-CN', cfg.proxy)
            except Exception:  # noqa: BLE001
                out[i + k] = ''
    return out

