# Дополнения к README: история остатков и графики

Этот файл содержит новые разделы для README по работе с историей остатков
(`inventory_history`), автоматизацией синхронизации и построением графиков
цен/остатков в UI.

Вы можете либо включить его целиком в основной `README.md`, либо разбить
на несколько подразделов в нужных местах.

---

## Ежедневная синхронизация остатков

История остатков хранится в таблице `inventory_history` и используется для
построения графиков и аналитики (эндпоинты
`/api/v1/sku/<code>/inventory-history` и `/export/inventory-history/...`).

Технически ежедневный снимок формируется из текущих остатков в таблице
`inventory` с помощью скрипта:

```bash
python scripts/sync_inventory_history.py
```

Для удобства в `Makefile` есть две цели:

```bash
make sync-inventory-history-dry-run   # посмотреть, сколько записей будет добавлено (без изменений в БД)
make sync-inventory-history           # выполнить синхронизацию (создать снимок в inventory_history)
```

Под капотом скрипт:

- читает текущие остатки из `inventory`;
- вставляет записи в `inventory_history` с полями `code`, `stock_total`,
  `stock_free`, `reserved`, `as_of`;
- гарантирует не более **одного снимка в день** для пары (`code`, `as_of::date`).

### Автоматический запуск: Windows Task Scheduler

На Windows рекомендовано запускать синхронизацию **1 раз в день**, например,
ночью после обновления прайса.

Базовая команда, которую должен выполнять планировщик:

```powershell
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant
make sync-inventory-history
```

Общий сценарий настройки (через «Планировщик заданий»):

1. Открыть **Task Scheduler** (Планировщик заданий).
2. Создать задачу (Create Task…).
3. На вкладке **Triggers**:
   - добавить триггер «Раз в день», время — например, `03:00`.
4. На вкладке **Actions**:
   - Action: *Start a program*;
   - Program/script: `powershell.exe`
   - Arguments (пример):

     ```text
     -NoProfile -ExecutionPolicy Bypass -Command "cd 'D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant'; make sync-inventory-history"
     ```

5. Сохранить задачу и протестировать запуск вручную («Run»).

### (Опционально) Cron-подобный запуск в Linux

Если проект крутится на Linux/WSL, можно использовать `cron`:

```bash
crontab -e
```

И добавить, например, строку:

```cron
0 3 * * * cd /opt/wine-assistant && make sync-inventory-history >> /var/log/wine-assistant-sync.log 2>&1
```

Это запустит `make sync-inventory-history` каждый день в 03:00.

---

## Как посмотреть, что в `inventory_history`

После запуска ежедневной синхронизации имеет смысл уметь быстро проверить,
что данные действительно пишутся в `inventory_history` и доступны через API.

### Через SQL (psql / Adminer)

Посмотреть последние N записей по всей таблице:

```sql
SELECT
    code,
    stock_total,
    stock_free,
    reserved,
    as_of
FROM public.inventory_history
ORDER BY as_of DESC
LIMIT 50;
```

История по конкретному SKU:

```sql
SELECT
    code,
    stock_total,
    stock_free,
    reserved,
    as_of
FROM public.inventory_history
WHERE code = 'D010210'
ORDER BY as_of DESC
LIMIT 50;
```

История за конкретный диапазон дат (по `as_of::date`):

```sql
SELECT
    code,
    stock_total,
    stock_free,
    reserved,
    as_of
FROM public.inventory_history
WHERE code = 'D010210'
  AND as_of::date BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
ORDER BY as_of DESC;
```

Через `psql` в контейнере:

```bash
docker compose exec db   psql -U postgres -d wine_db -c "SELECT code, stock_total, stock_free, reserved, as_of FROM public.inventory_history ORDER BY as_of DESC LIMIT 20;"
```

### Через API + curl.exe + jq

История остатков по SKU (API-эндпоинт):

```powershell
$baseUrl = "http://localhost:18000"
$env:API_KEY = "ВАШ_API_КЛЮЧ"
$code = "D010210"

curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code/inventory-history?from=2020-01-01&to=2030-12-31&limit=10" |
  jq '.items[] | {
    as_of,
    stock_total,
    stock_free,
    reserved
  }'
```

Проверка типов (что это числа, а не строки):

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code/inventory-history?from=2020-01-01&to=2030-12-31&limit=1" |
  jq '.items[0] | {
    stock_total_type: ( .stock_total | type ),
    stock_free_type: ( .stock_free | type ),
    reserved_type: ( .reserved | type )
  }'
# Все три поля должны быть "number"
```

Экспорт истории в JSON (под дальнейший анализ или выгрузку):

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/export/inventory-history/$code?format=json&limit=50" |
  jq '.items[] | {
    as_of,
    stock_total,
    stock_free,
    reserved
  }'
```

