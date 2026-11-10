#!/usr/bin/env bash
# Последовательный запуск всех заданий КР из корня проекта:  bash run_all.sh
# Перед запуском (по желанию):  export KR_CONTACT="ваш-email-или-ссылка"   # попадает в User-Agent запросов к Википедии/Wikidata
# Между task3 и task4 откройте data/ontology.ttl в Protégé, доработайте и сохраните (Turtle) под тем же именем.
set -euo pipefail
cd "$(dirname "$0")"

uv run scripts/task1_collect_domain.py      # 1. домен -> data/domain.csv
uv run scripts/task3_build_ontology.py      # 3. стартовая онтология -> data/ontology.ttl (существующий файл не трогает)
uv run scripts/task4_build_graph.py         # 4. граф из Wikidata -> data/graph.ttl
uv run scripts/task5_build_corpus.py        # 5. корпус текстов -> data/corpus.jsonl
uv run scripts/task1_check_domain.py        # 1. проверка домена SPARQL-запросами -> reports/task1_domain/
uv run scripts/task3_check_ontology.py      # 3. проверка онтологии -> reports/task3_ontology/
uv run scripts/task4_graph_stats.py         # 4. статистика графа -> reports/task4_graph/
uv run scripts/task5_check_corpus.py        # 5. проверка корпуса -> reports/task5_corpus/
uv run scripts/task2_questions.py           # 2. вопросы и эталоны -> reports/task2_questions/
uv run scripts/task6_validate_and_infer.py  # 6. SHACL + owlrl -> reports/task6_validation/

echo
echo "=== Файлы для отчёта ==="
ls -1 data/ontology.ttl data/graph.ttl data/corpus.jsonl data/domain.csv shapes/task6_shapes.ttl 2>/dev/null
find reports -type f | sort
ls -1 logs/*.log 2>/dev/null | tail -n 12
