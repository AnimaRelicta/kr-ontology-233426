#!/usr/bin/env python3
"""
ЗАДАНИЕ 2. 12 вопросов к базе знаний: 6 графовых, 4 текстовых, 2 комбинированных.

Здесь ЕДИНЫЙ банк вопросов (QUESTIONS): формулировка, тип, эталонный ответ, SPARQL-запрос, цитата и источник,
причина отсутствия ответа в графе, какие классы/свойства онтологии используются.
Скрипт:
  - выполняет графовые запросы к data/graph.ttl и сверяет результат с эталоном;
  - проверяет, что цитаты для текстовых вопросов дословно есть в data/corpus.jsonl;
  - для комбинированных вопросов вычисляет графовую часть и достаёт текстовую часть;
  - пишет reports/task2_questions/questions_report.md (готовая таблица для отчёта) и questions_results.json.
Банк вопросов импортирует task3_check_ontology.py (таблица «вопрос -> классы/свойства»).

Запуск:  uv run scripts/task2_questions.py [--graph ...] [--onto ...] [--corpus ...]
Нужен rdflib. Предварительно: task3, task4, task5.
ВАЖНО: эталоны вопросов 1-6 и QID в 7-12 взяты из первой версии работы; если после перевыгрузки данных ответы
изменились (Википедия/Wikidata правятся), скрипт покажет РАСХОЖДЕНИЕ - обновите эталон и перепроверьте вручную.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import common as C
import runlog

PFX = """PREFIX : <http://example.org/rs100/onto#>
PREFIX res: <http://example.org/rs100/res/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
OUT_DIR = C.REPORTS / "task2_questions"


def RU(s, v="?name"):
    """Метка на русском, а если русской нет - на английском (напр. у Jay-Z только en)."""
    return (f'(lang({v})="ru" || (lang({v})="en" && NOT EXISTS {{ {s} rdfs:label ?x . FILTER(lang(?x)="ru") }}))')


Q_YOUNGEST_DEAD = ('SELECT ?m ?name ?b ?d ?en WHERE { ?m a :Musician ; rdfs:label ?name ; :birthDate ?b ; :deathDate ?d . '
                   'OPTIONAL { ?m :wikipediaEn ?en } FILTER(' + RU('?m') + ') }')
Q_TOP_AWARDS = ('SELECT ?m ?name (COUNT(?r) AS ?n) WHERE { ?m a :Musician ; rdfs:label ?name ; :hasAwardReceipt ?r . '
                'FILTER(' + RU('?m') + ') } GROUP BY ?m ?name ORDER BY DESC(?n) LIMIT 1')

