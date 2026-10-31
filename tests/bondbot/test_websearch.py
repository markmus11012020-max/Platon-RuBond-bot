from __future__ import annotations

from bondbot.services.websearch import parse_ddg_html

HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsmart-lab.ru%2Fblog%2F1.php&rut=x">
    Балтийский лизинг: обзор
  </a>
  <a class="result__snippet">Что известно об эмитенте.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/news/2">Другая новость</a>
  <div class="result__snippet">Краткое описание.</div>
</div>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fduckduckgo.com%2Fsettings&rut=x">
    Настройки
  </a>
</div>
</body></html>
"""


def test_parse_ddg_html_decodes_and_filters() -> None:
    results = parse_ddg_html(HTML, limit=5)
    assert len(results) == 2
    assert results[0]["source"] == "smart-lab"
    assert results[0]["url"] == "https://smart-lab.ru/blog/1.php"
    assert results[0]["title"] == "Балтийский лизинг: обзор"
    assert results[0]["snippet"] == "Что известно об эмитенте."
    assert results[0]["live"] is True
    assert results[1]["source"] == "example.com"
