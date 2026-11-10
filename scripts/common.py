"""Общий модуль: пути, адреса API, сетевые запросы с повторами, кэш Wikidata, запись Turtle без rdflib.

Все скрипты task1..task6 запускаются из КОРНЯ проекта (пути относительные).
Контакт для заголовка User-Agent (требование Wikimedia) задаётся переменной окружения KR_CONTACT.
"""
import json
import os
import time
from pathlib import Path

import requests

# ----------------------------------------------------------------- пути
DATA = Path("data")
CACHE_DIR = DATA / "cache"                    # кэш ответов Wikidata/Википедии (можно не сдавать)
TEXT_CACHE = CACHE_DIR / "texts"
LABELS_FILE = CACHE_DIR / "labels.json"       # {qid: {"ru": "...", "en": "..."}}
MANUAL_FILE = DATA / "rs100_manual.csv"       # необязательный ручной список (колонка title)
DOMAIN_CSV = DATA / "domain.csv"              # результат task1
ONTOLOGY_TTL = DATA / "ontology.ttl"          # результат task3
GRAPH_TTL = DATA / "graph.ttl"                # результат task4
CORPUS_JSONL = DATA / "corpus.jsonl"          # результат task5
SHAPES_TTL = Path("shapes/task6_shapes.ttl")  # ограничения SHACL (task6)
REPORTS = Path("reports")                     # отчёты: reports/taskN_*/

# ----------------------------------------------------------------- параметры домена
PAGE_TITLE = "100 величайших исполнителей всех времён по версии журнала Rolling Stone"
EXPECTED = 100
DOMAIN_MIN, DOMAIN_MAX = 30, 60

# ----------------------------------------------------------------- адреса
RU_API = "https://ru.wikipedia.org/w/api.php"
EN_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
SPARQL_URL = "https://query.wikidata.org/sparql"
UA = f"kr-ontology-rs100/1.0 (student project; contact: {os.environ.get('KR_CONTACT', 'not-set')})"
HEAD = {"User-Agent": UA}

# ----------------------------------------------------------------- пространства имён
ONT = "http://example.org/rs100/onto#"        # ПРОСТРАНСТВО ИМЁН ОНТОЛОГИИ
RES = "http://example.org/rs100/res/"         # пространство имён данных
WD = "http://www.wikidata.org/entity/"
WDT = "http://www.wikidata.org/prop/direct/"
XSD = "http://www.w3.org/2001/XMLSchema#"
MAIN_CLASS = "Musician"


def local(u):
    """Локальное имя IRI: ...#Musician -> Musician, .../Q5 -> Q5."""
    s = str(u)
    return s.split("#")[-1] if "#" in s else s.rsplit("/", 1)[-1]


def read_domain():
    import pandas as pd
    if not DOMAIN_CSV.exists():
        raise SystemExit(f"Нет {DOMAIN_CSV}: сначала запустите scripts/task1_collect_domain.py")
    return pd.read_csv(DOMAIN_CSV)


# ============================ СЕТЬ ============================
def get(url, params):
    last = None
    for attempt in range(5):
        try:
            r = requests.get(url, params={**params, "format": "json"}, headers=HEAD, timeout=60)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 5 * (attempt + 1))))
                last = "HTTP 429"
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = repr(e)
            print(f"  [попытка {attempt + 1}] {url}: {last}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Не отвечает {url}: {last}")


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ============================ КЭШ WIKIDATA ============================
def fetch_entities(ids):
    CACHE_DIR.mkdir(exist_ok=True)
    out, todo = {}, []
    for i in ids:
        f = CACHE_DIR / f"{i}.json"
        if f.exists():
            out[i] = json.loads(f.read_text(encoding="utf-8"))
        else:
            todo.append(i)
    for ch in chunks(todo, 50):
        data = get(WD_API, {"action": "wbgetentities", "ids": "|".join(ch),
                            "props": "labels|sitelinks|claims", "languages": "en|ru",
                            "sitefilter": "enwiki|ruwiki"})
        for i, ent in data.get("entities", {}).items():
            if "missing" in ent:
                continue
            (CACHE_DIR / f"{i}.json").write_text(json.dumps(ent, ensure_ascii=False), encoding="utf-8")
            out[i] = ent
        time.sleep(0.5)
    return out


def fetch_labels(ids):
    """Метки ru/en для любых QID (кэш в labels2.json)."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache = json.loads(LABELS_FILE.read_text(encoding="utf-8")) if LABELS_FILE.exists() else {}
    todo = [i for i in sorted(set(ids)) if i not in cache]
    for ch in chunks(todo, 50):
        data = get(WD_API, {"action": "wbgetentities", "ids": "|".join(ch), "props": "labels", "languages": "en|ru"})
        for i, ent in data.get("entities", {}).items():
            lab = ent.get("labels", {})
            cache[i] = {"ru": lab.get("ru", {}).get("value", ""), "en": lab.get("en", {}).get("value", "")}
        LABELS_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.5)
    return cache



# ============================ TURTLE-WRITER (без rdflib) ============================
def esc(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))


def lit(value, dt=None, lang=None):
    if lang:
        return f'"{esc(str(value))}"@{lang}'
    if dt:
        return f'"{esc(str(value))}"^^xsd:{dt}'
    return f'"{esc(str(value))}"'


class TTL:
    PREFIXES = {"": ONT, "res": RES, "wd": WD, "wdt": WDT, "owl": "http://www.w3.org/2002/07/owl#",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "xsd": XSD}

    def __init__(self):
        self.triples = set()

    def add(self, s, p, o):
        self.triples.add((s, p, o))

    def dump(self, path, header=""):
        by_s = {}
        for s, p, o in self.triples:
            by_s.setdefault(s, {}).setdefault(p, []).append(o)
        lines = [f"@prefix {k}: <{v}> ." for k, v in self.PREFIXES.items()]
        if header:
            lines.insert(0, header)
        lines.append("")
        for s in sorted(by_s):
            preds = by_s[s]
            order = sorted(preds, key=lambda p: (p != "a", p))
            parts = [f"    {p} " + ", ".join(sorted(preds[p])) for p in order]
            lines.append(f"{s}\n" + " ;\n".join(parts) + " .\n")
        Path(path).write_text("\n".join(lines), encoding="utf-8")