# ---------------------------------------------------------------------------------------------
# Графовые вопросы 1-6: id, тип, текст, SPARQL, приведение результата, эталон (машинный), эталон (для отчёта)
# ---------------------------------------------------------------------------------------------
GRAPH_Q = [
    dict(id=1, kind="фильтр по дате", text="Кто из музыкантов родился 1 января 1960 года или позже?",
         sparql='SELECT ?name WHERE { ?m a :Musician ; rdfs:label ?name ; :birthDate ?d . '
                'FILTER(?d >= "1960-01-01"^^xsd:date && ' + RU('?m') + ') } ORDER BY ?d',
         conv=lambda r: [str(x[0]) for x in r],
         ref=["Доктор Дре", "JAŸ‐Z", "Тупак Шакур", "Эминем"],
         ref_text="Доктор Дре, JAŸ‐Z, Тупак Шакур, Эминем",
         classes=["Musician"], props=["birthDate"]),
    dict(id=2, kind="агрегация", text="Сколько музыкантов в базе всего и сколько из них умерли?",
         sparql='SELECT (COUNT(DISTINCT ?m) AS ?total) (COUNT(DISTINCT ?dead) AS ?dead_n) WHERE '
                '{ ?m a :Musician . OPTIONAL { ?m :deathDate ?dd . BIND(?m AS ?dead) } }',
         conv=lambda r: [int(r[0][0]), int(r[0][1])],
         ref=[53, 34], ref_text="Всего 53, умерли 34",
         classes=["Musician"], props=["deathDate"]),
    dict(id=3, kind="сортировка + агрегация", text="У каких трёх музыкантов больше всего полученных наград?",
         sparql='SELECT ?name (COUNT(?r) AS ?n) WHERE { ?m a :Musician ; rdfs:label ?name ; :hasAwardReceipt ?r . '
                'FILTER(' + RU('?m') + ') } GROUP BY ?name ORDER BY DESC(?n) LIMIT 3',
         conv=lambda r: [(str(x[0]), int(x[1])) for x in r],
         ref=[("Арета Франклин", 44), ("Элтон Джон", 27), ("Боб Дилан", 25)],
         ref_text="Арета Франклин (44), Элтон Джон (27), Боб Дилан (25)",
         classes=["Musician", "AwardReceipt"], props=["hasAwardReceipt"]),
    dict(id=4, kind="многошаговый (2 ребра)", text="Кто из музыкантов списка состоял в той же группе, что и Рой Орбисон?",
         sparql='SELECT DISTINCT ?name WHERE { res:Q188426 :memberOf ?g . ?o a :Musician ; :memberOf ?g ; rdfs:label ?name . '
                'FILTER(?o != res:Q188426 && ' + RU('?o') + ') }',
         conv=lambda r: sorted(str(x[0]) for x in r),
         ref=sorted(["Том Петти", "Боб Дилан"]), ref_text="Том Петти, Боб Дилан",
         classes=["Musician", "Organization"], props=["memberOf"]),
    dict(id=5, kind="квалификатор времени", text="Кто был супругом Джона Леннона в 1970 году?",
         sparql='SELECT ?name WHERE { res:Q1203 :hasMarriage ?mar . ?mar :spouse ?sp ; :marriageStart ?s . '
                'OPTIONAL { ?mar :marriageEnd ?e } ?sp rdfs:label ?name . '
                'FILTER(?s <= "1970-06-30"^^xsd:date && (!BOUND(?e) || ?e >= "1970-06-30"^^xsd:date) && ' + RU('?sp') + ') }',
         conv=lambda r: [str(x[0]) for x in r],
         ref=["Йоко Оно"], ref_text="Йоко Оно",
         classes=["Person", "Marriage"], props=["hasMarriage", "spouse", "marriageStart", "marriageEnd"]),
    dict(id=6, kind="фильтр по числу + сортировка", text="Какие музыканты выше 180 см? Перечислить по убыванию роста.",
         sparql='SELECT ?name ?h WHERE { ?m a :Musician ; rdfs:label ?name ; :heightCm ?h . '
                'FILTER(?h > 180 && ' + RU('?m') + ') } ORDER BY DESC(?h)',
         conv=lambda r: [(str(x[0]), float(x[1])) for x in r],
         ref=[("Джонни Кэш", 188.0), ("Карл Перкинс", 185.0), ("Фрэнк Заппа", 183.0)],
         ref_text="Джонни Кэш (188), Карл Перкинс (185), Фрэнк Заппа (183)",
         classes=["Musician"], props=["heightCm"]),
]

# ---------------------------------------------------------------------------------------------
# Текстовые вопросы 7-10: ответ есть только в тексте статьи
# quotes - фрагменты, которые ДОЛЖНЫ дословно встречаться в тексте документа doc
# ---------------------------------------------------------------------------------------------
TEXT_Q = [
    dict(id=7, kind="текст: причина / история", doc="Q392:enwiki",
         text="Почему публика освистала Боба Дилана на фолк-фестивале в Ньюпорте в 1965 году?",
         ref="Дилан вышел на сцену с электрогитарой, чего фолк-публика не ждала; освистывали фолк-поклонники, "
             "которых он этим отдалил. Он сыграл три песни и ушёл со сцены.",
         quotes=["he was met with cheering and booing and left the stage after three songs",
                 "the boos were from folk fans whom Dylan had alienated by appearing, unexpectedly, with an electric guitar"],
         reason="В графе нет событий, выступлений и реакции публики: только даты, места, награды, браки; "
                "причины и мотивы — это повествование, которого нет в Wikidata-свойствах онтологии.",
         classes=["Musician"], props=["wikipediaEn"]),
    dict(id=8, kind="текст: причина / история", doc="Q409:enwiki",
         text="Что считается причиной нападения на Боба Марли в 1976 году?",
         ref="Нападение произошло за два дня до концерта «Smile Jamaica»; считается, что оно имело политические мотивы, "
             "так как многие воспринимали концерт как митинг в поддержку Майкла Мэнли.",
         quotes=['two days before "Smile Jamaica"',
                 "believed to have been politically motivated, as many felt that Smile Jamaica was actually a support rally for Manley"],
         reason="Мотивы и политический контекст происшествия не представлены в графе: нет класса «событие» и связи "
                "музыканта с такими событиями; ответ — интерпретация в тексте статьи.",
         classes=["Musician"], props=["wikipediaEn"]),
    dict(id=9, kind="текст: причина / история", doc="Q5928:enwiki",
         text="От чего умер Джими Хендрикс?",
         ref="Он задохнулся (асфиксия) от аспирации собственной рвоты, будучи в состоянии интоксикации барбитуратами "
             "(доза превышала рекомендованную в 18 раз).",
         quotes=["aspirated his own vomit and died of asphyxia while intoxicated with barbiturates",
                 "18 times the recommended dosage"],
         reason="В графе есть только дата смерти (deathDate); у онтологии нет свойства «причина смерти», "
                "а обстоятельства смерти описаны только в тексте.",
         classes=["Musician"], props=["wikipediaEn"]),
    dict(id=10, kind="текст: описание / происхождение", doc="Q220707:enwiki",
         text="Откуда у Мадди Уотерса прозвище «Muddy»?",
         ref="Прозвище «Muddy» он получил ещё в детстве, потому что любил играть в грязной воде ручья Дир-Крик.",
         quotes=['gave him the nickname "Muddy" at an early age because he loved to play in the muddy water of nearby Deer Creek'],
         reason="Прозвища и их происхождение не моделируются в онтологии (есть только метки rdfs:label); "
                "история прозвища есть только в тексте.",
         classes=["Musician"], props=["wikipediaEn"]),
]

