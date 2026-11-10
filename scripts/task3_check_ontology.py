#!/usr/bin/env python3
"""
ЗАДАНИЕ 3 (проверка). Автоматическая проверка онтологии на требования КР + таблица «вопрос -> классы и свойства».

Таблица вопросов берётся из банка вопросов task2_questions.py (одно место правды).
Свойства/классы, не использованные ни в одном вопросе, выводятся с черновым пояснением (EXPLAIN) - его нужно
подтвердить в отчёте или удалить лишние свойства из онтологии (в КР: «онтология описывает только то, что нужно вопросам»).

Запуск:  uv run scripts/task3_check_ontology.py [--onto data/ontology.ttl]
Нужен: rdflib. Результат: reports/task3_ontology/ontology_check.md (+ код возврата 1, если есть нарушения).
Скриншоты Protégé (иерархия классов, свойства с domain/range) делаются вручную.
"""
import argparse
import sys
from pathlib import Path

from rdflib import Graph, URIRef, Literal, RDF, RDFS, OWL

import common as C
import runlog
from common import local
from task2_questions import USAGE

NS = C.ONT
OUT_DIR = C.REPORTS / "task3_ontology"

# Черновые пояснения для свойств и классов, которых нет в вопросах 1-12 (подтвердите или исправьте).
EXPLAIN = {
    "birthPlace": "функциональное объектное свойство основного класса (место рождения, класс Place); нужно для условия «>=5 свойств» и для расширений («кто родился в городе N»)",
    "citizenship": "описание основного класса (объектное свойство к Country); нужно для условия домена «>=5 свойств» и для расширений (фильтр по стране)",
    "occupation": "описание основного класса (объектное свойство к Occupation); нужно для условия «>=5 свойств»",
    "genre": "описание основного класса (объектное свойство к Genre); нужно для условия «>=5 свойств»",
    "recordLabel": "описание основного класса (объектное свойство к RecordLabel); нужно для условия «>=5 свойств»",
    "playsInstrument": "описание основного класса (объектное свойство к Instrument); нужно для условия «>=5 свойств»",
    "award": "связывает факт получения награды (AwardReceipt) с самой наградой; без него hasAwardReceipt (Q3, Q12) не описывает, какая награда получена",
    "awardYear": "квалификатор времени награды (требование домена: свойство с временным квалификатором); основа для вопросов вида «награды за 1990-е»",
    "hasFollowers": "связывает музыканта с замером числа подписчиков (числовой показатель с датой, требование домена)",
    "followersCount": "числовой показатель с датой измерения (требование домена: числа и квалификатор времени)",
    "followersDate": "квалификатор времени для followersCount",
    "activeFromYear": "дата начала карьеры - временное свойство основного класса (требование: даты)",
    "activeUntilYear": "дата окончания карьеры - временное свойство основного класса (требование: даты)",
    "childrenCount": "числовое свойство основного класса (требование: числа)",
    "officialWebsite": "ссылка на внешний источник сведений о сущности (не вопрос, а provenance)",
    "wikipediaRu": "ссылка на русскую статью - источник текста для корпуса (task5); параллель к wikipediaEn",
    "rsRank": "место в списке Rolling Stone - основание принадлежности сущности к домену",
    "Agent": "надкласс иерархии (Person, Organization); нужен для domain у wikipediaEn/wikipediaRu/officialWebsite",
    "MusicalGroup": "подкласс Organization для групп; значения memberOf (Q4) - группы, класс уточняет их тип",
    "RecordLabel": "тип значений recordLabel", "Country": "тип значений citizenship", "Place": "тип значений birthPlace",
    "Genre": "тип значений genre", "Occupation": "тип значений occupation", "Instrument": "тип значений playsInstrument",
    "Award": "тип значений award", "FollowersSnapshot": "тип узла-замера подписчиков (hasFollowers)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onto", default=str(C.ONTOLOGY_TTL))
    ap.add_argument("--out", default=str(OUT_DIR))
    a = ap.parse_args()
    g = Graph()
    g.parse(a.onto, format="turtle")
    print(f"Онтология загружена: {len(g)} троек")

    classes = sorted(c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef))
    oprops = sorted(g.subjects(RDF.type, OWL.ObjectProperty))
    dprops = sorted(g.subjects(RDF.type, OWL.DatatypeProperty))
    funcs = set(g.subjects(RDF.type, OWL.FunctionalProperty))
    res = []   # (требование, выполнено, детали)

    def add(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    # 1. классы и иерархия
    sub = [(c, p) for c in classes for p in g.objects(c, RDFS.subClassOf) if p in classes]
    add("не меньше 5 классов", len(classes) >= 5, f"классов: {len(classes)}")
    add("есть иерархия классов", len(sub) > 0, f"отношений subClassOf: {len(sub)}")
    # 2. свойства
    add("есть object- и datatype-свойства", oprops and dprops, f"object: {len(oprops)}, datatype: {len(dprops)}")
    props = oprops + dprops
    no_dom = [local(p) for p in props if not any(True for _ in g.objects(p, RDFS.domain))]
    no_rng = [local(p) for p in props if not any(True for _ in g.objects(p, RDFS.range))]
    add("у всех свойств указан domain", not no_dom, ", ".join(no_dom))
    add("у всех свойств указан range", not no_rng, ", ".join(no_rng))
    add("есть функциональное свойство", len(funcs) > 0, f"функциональных: {len(funcs)}")
    # 3. подписи
    def has_lang(s, pred, lang):
        return any(isinstance(o, Literal) and o.language == lang for o in g.objects(s, pred))
    bad = []
    for e in classes + props:
        miss = []
        if not has_lang(e, RDFS.label, "ru"): miss.append("label@ru")
        if not has_lang(e, RDFS.label, "en"): miss.append("label@en")
        if not any(True for _ in g.objects(e, RDFS.comment)): miss.append("comment")
        if miss: bad.append(f"{local(e)} ({', '.join(miss)})")
    add("у всех классов и свойств есть label (ru, en) и comment", not bad, "; ".join(bad))
    # 4. пространство имён
    foreign = [str(e) for e in classes + props if not str(e).startswith(NS)]
    add("все классы и свойства в собственном пространстве имён", not foreign, "; ".join(foreign))
    # 5. домены и диапазоны ссылаются на свои классы
    wrong = []
    for p in props:
        for o in list(g.objects(p, RDFS.domain)) + [r for r in g.objects(p, RDFS.range) if p in oprops]:
            if isinstance(o, URIRef) and o not in classes:
                wrong.append(f"{local(p)} -> {o}")
    add("domain/range объектных свойств - классы онтологии", not wrong, "; ".join(wrong))
    # 6. equivalent*
    eqc = [(local(c), str(o)) for c in classes for o in g.objects(c, OWL.equivalentClass)]
    eqp = [(local(p), str(o)) for p in props for o in g.objects(p, OWL.equivalentProperty)]
    add("указаны owl:equivalentClass / owl:equivalentProperty к Wikidata", eqc and eqp,
        f"классов: {len(eqc)}, свойств: {len(eqp)}")
    # 7. использование в вопросах
    used_p = {p for _, ps in USAGE.values() for p in ps}
    used_c = {c for cs, _ in USAGE.values() for c in cs}
    unknown = sorted((used_p | used_c) - {local(e) for e in classes + props})
    add("всё упомянутое в таблице вопросов есть в онтологии", not unknown, ", ".join(unknown))
    unused_p = sorted(local(p) for p in props if local(p) not in used_p)
    unused_c = sorted(local(c) for c in classes if local(c) not in used_c)

    ok_all = all(r[1] for r in res)
    md = ["# Проверка онтологии (задание 3)", "", f"Файл: `{a.onto}`", "",
          "| требование | результат | детали |", "|---|---|---|",
          *[f"| {n} | {'выполнено' if ok else 'НАРУШЕНО'} | {d} |" for n, ok, d in res], "",
          "## Классы и свойства по вопросам", "", "| вопрос | классы | свойства |", "|---|---|---|",
          *[f"| {q} | {', '.join(cs)} | {', '.join(ps)} |" for q, (cs, ps) in USAGE.items()], "",
          "## Не используются в вопросах (нужно пояснение в отчёте)", "",
          "| элемент | зачем нужен (черновик пояснения) |", "|---|---|",
          *[f"| {n} | {EXPLAIN.get(n, 'ПОЯСНЕНИЕ НЕ ЗАДАНО - объяснить или удалить из онтологии')} |" for n in unused_p + unused_c], ""]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "ontology_check.md").write_text("\n".join(md), encoding="utf-8")
    for n, ok, d in res:
        print(f"[{'OK' if ok else 'НАРУШЕНО'}] {n}" + (f": {d}" if d else ""))
    print(f"\nСвойства без вопросов ({len(unused_p)}): {unused_p}\nКлассы без вопросов ({len(unused_c)}): {unused_c}")
    nox = [n for n in unused_p + unused_c if n not in EXPLAIN]
    if nox:
        print("НЕТ ПОЯСНЕНИЯ для:", nox)
        ok_all = False
    print("ИТОГ:", "все требования выполнены" if ok_all else "есть нарушения")
    return 0 if ok_all else 1


if __name__ == "__main__":
    with runlog.session(__file__, inputs=[C.ONTOLOGY_TTL], outputs=[OUT_DIR / "ontology_check.md"]):
        sys.exit(main())
