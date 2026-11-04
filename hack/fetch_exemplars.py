"""Fetch public-domain exemplars of the language teachers from ru.wikisource.

Only authors whose works are in the public domain; passages are cut from
the middle of a work, a few thousand characters each.
"""
import html
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

WORKS = {
    "chekhov": ["Тоска (Чехов)", "Студент (Чехов)", "Дама с собачкой (Чехов)"],
    "gogol": ["Шинель (Гоголь)", "Нос (Гоголь)", "Коляска (Гоголь)"],
    "leskov": ["Тупейный художник (Лесков)", "Человек на часах (Лесков)"],
    "babel": ["Переход через Збруч (Бабель)", "Соль (Бабель)"],
    "platonov": ["Возвращение (Платонов)", "Фро (Платонов)"],
    "kharms": ["Случаи (Хармс)"],
}


def raw(title, depth=0):
    url = "https://ru.wikisource.org/w/index.php?" + urllib.parse.urlencode({"title": title, "action": "raw"})
    req = urllib.request.Request(url, headers={"User-Agent": "mnemosyne-atlas/0.1"})
    t = urllib.request.urlopen(req, timeout=30).read().decode()
    m = re.match(r"#(?:REDIRECT|ПЕРЕНАПРАВЛЕНИЕ)\s*\[\[([^\]|]+)", t, re.I)
    if m and depth < 3:
        return raw(m.group(1), depth + 1)
    return t


def clean(t):
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"<ref.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"^[=:*#|!].*$", "", t, flags=re.M)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


out = Path(sys.argv[1] if len(sys.argv) > 1 else "atlas/literature/exemplars")
for author, titles in WORKS.items():
    for i, title in enumerate(titles):
        try:
            text = clean(raw(title))
        except Exception as e:
            print("skip", title, e)
            continue
        if len(text) < 1500:
            print("short", title, len(text))
            continue
        mid = len(text) // 3
        start = text.find("\n\n", mid) + 2
        passage = text[start:start + 2500]
        d = out / author
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{i}.txt").write_text(passage)
        print("ok", author, title, len(text))
