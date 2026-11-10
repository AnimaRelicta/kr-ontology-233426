#!/usr/bin/env python3
"""
ЗАДАНИЕ 1 (сбор). Формирует домен: исполнители-люди из списка «100 величайших по версии Rolling Stone».

Шаги: список из ru.wikipedia (или data/rs100_manual.csv) -> QID через API -> сущности Wikidata (кэш data/cache/)
      -> оставляем людей (Q5) -> data/domain.csv (rank, title, qid).
Проверка домена SPARQL-запросами (доля заполненности, квалификаторы времени) - в task1_check_domain.py.

Запуск (из корня проекта):   uv run scripts/task1_collect_domain.py
Нужны: requests pandas beautifulsoup4
"""
import re
import sys
from urllib.parse import unquote

import pandas as pd
from bs4 import BeautifulSoup

import common as C
import runlog
from common import get, chunks, fetch_entities

RU_API, PAGE_TITLE, EXPECTED = C.RU_API, C.PAGE_TITLE, C.EXPECTED
MANUAL_FILE, CACHE_DIR = C.MANUAL_FILE, C.CACHE_DIR


def _article_title(href):
    if "/wiki/" not in href:
        return None
    t = href.split("/wiki/", 1)[1]
    if ":" in t or "#" in t or "redlink" in href:
        return None
    return unquote(t).replace("_", " ")


def extract_list():
    data = get(RU_API, {"action": "parse", "page": PAGE_TITLE, "prop": "text", "redirects": 1, "formatversion": 2})
    soup = BeautifulSoup(data["parse"]["text"], "html.parser")
    found = {}
    # две колонки: слева <ol> (места 1-50), справа «51. <a>..</a><br>52. ...»
    for td in soup.select("table.ts-col-begin td"):
        m = re.search(r"Места\s+(\d+)", td.get_text(" ", strip=True))
        start = int(m.group(1)) if m else 1
        ol = td.find("ol")
        if ol:
            for i, li in enumerate(ol.find_all("li", recursive=False)):
                for a in li.find_all("a", href=True):
                    t = _article_title(a["href"])
                    if t:
                        found.setdefault(start + i, t)
                        break
        else:
            cur = None
            for node in td.descendants:
                if isinstance(node, str):
                    mm = re.fullmatch(r"\s*(\d{1,3})\.\s*", node)
                    if mm:
                        cur = int(mm.group(1))
                elif node.name == "a" and cur is not None and node.get("href"):
                    t = _article_title(node["href"])
                    if t:
                        found.setdefault(cur, t)
                        cur = None
    df = pd.DataFrame([{"rank": r, "title": t} for r, t in sorted(found.items())])
    print(f"Статья: извлечено строк: {len(df)}")
    return df


def load_list():
    if MANUAL_FILE.exists():
        df = pd.read_csv(MANUAL_FILE)
        df["rank"] = range(1, len(df) + 1)
        print(f"Использую ручной список {MANUAL_FILE}: {len(df)} строк")
        return df[["rank", "title"]]
    df = extract_list()
    if len(df) != EXPECTED:
        print(f"ВНИМАНИЕ: ожидалось {EXPECTED}, получено {len(df)}. Положите рядом rs100_manual.csv (колонка title).")
    return df



def titles_to_qids(titles):
    mapping = {}
    for ch in chunks(titles, 50):
        data = get(RU_API, {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                            "titles": "|".join(ch), "redirects": 1, "formatversion": 2})
        q = data.get("query", {})
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        final = {p["title"]: p.get("pageprops", {}).get("wikibase_item") for p in q.get("pages", [])}
        for t in ch:
            t1 = norm.get(t, t)
            mapping[t] = final.get(redir.get(t1, t1))
    return mapping



def is_human(ent):
    return any(s.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5"
               for s in ent.get("claims", {}).get("P31", []))


def main():
    C.DATA.mkdir(exist_ok=True)
    lst = load_list()
    qmap = titles_to_qids(lst["title"].tolist())
    lst["qid"] = lst["title"].map(qmap)
    if lst["qid"].isna().any():
        print("Нет QID у страниц:", lst[lst["qid"].isna()]["title"].tolist())
    lst = lst.dropna(subset=["qid"])
    ents = fetch_entities(list(lst["qid"].unique()))
    domain = lst[lst["qid"].map(lambda q: q in ents and is_human(ents[q]))].reset_index(drop=True)
    print(f"Всего в списке {len(lst)}, людей (Q5): {len(domain)}")
    if not (C.DOMAIN_MIN <= len(domain) <= C.DOMAIN_MAX):
        print(f"ВНИМАНИЕ: в домене {len(domain)} сущностей, требование КР - {C.DOMAIN_MIN}-{C.DOMAIN_MAX}.")
    skipped = lst[~lst["qid"].isin(domain["qid"])]["title"].tolist()
    print("Не люди (группы и т. п.), исключены из домена:", skipped)
    domain.to_csv(C.DOMAIN_CSV, index=False)
    print(f"Сохранено: {C.DOMAIN_CSV}")
    return 0


if __name__ == "__main__":
    with runlog.session(__file__, inputs=[C.MANUAL_FILE], outputs=[C.DOMAIN_CSV]):
        sys.exit(main())
