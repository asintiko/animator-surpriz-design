# Search — умный поиск в каталоге

API: `GET /api/catalog/search?q=...` — вызывает `list_characters_for_public(search=q)` → `filter_characters_by_search` + `sort_characters_for_search`.

## Что понимает

- **Кириллица ↔ латиница**: `Спайдермен` ↔ `spiderman` ↔ `spaydermen`
- **Синонимы**: `паук` → находит «Спайдермен», `ladybug` ↔ `леди баг`, `elsa` ↔ `эльза`
- **Опечатки** (от 5 символов, max 1 правка): `spaderman`, `spidrman` → Спайдермен
- **Регистр**: `SPIDER` = `spider`
- **Несколько токенов**: `чел паук` → находит «Спайдермен»

## Архитектура (catalog_store.py)

```
query → _expand_query_variants(q) → set вариантов:
   • normalize_search_text (lat→cyr→ascii→слитно)
   • _latin_to_cyrillic (для англ. ввода)
   • _SYNONYM_INDEX[token] (синонимы по группам)

document → _character_search_haystack:
   • name + slug + description + categories + tags + search_terms
   • + синонимы каждого токена документа (двунаправленность)

match: вариант ∈ haystack OR fuzzy (Levenshtein ≤1, len≥5)

ranking: имя-точно > имя-старт > имя-substr > синоним-в-имени > slug > terms > haystack
```

## Где править

- Список синонимов: `core/catalog_store.py` → `_SYNONYM_PAIRS`
- Чувствительность fuzzy: `_fuzzy_contains` (порог `len ≥ 5`, `max_edit ≤ 1`)
- Поля в haystack: `_character_search_haystack`

## Тест на проде

```bash
for q in "паук" "spider" "spaderman" "ladybug" "леди баг" "elsa"; do
  enc=$(python3 -c "from urllib.parse import quote; print(quote('$q'))")
  echo "=== $q ==="
  curl -sS "https://animator-surpriz.uz/api/catalog/search?q=$enc" | jq -r '.total, .items[].name'
done
```

## Связано

- [[Catalog]] — UI `/catalog/`
- [[Architecture]]
