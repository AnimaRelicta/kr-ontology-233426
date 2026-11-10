#!/usr/bin/env python3
"""
ЗАДАНИЕ 5 (сбор). Собирает корпус текстов -> data/corpus.jsonl (одна статья Википедии ru/en = одна строка).
Поля записи: id, qid, entity, source, lang, title, url, license, n_chars, text.

Запуск:   uv run scripts/task5_build_corpus.py
Нужны: requests pandas. Предварительно: task1 (domain.csv). Проверку корпуса делает task5_check_corpus.py.
"""
import json
import re
import sys
import time

import common as C
import runlog
from common import get, fetch_entities, fetch_labels, TEXT_CACHE, RU_API, EN_API

def fetch_wiki_text(lang, title):
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    f = TEXT_CACHE / f"{lang}_{re.sub(r'[^0-9A-Za-zА-Яа-я_-]', '_', title)}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    api = RU_API if lang == "ru" else EN_API
    data = get(api, {"action": "query", "prop": "extracts|info", "explaintext": 1, "inprop": "url",
                     "redirects": 1, "titles": title, "formatversion": 2})
    pages = data.get("query", {}).get("pages", [])
    page = pages[0] if pages else {}
    rec = {"title": page.get("title", title), "url": page.get("fullurl", ""), "text": (page.get("extract") or "").strip()}
    f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.3)
    return rec


def build_corpus(domain, ents, labels, path):
    n_docs, with_text, missing = 0, set(), []
    with open(path, "w", encoding="utf-8") as out:
        for r in domain.itertuples():
            sl = ents[r.qid].get("sitelinks", {})
            name = labels.get(r.qid, {}).get("ru") or labels.get(r.qid, {}).get("en") or r.title
            for lang, site in (("ru", "ruwiki"), ("en", "enwiki")):
                if site not in sl:
                    continue
                try:
                    rec = fetch_wiki_text(lang, sl[site]["title"])
                except RuntimeError as e:
                    print(f"  текст {lang} {r.qid}: {e}")
                    continue
                if not rec["text"]:
                    continue
                doc = {"id": f"{r.qid}:{lang}wiki", "qid": r.qid, "entity": name, "source": "wikipedia", "lang": lang,
                       "title": rec["title"], "url": rec["url"], "license": "CC BY-SA 4.0",
                       "n_chars": len(rec["text"]), "text": rec["text"]}
                out.write(json.dumps(doc, ensure_ascii=False) + "\n")
                n_docs += 1
                with_text.add(r.qid)
            if r.qid not in with_text:
                missing.append(r.qid)
    return n_docs, with_text, missing



def main():
    domain = C.read_domain()
    ents = fetch_entities(list(domain["qid"].unique()))
    labels = fetch_labels(set(domain["qid"]))
    n_docs, with_text, missing = build_corpus(domain, ents, labels, C.CORPUS_JSONL)
    print(f"Документов: {n_docs}; сущностей с текстом: {len(with_text)} из {len(domain)}")
    if missing:
        print("БЕЗ ТЕКСТА:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    with runlog.session(__file__, inputs=[C.DOMAIN_CSV], outputs=[C.CORPUS_JSONL]):
        sys.exit(main())