# ---------------------------------------------------------------------------------------------
# Комбинированные 11-12: сначала граф находит сущность, потом ответ берётся из текста о ней
# ---------------------------------------------------------------------------------------------
COMB_Q = [
    dict(id=11, kind="комбинированный (граф → текст)", doc="Q5977:enwiki", expect_qid="Q5977",
         text="Что известно об обстоятельствах гибели самого молодого из умерших музыкантов списка?",
         graph_part="Среди музыкантов с birthDate и deathDate вычислить возраст на момент смерти и выбрать минимальный "
                    "→ Бадди Холли (Q5977), 22 года; берётся ссылка wikipediaEn на его статью.",
         text_part="В разделе «Death» статьи: самолёт разбился вскоре после взлёта, погибли Холли, Ричи Валенс, Биг Боппер "
                   "и пилот Роджер Питерсон; вылет в плохую погоду, пилот не имел права летать только по приборам.",
         ref="Самый молодой из умерших — Бадди Холли (22 года). Он погиб при крушении самолёта вскоре после взлёта вместе с "
             "Ричи Валенсом, Биг Боппером и пилотом Роджером Питерсоном; самолёт вылетел в плохую погоду, а пилот не был "
             "сертифицирован для полётов только по приборам.",
         quotes=["Soon after takeoff, the plane crashed, killing Holly, Ritchie Valens, the Big Bopper, and pilot Roger Peterson",
                 "took off in inclement weather, even though he was not certified to fly by instruments only"],
         classes=["Musician"], props=["birthDate", "deathDate", "wikipediaEn"]),
    dict(id=12, kind="комбинированный (граф → текст)", doc="Q125121:enwiki", expect_qid="Q125121",
         text="Как началась музыкальная карьера музыканта с наибольшим числом наград?",
         graph_part="Агрегация: по числу hasAwardReceipt выбрать музыканта-лидера → Арета Франклин (Q125121), 44 награды; "
                    "берётся ссылка wikipediaEn.",
         text_part="Из статьи: её заметили благодаря исполнению госпела в баптистской церкви New Bethel в Детройте.",
         ref="Больше всего наград у Ареты Франклин (44). Её заметили как певицу госпела в баптистской церкви New Bethel в Детройте.",
         quotes=["noticed for her gospel singing at New Bethel Baptist Church in Detroit"],
         classes=["Musician", "AwardReceipt"], props=["hasAwardReceipt", "wikipediaEn"]),
]

QUESTIONS = GRAPH_Q + TEXT_Q + COMB_Q
USAGE = {q["id"]: (q["classes"], q["props"]) for q in QUESTIONS}   # для task3_check_ontology.py


def norm(s):
    return re.sub(r"\s+", " ", s.replace("“", '"').replace("”", '"').replace("’", "'")).strip()


def load_corpus(path):
    docs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            docs[d["id"]] = d
    return docs