Экспорт в Excel:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/export/inventory-history/$code?format=xlsx&limit=200" `
  -o "inventory_history_$code.xlsx"
```

После этого файл `inventory_history_<code>.xlsx` можно открыть в Excel и
построить простой график остатков по времени.

---

## Как строить графики цен и остатков в UI

Во фронтенде проекта есть простой HTML-интерфейс `ui.html`, который:

- показывает список товаров (по `/api/v1/products/search`);
- открывает карточку SKU;
- рисует два графика с помощью **Chart.js**:
  - историю цен (`/api/v1/sku/<code>/price-history`);
  - историю остатков (`/api/v1/sku/<code>/inventory-history`).

### Структура данных для графиков

Оба эндпоинта возвращают массив `items` со временем и значением:

- `/api/v1/sku/<code>/price-history`:

  ```json
  {
    "items": [
      {
        "effective_from": "2025-01-20T00:00:00",
        "effective_to": "2025-06-03T00:00:00",
        "price_rub": 1677.0
      }
    ]
  }
  ```

- `/api/v1/sku/<code>/inventory-history`:

  ```json
  {
    "items": [
      {
        "as_of": "2025-12-02T15:26:28.671832",
        "stock_total": 12502,
        "stock_free": 12334,
        "reserved": 0
      }
    ]
  }
  ```

Для графиков важно:

- использовать **`effective_from`** или **`as_of`** как подписи по оси X;
- брать числовое поле (`price_rub`, `stock_total`, `stock_free`, `reserved`)
  как значения по оси Y.

### Обобщённый рендер графика (Chart.js)

Пример вспомогательной функции для отрисовки одной линии:

```js
function renderHistoryChart(ctx, existingChart, label, dataPoints, valueKey) {
  const labels = dataPoints.map((p) => p.effective_from || p.as_of || "");
  const values = dataPoints.map((p) => p[valueKey]);

  if (existingChart) {
    existingChart.destroy();
  }

  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label,
          data: values,
          tension: 0.2, // лёгкое сглаживание линий
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        x: {
          ticks: { maxRotation: 45, minRotation: 0 },
        },
      },
    },
  });
}
```

### Загрузка истории и отрисовка графиков

```js
let priceChart = null;
let inventoryChart = null;

async function loadSkuDetail(code) {
  try {
    const sku = await apiGet(`/sku/${code}`);
    renderSkuCard(sku);

    const [priceHistory, inventoryHistory] = await Promise.all([
      apiGet(`/sku/${code}/price-history`, {
        from: "2020-01-01",
        to: "2030-12-31",
        limit: 100,
      }),
      apiGet(`/sku/${code}/inventory-history`, {
        from: "2020-01-01",
        to: "2030-12-31",
        limit: 100,
      }),
    ]);

    const priceCtx = document
      .getElementById("priceHistoryChart")
      .getContext("2d");
    const invCtx = document
      .getElementById("inventoryHistoryChart")
      .getContext("2d");

    // График истории цен
    priceChart = renderHistoryChart(
      priceCtx,
      priceChart,
      "Цена, ₽",
      priceHistory.items || [],
      "price_rub"
    );

    // График истории остатков (используем stock_total, можно поменять на stock_free)
    inventoryChart = renderHistoryChart(
      invCtx,
      inventoryChart,
      "Остаток, шт",
      inventoryHistory.items || [],
      "stock_total"
    );
  } catch (err) {
    console.error(err);
    alert("Ошибка при загрузке SKU или истории: " + err.message);
  }
}
```

### HTML-разметка для графиков

```html
<div class="mb-3">
  <h6>История цен</h6>
  <canvas id="priceHistoryChart" height="120"></canvas>
</div>

<div class="mb-3">
  <h6>История остатков</h6>
  <canvas id="inventoryHistoryChart" height="120"></canvas>
