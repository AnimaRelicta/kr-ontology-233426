# КР1. Онтология и база знаний: исполнители из списка Rolling Stone 100

Домен: **люди** (Q5) из списка «100 величайших исполнителей всех времён по версии Rolling Stone»
([ru.wikipedia](https://ru.wikipedia.org/wiki/100_величайших_исполнителей_всех_времён_по_версии_журнала_Rolling_Stone)).
Группы из списка отбрасываются, остаётся ~53 человека (требование КР: 30–60 сущностей одного класса).
Источник данных: [Wikidata Query Service](https://query.wikidata.org/) и API Wikidata/Википедии. Текст задания: `docs/task_description.docx`.

## Ссылка на гугл диск

https://drive.google.com/drive/folders/1j3k5vkK4p3Lm6mAe53A5HKl5H93SHfDc?usp=sharing

## Структура проекта

```
scripts/
  common.py                  общий модуль: пути, адреса API, сеть, кэш, запись Turtle
  runlog.py                  лог запуска (доказательство, что скрипт запускался) -> logs/
  task1_collect_domain.py    ЗАДАНИЕ 1: домен (список -> QID -> только люди)        -> data/domain.csv
  task1_check_domain.py      ЗАДАНИЕ 1: SPARQL-проверка домена (заполненность, квалификаторы времени)
  task2_questions.py         ЗАДАНИЕ 2: банк из 12 вопросов + эталоны + сверка с графом и корпусом
  task3_build_ontology.py    ЗАДАНИЕ 3: стартовая онтология (затем правится в Protégé) -> data/ontology.ttl
  task3_check_ontology.py    ЗАДАНИЕ 3: проверка требований + таблица «вопрос -> классы/свойства»
  task4_build_graph.py       ЗАДАНИЕ 4: выгрузка из Wikidata и описание онтологией      -> data/graph.ttl
  task4_graph_stats.py       ЗАДАНИЕ 4: статистика графа (тройки, сущности, классы, свойства)
  task5_build_corpus.py      ЗАДАНИЕ 5: тексты статей Википедии (ru/en)                  -> data/corpus.jsonl
  task5_check_corpus.py      ЗАДАНИЕ 5: проверка корпуса, таблица «сущность -> источник»
  task6_validate_and_infer.py ЗАДАНИЕ 6: SHACL (pyshacl) + логический вывод (owlrl)
shapes/task6_shapes.ttl      ограничения SHACL (исходник задания 6)
data/                        результаты сборки: domain.csv, ontology.ttl, graph.ttl, corpus.jsonl (data/cache/ - кэш)
reports/task*_*/             отчёты скриптов (для вставки в docx)
logs/                        логи запусков
run_all.sh                   запуск всей цепочки одной командой
docs/task_description.docx   условие
```

## Подготовка

Нужен [uv](https://docs.astral.sh/uv/) и Python ≥ 3.14 (см. `pyproject.toml`; зависимости ставятся автоматически при `uv run`).
Все команды — **из корня проекта**. Необязательно, но желательно указать контакт для заголовка User-Agent
(Wikimedia требует идентифицировать клиента):

```bash
export KR_CONTACT="ваш-email-или-ссылка"      # Windows PowerShell:  $env:KR_CONTACT="..."
```

## Порядок запуска и параметры

Один раз целиком: `bash run_all.sh`. Либо по шагам — **порядок важен**, у каждого шага указано, что нужно до него.

| № | команда | параметры | что нужно до этого | результат |
|---|---|---|---|---|
| 1 | `uv run scripts/task1_collect_domain.py` | — (необязательно положить `data/rs100_manual.csv` с колонкой `title`, если парсинг статьи даст не 100 строк) | сеть | `data/domain.csv` |
| 2 | `uv run scripts/task3_build_ontology.py` | `--force` — пересоздать, `--out путь` | — | `data/ontology.ttl` |
| 3 | **Protégé**: открыть `data/ontology.ttl`, доработать, сохранить в Turtle под тем же именем | — | шаг 2 | `data/ontology.ttl` + скриншоты |
| 4 | `uv run scripts/task4_build_graph.py` | — | шаг 1 | `data/graph.ttl` |
| 5 | `uv run scripts/task5_build_corpus.py` | — | шаг 1 | `data/corpus.jsonl` |
| 6 | `uv run scripts/task1_check_domain.py` | `--discover` — искать квалификаторы времени у всех свойств (тяжёлый запрос); `--domain`, `--corpus`, `--out` | шаги 1, 5 | `reports/task1_domain/` |
| 7 | `uv run scripts/task3_check_ontology.py` | `--onto путь` | шаг 3 | `reports/task3_ontology/` |
| 8 | `uv run scripts/task4_graph_stats.py` | `--graph`, `--onto`, `--out` | шаги 3, 4 | `reports/task4_graph/` |
| 9 | `uv run scripts/task5_check_corpus.py` | `--corpus`, `--domain`, `--out` | шаги 1, 5 | `reports/task5_corpus/` |
| 10 | `uv run scripts/task2_questions.py` | `--graph`, `--onto`, `--corpus` | шаги 3, 4, 5 | `reports/task2_questions/` |
| 11 | `uv run scripts/task6_validate_and_infer.py` | `--rdfs` — RDFS-семантика вместо OWL RL (быстрее) | шаги 3, 4 | `reports/task6_validation/` |

Замечания:
- Шаг 2 **не перезаписывает** существующий `data/ontology.ttl` (чтобы не потерять правки из Protégé) — только с `--force`.
- Сбор (шаги 1, 4, 5) кэширует ответы в `data/cache/`: повторный запуск не ходит в сеть за уже скачанным.
- Каждый скрипт пишет лог в `logs/<скрипт>_<дата-время>.log` (команда, версии, SHA-256 входов/выходов, весь вывод) и строку в `logs/runs.jsonl`.
- Код возврата 1 означает, что проверка нашла нарушения (см. вывод и `reports/`).
- Если `task2_questions.py` показывает РАСХОЖДЕНИЕ, данные в Wikidata/Википедии могли измениться с момента выбора эталонов:
  проверьте вручную и обновите эталон в `QUESTIONS` (в самом скрипте).

## Что где требует задание

| задание КР | баллы | скрипты | что вставить в отчёт |
|---|---|---|---|
| 1. Домен | 1 | task1_collect_domain, task1_check_domain | `reports/task1_domain/domain_check.md` (итог по требованиям, доли заполненности, свойства с квалификатором времени, SPARQL-запросы), `text_sources.csv` (ссылка на источник текста для каждой сущности); запись о домене в общей таблице группы |
| 2. Вопросы | 1 | task2_questions | `reports/task2_questions/questions_report.md` (12 вопросов: тип, эталон, цитата+ссылка, причина отсутствия в графе, граф/текст-части) |
| 3. Онтология | 0,5 | task3_build_ontology (+ Protégé), task3_check_ontology | `reports/task3_ontology/ontology_check.md` (требования, таблица «вопрос → классы/свойства», пояснения к неиспользуемым), скриншоты Protégé, `data/ontology.ttl` |
| 4. Граф | 0,5 | task4_build_graph, task4_graph_stats | `reports/task4_graph/graph_stats.md` (тройки, сущности, классы, свойства), `data/graph.ttl` |
| 5. Корпус | 0,5 | task5_build_corpus, task5_check_corpus | `reports/task5_corpus/corpus_stats.md`, `data/corpus.jsonl` |
| 6. Проверка и вывод | 0,5 | task6_validate_and_infer | `reports/task6_validation/validation_summary.md` (+ `shacl_report.ttl`, `inferred_triples.ttl`) |

## Файлы для сдачи и для составления отчёта

**Исходники (архив):** `scripts/`, `shapes/task6_shapes.ttl`, `data/ontology.ttl`, `data/graph.ttl`, `data/corpus.jsonl`,
`data/domain.csv`, `README.md`, `pyproject.toml`, `uv.lock`, `run_all.sh`.

**Отчёты и доказательства запуска:** вся папка `reports/` и `logs/` (достаточно по одному последнему логу каждого скрипта + `logs/runs.jsonl`).