def age(b, d):
    b, d = date.fromisoformat(b), date.fromisoformat(d)
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def quotes_ok(q, docs):
    text = norm(docs[q["doc"]]["text"]) if q["doc"] in docs else ""
    return [(fr, norm(fr) in text) for fr in q["quotes"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default=str(C.GRAPH_TTL))
    ap.add_argument("--onto", default=str(C.ONTOLOGY_TTL))
    ap.add_argument("--corpus", default=str(C.CORPUS_JSONL))
    a = ap.parse_args()
    from rdflib import Graph
    g = Graph()
    g.parse(a.graph, format="turtle")
    try:
        g.parse(a.onto, format="turtle")
    except Exception as e:
        print("онтология не загружена:", e)
    print(f"Загружено троек: {len(g)}")
    docs = load_corpus(a.corpus)
    ok_all, results = True, {}

    print("\n=== Вопросы 1-6: граф ===")
    for q in GRAPH_Q:
        got = q["conv"](list(g.query(PFX + q["sparql"])))
        ok = got == q["ref"]
        ok_all &= ok
        results[q["id"]] = {"ok": ok, "got": got}
        print(f"[{'OK' if ok else 'РАСХОЖДЕНИЕ'}] Q{q['id']} ({q['kind']}): {q['text']}\n    получено: {got}"
              + ("" if ok else f"\n    эталон:   {q['ref']}"))

    print("\n=== Вопросы 7-10: цитаты в корпусе ===")
    for q in TEXT_Q:
        res = quotes_ok(q, docs)
        ok = all(x for _, x in res)
        ok_all &= ok
        url = docs.get(q["doc"], {}).get("url", "")
        results[q["id"]] = {"ok": ok, "url": url}
        for fr, x in res:
            print(f"[{'OK' if x else 'НЕТ'}] Q{q['id']} {q['doc']}: «{fr[:70]}…»")
        print("      источник:", url)

    print("\n=== Вопросы 11-12: графовая часть + текст ===")
    rows = list(g.query(PFX + Q_YOUNGEST_DEAD))
    youngest = min(rows, key=lambda r: age(str(r[2]), str(r[3])))
    top = list(g.query(PFX + Q_TOP_AWARDS))[0]
    found = {11: (str(youngest[0]).rsplit("/", 1)[-1], f"{youngest[1]}, возраст {age(str(youngest[2]), str(youngest[3]))}"),
             12: (str(top[0]).rsplit("/", 1)[-1], f"{top[1]}, наград {top[2]}")}
    for q in COMB_Q:
        qid, info = found[q["id"]]
        res = quotes_ok(q, docs)
        ok = (qid == q["expect_qid"]) and all(x for _, x in res)
        ok_all &= ok
        url = docs.get(q["doc"], {}).get("url", "")
        results[q["id"]] = {"ok": ok, "graph_found": f"{qid}: {info}", "url": url}
        print(f"[{'OK' if ok else 'РАСХОЖДЕНИЕ'}] Q{q['id']}: граф нашёл {qid} ({info}), ожидался {q['expect_qid']}; "
              f"цитаты: {[x for _, x in res]}\n      источник: {url}")
        if q["id"] == 11 and q["doc"] in docs:
            m = re.search(r"== ?Death ?==(.{0,600})", docs[q["doc"]]["text"], re.S)
            print("      текст («Death»):", (m.group(1) if m else docs[q["doc"]]["text"][:600]).strip()[:600])

    write_report(results)
    print("\nИТОГ:", "всё совпало с эталоном" if ok_all else "есть расхождения")
    return 0 if ok_all else 1


def write_report(results):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    st = lambda i: "совпало" if results.get(i, {}).get("ok") else "РАСХОЖДЕНИЕ"
    md = ["# Вопросы к базе знаний (задание 2)", "",
          "## Вопросы, на которые отвечает граф (1-6)", "",
          "| № | тип | вопрос | эталонный ответ | запуск |", "|---|---|---|---|---|"]
    md += [f"| {q['id']} | {q['kind']} | {q['text']} | {q['ref_text']} | {st(q['id'])} |" for q in GRAPH_Q]
    md += ["", "### SPARQL-запросы к графу", ""]
    for q in GRAPH_Q:
        md += [f"**Q{q['id']}.** {q['text']}", "```sparql", (PFX + q["sparql"]).strip(), "```", ""]
    md += ["## Вопросы, ответ на которые есть только в тексте (7-10)", "",
           "| № | вопрос | эталонный ответ | цитата | источник | почему нет в графе | запуск |", "|---|---|---|---|---|---|---|"]
    for q in TEXT_Q:
        cites = "<br>".join(f"«{c}»" for c in q["quotes"])
        md.append(f"| {q['id']} | {q['text']} | {q['ref']} | {cites} | {results.get(q['id'], {}).get('url', '')} | {q['reason']} | {st(q['id'])} |")
    md += ["", "## Комбинированные вопросы (11-12)", "",
           "| № | вопрос | что берём из графа | что берём из текста | эталонный ответ | источник текста | запуск |", "|---|---|---|---|---|---|---|"]
    for q in COMB_Q:
        md.append(f"| {q['id']} | {q['text']} | {q['graph_part']} | {q['text_part']} | {q['ref']} | {results.get(q['id'], {}).get('url', '')} | {st(q['id'])} |")
    md += ["", "## Какие классы и свойства использует каждый вопрос", "", "| № | классы | свойства |", "|---|---|---|"]
    md += [f"| {q['id']} | {', '.join(q['classes'])} | {', '.join(q['props'])} |" for q in QUESTIONS]
    (OUT_DIR / "questions_report.md").write_text("\n".join(md), encoding="utf-8")
    (OUT_DIR / "questions_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Отчёт: {OUT_DIR / 'questions_report.md'}")


if __name__ == "__main__":
    with runlog.session(__file__, inputs=[C.GRAPH_TTL, C.ONTOLOGY_TTL, C.CORPUS_JSONL],
                        outputs=[OUT_DIR / "questions_report.md", OUT_DIR / "questions_results.json"]):
        sys.exit(main())
