#!/usr/bin/env python3
"""
ЗАДАНИЕ 3 (построение). Генерирует СТАРТОВУЮ онтологию data/ontology.ttl в собственном пространстве имён.

Дальше файл открывается в Protégé и дорабатывается вручную (скриншоты - в отчёт).
ЗАЩИТА ОТ ПЕРЕЗАПИСИ: если data/ontology.ttl уже есть (например, сохранён из Protégé), скрипт ничего не трогает;
чтобы пересоздать заново - ключ --force.

Запуск:   uv run scripts/task3_build_ontology.py [--force] [--out data/ontology.ttl]
Проверка требований и таблица «вопрос -> классы/свойства» - в task3_check_ontology.py.
"""
import argparse
import sys
from pathlib import Path

import common as C
import runlog
from common import TTL, lit, ONT

# ============================ ОНТОЛОГИЯ (единый источник правды) ============================
# (имя, родитель, label_en, label_ru, comment_en, comment_ru, wikidata-эквивалент)
CLASSES = [
    ("Agent", None, "Agent", "Агент", "A person or an organisation.", "Человек или организация.", None),
    ("Person", "Agent", "Person", "Человек", "A human being.", "Человек.", "Q5"),
    ("Musician", "Person", "Musician", "Музыкант", "A person from the Rolling Stone list of greatest artists (domain class).",
     "Человек из списка величайших исполнителей Rolling Stone (основной класс домена).", None),
    ("Organization", "Agent", "Organization", "Организация", "An organised group of people.", "Организованная группа людей.", None),
    ("MusicalGroup", "Organization", "Musical group", "Музыкальная группа", "A band or other musical ensemble.",
     "Музыкальная группа или ансамбль.", "Q215380"),
    ("RecordLabel", "Organization", "Record label", "Звукозаписывающий лейбл", "A company that releases recordings.",
     "Компания, выпускающая музыкальные записи.", "Q18127"),
    ("Place", None, "Place", "Место", "A geographic location, e.g. a city.", "Географический объект, например город.", "Q17334923"),
    ("Country", "Place", "Country", "Страна", "A sovereign state.", "Государство.", "Q6256"),
    ("Genre", None, "Music genre", "Музыкальный жанр", "A musical genre.", "Музыкальный жанр.", "Q188451"),
    ("Occupation", None, "Occupation", "Род занятий", "A profession or occupation.", "Профессия или род занятий.", "Q12737077"),
    ("Instrument", None, "Musical instrument", "Музыкальный инструмент", "An instrument a musician plays.",
     "Инструмент, на котором играет музыкант.", "Q34379"),
    ("Award", None, "Award", "Награда", "An award or prize.", "Награда или премия.", "Q618779"),
    ("AwardReceipt", None, "Award receipt", "Получение награды", "A fact that a musician received an award (with a year).",
     "Факт получения музыкантом награды (с годом).", None),
    ("Marriage", None, "Marriage", "Брак", "A marriage of a person (with optional start and end dates).",
     "Брак человека (с необязательными датами начала и конца).", None),
    ("FollowersSnapshot", None, "Followers snapshot", "Число подписчиков на дату",
     "Number of social-media followers at a point in time.", "Число подписчиков в соцсети на определённую дату.", None),
]

