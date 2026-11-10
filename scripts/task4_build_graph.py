#!/usr/bin/env python3
"""
ЗАДАНИЕ 4 (построение). Выгружает данные из Wikidata и описывает их терминами СВОЕЙ онтологии -> data/graph.ttl.
У каждой сущности Wikidata есть owl:sameAs на wd:Q...; награды, браки и подписчики - узлы-факты (с годом/датами).

Запуск:   uv run scripts/task4_build_graph.py
Нужны: requests pandas (rdflib - по желанию, для самопроверки). Предварительно: task1 (domain.csv).
Статистику и проверку словаря делает task4_graph_stats.py.
"""
import re
import sys
from collections import Counter
from urllib.parse import quote

import common as C
import runlog
from common import TTL, lit, fetch_entities, fetch_labels

def stmts(e, pid):
    return [s for s in e.get("claims", {}).get(pid, [])
            if s.get("rank") != "deprecated" and s.get("mainsnak", {}).get("snaktype") == "value"]


def val(st):
    return st["mainsnak"]["datavalue"]["value"]


def item_id(st):
    v = val(st)
    return v["id"] if isinstance(v, dict) and "id" in v else None


def qual_vals(st, pid):
    return [q["datavalue"]["value"] for q in st.get("qualifiers", {}).get(pid, [])
            if q.get("snaktype") == "value" and "datavalue" in q]


def parse_time(v):
    """-> (год, месяц, день, точность) или None."""
    m = re.match(r"^([+-])(\d+)-(\d\d)-(\d\d)T", v.get("time", ""))
    if not m:
        return None
    y = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
    return y, int(m.group(3)), int(m.group(4)), int(v.get("precision", 0))


def to_date(v):
    """xsd:date только при точности «день»; иначе None (не выдумываем день и месяц)."""
    t = parse_time(v)
    if not t or t[3] < 11 or not (1 <= t[0] <= 9999) or t[1] == 0 or t[2] == 0:
        return None
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"


def to_year(v):
    t = parse_time(v)
    if not t or t[3] < 9 or not (1 <= t[0] <= 9999):
        return None
    return f"{t[0]:04d}"


def to_height_cm(v):
    try:
        amount = float(v["amount"])
    except (KeyError, ValueError):
        return None
    unit = v.get("unit", "").rsplit("/", 1)[-1]
    factor = {"Q174728": 1.0, "Q11573": 100.0, "Q218593": 2.54, "Q3710": 30.48}.get(unit)   # см, м, дюйм, фут
    return None if factor is None else round(amount * factor, 1)


def to_int(v):
    try:
        return int(float(v["amount"]))
    except (KeyError, ValueError):
        return None



