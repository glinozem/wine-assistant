
# Справочник виноделен и обогащение каталога

## Зачем нужен справочник `wineries`

Для работы с каталогом удобно иметь отдельный справочник виноделен, а не дублировать
информацию (регион, сайт, описание) в каждой строке `products`. Для этого введена
таблица `wineries`, где одна строка соответствует одному производителю / винодельне.

Ключевая идея: поле `wineries.supplier` **строго совпадает** с `products.supplier`.
Таким образом, все данные о винодельне можно хранить и обновлять централизованно,
а затем использовать как в API, так и в экспортных отчётах.

## Структура таблицы `wineries`

Таблица создаётся миграцией `0011_wineries.sql` и хранит нормализованную информацию
о винодельне:

- `supplier` — строковый идентификатор винодельни (как в `products.supplier`), `UNIQUE`;
- `supplier_ru` — отображаемое имя винодельни на русском;
- `region` — нормализованный регион (в том числе составные регионы: «Кахети, Гурджаани»);
- `producer_site` — официальный сайт винодельни;
- `description_ru` — развёрнутое описание винодельни на русском (из PDF-каталога);
- служебные поля `id`, `created_at`, `updated_at`.

`wineries` выступает как “source of truth” для текстовых атрибутов винодельни.

## Импорт данных из PDF‑каталога

Для заполнения `wineries` данными из каталога добавлено несколько служебных скриптов
в папке `scripts/`:

- `extract_wineries_from_pdf.py` — парсит `Каталог DW 2025.pdf`, ищет блоки
  вида `Производитель: ...` и вытаскивает:
  - оригинальное имя,
  - русское название,
  - регион,
  - сайт,
  - описание.
  Результат сохраняется в:
  - `data/catalog/wineries_enrichment_from_pdf.xlsx`,
  - `data/catalog/wineries_enrichment_from_pdf_debug.xlsx` (с дополнительной колонкой `_page`).

- `normalize_wineries_suppliers.py` — приводит имена производителей из PDF к точным
  значениям, которые реально встречаются в `products.supplier`
  (например, `Maison Joseph Cattin` → `Cattin`,
  `Lake Road – Origin Wine` → `Lake Road - Origin Wine`,
  `Mangup Estate` → `Мангуп`, `Минский завод игристых вин (МЗИВ)` → `МЗИВ` и т.д.).
  Нормализованный файл сохраняется как
  `data/catalog/wineries_enrichment_from_pdf_norm.xlsx`.

- `check_wineries_vs_products.py` — сравнивает список поставщиков:
  - из нормализованного Excel‑файла,
  - и из базы (`SELECT DISTINCT supplier FROM products`).

  Скрипт показывает:
  - каких поставщиков нет в базе,
  - кого нет в каталоге,
  - а также подсказки по возможному сопоставлению имён (fuzzy‑matching).

## Загрузка справочника виноделен

Непосредственно создание/обновление записей в таблице `wineries` выполняет скрипт
`load_wineries.py`:

- читает `data/catalog/wineries_enrichment_from_pdf_norm.xlsx`;
- для каждого `supplier`:
  - если такого поставщика ещё нет в `wineries` → выполняет `INSERT`,
  - если есть → делает `UPDATE` полей `supplier_ru`, `region`, `producer_site`,
    `description_ru`.

По умолчанию скрипт работает в режиме предварительного просмотра (dry‑run) и ничего
не меняет в базе — он только выводит план действий (что будет вставлено/обновлено).

Для применения изменений используется флаг `--apply`, например:

```bash
python -m scripts.load_wineries --excel ".\data\catalog\wineries_enrichment_from_pdf_norm.xlsx"
python -m scripts.load_wineries --excel ".\data\catalog\wineries_enrichment_from_pdf_norm.xlsx" --apply
```

После выполнения скрипта таблица `wineries` содержит полный перечень виноделен
из PDF‑каталога, согласованный с `products.supplier`.

## Синхронизация `products` с `wineries`

После заполнения `wineries` продукты можно дообогатить нормализованными регионами:

```sql
UPDATE products p
SET region = w.region
FROM wineries w
WHERE p.supplier = w.supplier
  AND p.region IS NULL
  AND w.region IS NOT NULL;
```

Аналогичным образом при необходимости можно массово обновлять `producer_site`
и другие поля.

Итог:

- `products.region` и `products.producer_site` больше не “живут сами по себе”,
  а синхронизированы со справочником `wineries`;
- API и экспорт могут использовать как данные конкретного SKU, так и общие данные
  по винодельне (русское имя, регион, сайт, длинное описание).