# (имя, тип obj/data, domain, range, functional, label_en, label_ru, comment_en, comment_ru, wikidata-свойство)
PROPS = [
    ("birthPlace", "obj", "Musician", "Place", True, "birth place", "место рождения", "Place where the person was born.", "Место, где родился человек.", "P19"),
    ("citizenship", "obj", "Person", "Country", False, "citizenship", "гражданство", "Country of citizenship.", "Страна гражданства.", "P27"),
    ("occupation", "obj", "Person", "Occupation", False, "occupation", "род занятий", "Occupation of the person.", "Род занятий человека.", "P106"),
    ("genre", "obj", "Musician", "Genre", False, "genre", "жанр", "Genre the musician works in.", "Жанр, в котором работает музыкант.", "P136"),
    ("recordLabel", "obj", "Musician", "RecordLabel", False, "record label", "лейбл", "Label the musician recorded for.", "Лейбл, на котором записывался музыкант.", "P264"),
    ("memberOf", "obj", "Musician", "Organization", False, "member of", "член организации/группы", "Organization or band the musician is or was a member of.", "Организация или группа, в которой состоит или состоял музыкант.", "P463"),
    ("playsInstrument", "obj", "Musician", "Instrument", False, "plays instrument", "играет на инструменте", "Instrument the musician plays.", "Инструмент, на котором играет музыкант.", "P1303"),
    ("hasAwardReceipt", "obj", "Musician", "AwardReceipt", False, "has award receipt", "имеет получение награды", "Links a musician to an award receipt.", "Связывает музыканта с фактом получения награды.", None),
    ("award", "obj", "AwardReceipt", "Award", True, "award", "награда", "The award that was received.", "Полученная награда.", None),
    ("hasMarriage", "obj", "Person", "Marriage", False, "has marriage", "имеет брак", "Links a person to a marriage.", "Связывает человека с браком.", None),
    ("spouse", "obj", "Marriage", "Person", True, "spouse", "супруг(а)", "The partner in the marriage.", "Партнёр в браке.", None),
    ("hasFollowers", "obj", "Musician", "FollowersSnapshot", False, "has followers snapshot", "имеет данные о подписчиках", "Links a musician to a followers count at a date.", "Связывает музыканта с числом подписчиков на дату.", None),
    ("birthDate", "data", "Person", "date", True, "birth date", "дата рождения", "Date of birth.", "Дата рождения.", "P569"),
    ("deathDate", "data", "Person", "date", True, "death date", "дата смерти", "Date of death.", "Дата смерти.", "P570"),
    ("activeFromYear", "data", "Musician", "gYear", False, "active from (year)", "активен с (год)", "Year the career started.", "Год начала карьеры.", "P2031"),
    ("activeUntilYear", "data", "Musician", "gYear", False, "active until (year)", "активен до (год)", "Year the career ended.", "Год окончания карьеры.", "P2032"),
    ("heightCm", "data", "Person", "decimal", True, "height (cm)", "рост (см)", "Height in centimetres.", "Рост в сантиметрах.", "P2048"),
    ("childrenCount", "data", "Person", "integer", True, "number of children", "число детей", "Number of children.", "Число детей.", "P1971"),
    ("awardYear", "data", "AwardReceipt", "gYear", False, "award year", "год награды", "Year the award was received.", "Год получения награды.", None),
    ("marriageStart", "data", "Marriage", "date", False, "marriage start", "начало брака", "Start date of the marriage.", "Дата начала брака.", None),
    ("marriageEnd", "data", "Marriage", "date", False, "marriage end", "конец брака", "End date of the marriage.", "Дата окончания брака.", None),
    ("followersCount", "data", "FollowersSnapshot", "integer", True, "followers count", "число подписчиков", "Number of followers.", "Число подписчиков.", "P8687"),
    ("followersDate", "data", "FollowersSnapshot", "date", True, "followers date", "дата измерения подписчиков", "Date the followers count was measured.", "Дата, на которую измерено число подписчиков.", None),
    ("officialWebsite", "data", "Agent", "anyURI", False, "official website", "официальный сайт", "Official website URL.", "Адрес официального сайта.", "P856"),
    ("wikipediaEn", "data", "Agent", "anyURI", True, "English Wikipedia", "статья в англ. Википедии", "URL of the English Wikipedia article.", "Ссылка на статью в английской Википедии.", None),
    ("wikipediaRu", "data", "Agent", "anyURI", True, "Russian Wikipedia", "статья в рус. Википедии", "URL of the Russian Wikipedia article.", "Ссылка на статью в русской Википедии.", None),
    ("rsRank", "data", "Musician", "integer", True, "Rolling Stone rank", "место в списке Rolling Stone", "Rank in the Rolling Stone list (1-100).", "Место в списке Rolling Stone (1-100).", None),
]
PROP = {p[0]: p for p in PROPS}


def build_ontology():
    g = TTL()
    g.add("<" + ONT.rstrip("#") + ">", "a", "owl:Ontology")
    g.add("<" + ONT.rstrip("#") + ">", "rdfs:label", lit("RS100 musicians ontology", lang="en"))
    g.add("<" + ONT.rstrip("#") + ">", "rdfs:label", lit("Онтология музыкантов RS100", lang="ru"))
    for name, parent, len_, lru, cen, cru, wdq in CLASSES:
        c = f":{name}"
        g.add(c, "a", "owl:Class")
        if parent:
            g.add(c, "rdfs:subClassOf", f":{parent}")
        g.add(c, "rdfs:label", lit(len_, lang="en")); g.add(c, "rdfs:label", lit(lru, lang="ru"))
        g.add(c, "rdfs:comment", lit(cen, lang="en")); g.add(c, "rdfs:comment", lit(cru, lang="ru"))
        if wdq:
            g.add(c, "owl:equivalentClass", f"wd:{wdq}")
    for name, kind, dom, rng, func, len_, lru, cen, cru, wdp in PROPS:
        p = f":{name}"
        g.add(p, "a", "owl:ObjectProperty" if kind == "obj" else "owl:DatatypeProperty")
        if func:
            g.add(p, "a", "owl:FunctionalProperty")
        g.add(p, "rdfs:domain", f":{dom}")
        g.add(p, "rdfs:range", f":{rng}" if kind == "obj" else f"xsd:{rng}")
        g.add(p, "rdfs:label", lit(len_, lang="en")); g.add(p, "rdfs:label", lit(lru, lang="ru"))
        g.add(p, "rdfs:comment", lit(cen, lang="en")); g.add(p, "rdfs:comment", lit(cru, lang="ru"))
        if wdp:
            g.add(p, "owl:equivalentProperty", f"wdt:{wdp}")
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(C.ONTOLOGY_TTL))
    ap.add_argument("--force", action="store_true", help="перезаписать существующий файл")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists() and not a.force:
        print(f"{out} уже существует (возможно, правился в Protégé) - не перезаписываю. Ключ --force пересоздаёт файл.")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    onto = build_ontology()
    onto.dump(out, "# Стартовая онтология (сгенерирована task3_build_ontology.py). Откройте в Protégé и доработайте.")
    print(f"Онтология записана: {out}; троек: {len(onto.triples)}; классов: {len(CLASSES)}; свойств: {len(PROPS)}")
    return 0


if __name__ == "__main__":
    with runlog.session(__file__, outputs=[C.ONTOLOGY_TTL]):
        sys.exit(main())