def build_graph(domain, ents, labels):
    """domain: DataFrame(rank,title,qid). Возвращает (TTL, types{qid: set(классов)}, предупреждения)."""
    g = TTL()
    types = {}
    warns = Counter()
    domain_ids = set(domain["qid"])

    def uri(q):
        return f"res:{q}"

    def mark(q, cls):
        types.setdefault(q, set()).add(cls)

    def emit_entity(q):
        """sameAs + метки + классы для любой сущности."""
        g.add(uri(q), "owl:sameAs", f"wd:{q}")
        lab = labels.get(q, {})
        for lg in ("ru", "en"):
            if lab.get(lg):
                g.add(uri(q), "rdfs:label", lit(lab[lg], lang=lg))
        if not lab.get("ru") and not lab.get("en"):
            warns["entity_without_label"] += 1

    def link(subj, prop, target_q, cls):
        g.add(subj, f":{prop}", uri(target_q))
        mark(target_q, cls)

    for r in domain.itertuples():
        q = r.qid
        e = ents[q]
        s = uri(q)
        mark(q, "Musician")
        g.add(s, ":rsRank", lit(int(r.rank), "integer"))
        sl = e.get("sitelinks", {})
        for site, prop, base in (("enwiki", "wikipediaEn", "https://en.wikipedia.org/wiki/"),
                                 ("ruwiki", "wikipediaRu", "https://ru.wikipedia.org/wiki/")):
            if site in sl:
                g.add(s, f":{prop}", lit(base + quote(sl[site]["title"].replace(" ", "_"), safe="()_,.-'!~*"), "anyURI"))

        # простые объектные свойства: (pid, свойство, класс значения)
        for pid, prop, cls in (("P19", "birthPlace", "Place"), ("P27", "citizenship", "Country"),
                               ("P106", "occupation", "Occupation"), ("P136", "genre", "Genre"),
                               ("P264", "recordLabel", "RecordLabel"), ("P463", "memberOf", "Organization"),
                               ("P1303", "playsInstrument", "Instrument")):
            for st in stmts(e, pid):
                t = item_id(st)
                if t:
                    link(s, prop, t, cls)
        # birthPlace функциональное: оставляем первое значение
        bp = sorted(o for (ss, p, o) in g.triples if ss == s and p == ":birthPlace")
        if len(bp) > 1:
            warns["multiple_birthPlace_trimmed"] += 1
            for o in bp[1:]:
                g.triples.discard((s, ":birthPlace", o))

        # даты и числа
        for pid, prop, conv, dt in (("P569", "birthDate", to_date, "date"), ("P570", "deathDate", to_date, "date"),
                                    ("P2031", "activeFromYear", to_year, "gYear"), ("P2032", "activeUntilYear", to_year, "gYear")):
            vals_ = []
            for st in stmts(e, pid):
                v = conv(val(st))
                if v is None:
                    warns[f"{prop}_imprecise_skipped"] += 1
                else:
                    vals_.append(v)
            if prop in ("birthDate", "deathDate"):
                vals_ = sorted(set(vals_))[:1]
            for v in sorted(set(vals_)):
                g.add(s, f":{prop}", lit(v, dt))
        for st in stmts(e, "P2048")[:1]:
            h = to_height_cm(val(st))
            if h is None:
                warns["height_unknown_unit"] += 1
            else:
                g.add(s, ":heightCm", lit(h, "decimal"))
        for st in stmts(e, "P1971")[:1]:
            n = to_int(val(st))
            if n is not None:
                g.add(s, ":childrenCount", lit(n, "integer"))
        for st in stmts(e, "P856")[:1]:
            g.add(s, ":officialWebsite", lit(val(st), "anyURI"))

        # награды (с годом)
        for i, st in enumerate(stmts(e, "P166"), 1):
            a = item_id(st)
            if not a:
                continue
            node = f"res:{q}_award_{i}"
            mark_node = types.setdefault(node, set()); mark_node.add("AwardReceipt")
            g.add(s, ":hasAwardReceipt", node)
            link(node, "award", a, "Award")
            for v in qual_vals(st, "P585")[:1]:
                y = to_year(v)
                if y:
                    g.add(node, ":awardYear", lit(y, "gYear"))
        # браки (с датами)
        for i, st in enumerate(stmts(e, "P26"), 1):
            sp = item_id(st)
            if not sp:
                continue
            node = f"res:{q}_marriage_{i}"
            types.setdefault(node, set()).add("Marriage")
            g.add(s, ":hasMarriage", node)
            link(node, "spouse", sp, "Person")
            for qp, prop in (("P580", "marriageStart"), ("P582", "marriageEnd")):
                for v in qual_vals(st, qp)[:1]:
                    d = to_date(v)
                    if d:
                        g.add(node, f":{prop}", lit(d, "date"))
                    else:
                        warns[f"{prop}_imprecise_skipped"] += 1
        # подписчики (с датой измерения)
        for i, st in enumerate(stmts(e, "P8687"), 1):
            n = to_int(val(st))
            if n is None:
                continue
            node = f"res:{q}_followers_{i}"
            types.setdefault(node, set()).add("FollowersSnapshot")
            g.add(s, ":hasFollowers", node)
            g.add(node, ":followersCount", lit(n, "integer"))
            for v in qual_vals(st, "P585")[:1]:
                d = to_date(v)
                if d:
                    g.add(node, ":followersDate", lit(d, "date"))

    # типы и sameAs/метки для всех «настоящих» сущностей (кроме служебных узлов)
    for q, cs in types.items():
        if q.startswith("res:"):
            for c in cs:
                g.add(q, "a", f":{c}")
    real = {q for q in types if not q.startswith("res:")}
    for q in sorted(real | domain_ids):
        emit_entity(q)
        for c in types.get(q, set()):
            g.add(uri(q), "a", f":{c}")
        # родительский класс не выводим вручную - это работа owlrl на этапе 6
    return g, types, warns



def selfcheck_rdflib(path, expected):
    try:
        import rdflib
    except ImportError:
        print("rdflib не установлен - самопроверка Turtle пропущена.")
        return
    gg = rdflib.Graph()
    gg.parse(path, format="turtle")
    print(f"rdflib: {path.name} читается, троек {len(gg)} (мой подсчёт: {expected})",
          "OK" if len(gg) == expected else "<- РАСХОЖДЕНИЕ")


def main():
    domain = C.read_domain()
    ents = fetch_entities(list(domain["qid"].unique()))
    need = set(domain["qid"])
    for q in domain["qid"]:
        for pid in ("P19", "P27", "P106", "P136", "P264", "P463", "P1303", "P166", "P26"):
            need.update(t for t in (item_id(s) for s in stmts(ents[q], pid)) if t)
    labels = fetch_labels(need)
    g, types, warns = build_graph(domain, ents, labels)
    g.dump(C.GRAPH_TTL, "# Граф данных RS100 (люди). Онтология: ontology.ttl")
    print(f"Граф записан: {C.GRAPH_TTL}; троек: {len(g.triples)}; узлов с типом: {len(types)}")
    print("Предупреждения сборки:", dict(warns) or "нет")
    selfcheck_rdflib(C.GRAPH_TTL, len(g.triples))
    return 0


if __name__ == "__main__":
    with runlog.session(__file__, inputs=[C.DOMAIN_CSV], outputs=[C.GRAPH_TTL]):
        sys.exit(main())