</div>
```

Подключение Chart.js через CDN:

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

---

## How-to: нюансы дизайна графиков (Chart.js)

Ниже — небольшая «шпаргалка», как сделать графики чуть более удобочитаемыми:
цвета, подсказки, формат осей, логарифмическая шкала и т.п.

Все примеры относятся к `Chart.js 4.x` и могут быть применены к функции
`renderHistoryChart(...)` или её специализированным вариантам.

### 1. Цвета линий и заливки

Chart.js по умолчанию подставляет цвета сам, но для консистентного UI
можно явно задать палитру.

Пример: одна линия с кастомным цветом и лёгкой заливкой под графиком:

```js
return new Chart(ctx, {
  type: "line",
  data: {
    labels,
    datasets: [
      {
        label,
        data: values,
        tension: 0.2,
        borderWidth: 2,
        borderColor: "rgba(75, 192, 192, 1)",        // цвет линии
        backgroundColor: "rgba(75, 192, 192, 0.15)", // лёгкая заливка
        pointRadius: 2,
        pointHoverRadius: 4,
      },
    ],
  },
  options: {
    responsive: true,
    plugins: {
      legend: {
        display: true,
      },
    },
  },
});
```

Для нескольких линий (например, `stock_total` и `stock_free`) полезно
подобрать:

- одну «потолще» и более яркого цвета — для ключевого ряда;
- вторую — более лёгкую, возможно пунктирную (`borderDash: [4, 4]`).

### 2. Настройка tooltip'ов (подсказок)

По умолчанию всплывающая подсказка показывает:

- значение по X;
- значение по каждой линии.

Можно сделать более читаемо: добавить форматирование чисел, единицы измерения
и дату в читабельном виде.

Пример для графика цен:

```js
options: {
  plugins: {
    tooltip: {
      callbacks: {
        title(items) {
          // по умолчанию title = label по оси X
          return items[0].label || "";
        },
        label(context) {
          const value = context.parsed.y;
          const dsLabel = context.dataset.label || "";
          // разделитель тысяч и "₽"
          return `${dsLabel}: ${value.toLocaleString("ru-RU")} ₽`;
        },
      },
    },
  },
}
```

Для графика остатков:

```js
label(context) {
  const value = context.parsed.y;
  const dsLabel = context.dataset.label || "";
  return `${dsLabel}: ${value.toLocaleString("ru-RU")} шт`;
}
```

### 3. Формат подписи дат по оси X

Если в `labels` лежат ISO-строки (`"2025-01-20T00:00:00"`), их можно
преобразовать в более короткий формат до передачи в Chart.js:

```js
const labels = dataPoints.map((p) => {
  const raw = p.effective_from || p.as_of;
  if (!raw) return "";
  const d = new Date(raw);
  return d.toLocaleDateString("ru-RU", {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
  });
});
```

Либо обрезать в `ticks.callback`:

```js
options: {
  scales: {
    x: {
      ticks: {
        maxRotation: 45,
        minRotation: 0,
        callback(value) {
          const label = this.getLabelForValue(value);
          // Обрезаем до YYYY-MM-DD
          return label ? label.slice(0, 10) : "";
        },
      },
    },
  },
}
```

### 4. Логарифмическая шкала для «диких» остатков

Если значения по Y сильно различаются (например, 10, 1000, 100000), можно
сделать ось Y логарифмической — так график станет более читаемым.

Пример для графика остатков:

```js
options: {
  scales: {
    y: {
      type: "logarithmic",
      ticks: {
        callback(value) {
          // Показываем только «красивые» значения
          return Number(value).toLocaleString("ru-RU");
        },
      },
    },
  },
}
```

Важно:

- логарифмическая шкала не поддерживает `0` и отрицательные значения;
- перед включением стоит убедиться, что `stock_total`, `stock_free`, `reserved`
  всегда >= 0 (по модели так и должно быть).

### 5. Ограничение отображаемого диапазона (зум/фильтр)

Если истории длинные, можно:

- либо фильтровать данные **перед** передачей в Chart.js (например,
  только последние 30–50 точек),
- либо использовать плагины зума/скролла (например, `chartjs-plugin-zoom`).

Простейший вариант — фильтрация на фронте:

```js
function takeLastN(points, n) {
  if (!Array.isArray(points)) return [];
  if (points.length <= n) return points;
  return points.slice(-n);
}

const pricePoints = takeLastN(priceHistory.items || [], 50);
const inventoryPoints = takeLastN(inventoryHistory.items || [], 50);

priceChart = renderHistoryChart(priceCtx, priceChart, "Цена, ₽", pricePoints, "price_rub");
inventoryChart = renderHistoryChart(invCtx, inventoryChart, "Остаток, шт", inventoryPoints, "stock_total");
```

### 6. Тонкая настройка легенды и сетки

Чтобы не перегружать UI, иногда полезно:

- выключить сетку по X или Y;
- убрать легенду, если и так понятно, что показывается.

Примеры:

```js
options: {
  plugins: {
    legend: {
      display: true,   // или false, если линий мало и подпись не нужна
    },
  },
  scales: {
    x: {
      grid: {
        display: false,
      },
    },
    y: {
      grid: {
        color: "rgba(0, 0, 0, 0.05)", // очень лёгкая сетка
      },
    },
  },
}
```

---

В итоге минимальный «рецепт» для приятных графиков:

1. Явно задать цвета линий и небольшую заливку (особенно для ключевого ряда).
2. Настроить tooltip'ы (формат даты и чисел с единицами измерения).
3. Сократить подписи по оси X до коротких дат.
4. По необходимости включить логарифмическую шкалу для очень разных чисел.
5. Ограничить количество точек (последние N записей), чтобы график не
   превращался в «колючий куст».
