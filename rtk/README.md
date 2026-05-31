# Дипломная работа: Сравнительный экспериментальный стенд Testing ↔ Monitoring

## Содержание

1. [Центральная идея и научная конструкция](#1-центральная-идея-и-научная-конструкция)
2. [Архитектура стенда (Блок A)](#2-архитектура-стенда-блок-a)
3. [Структура проекта](#3-структура-проекта)
4. [Быстрый старт](#4-быстрый-старт)
5. [Блок B: Baseline-тестирование (A0)](#5-блок-b-baseline-тестирование-a0)
6. [Блок C: Observability-конфигурации](#6-блок-c-observability-конфигурации)
7. [Блок D: Ex-vivo regression (A1)](#7-блок-d-ex-vivo-regression-a1)
8. [Блок E: Fault injection + observability (A2)](#8-блок-e-fault-injection--observability-a2)
9. [Блок F: Overhead-измерения](#9-блок-f-overhead-измерения)
10. [Комбинированный режим A3](#10-комбинированный-режим-a3)
11. [Метрики эксперимента](#11-метрики-эксперимента)
12. [Запуск всех экспериментов](#12-запуск-всех-экспериментов)
13. [Генерация отчёта и верификация результатов](#13-генерация-отчёта-и-верификация-результатов)
14. [Артефакты дипломной работы](#14-артефакты-дипломной-работы)
15. [Описание исходной системы (RTK Agent)](#15-описание-исходной-системы-rtk-agent)
16. [Каталог сценариев](#16-каталог-сценариев)
17. [Запуск матричных экспериментов и генерация датасета](#17-запуск-матричных-экспериментов-и-генерация-датасета)
18. [Data contract и структура результатов](#18-data-contract-и-структура-результатов)
19. [Агрегация и таблицы для диплома](#19-агрегация-и-таблицы-для-диплома)
20. [Визуализация и научные графики](#20-визуализация-и-научные-графики)
21. [Case-study: анализ отдельных сценариев](#21-case-study-анализ-отдельных-сценариев)
22. [Интерпретация результатов эксперимента](#22-интерпретация-результатов-эксперимента)
23. [Отчёт по исследовательскому слою](#23-отчёт-по-исследовательскому-слою)

---

## 1. Центральная идея и научная конструкция

Диплом разрабатывает **сравнительный экспериментальный стенд**, который количественно отвечает на вопросы:

- что обнаруживает классическое тестирование (baseline);
- что дополнительно даёт **ex-vivo / field-driven regression** поверх baseline;
- что дополнительно даёт **fault injection + observability evaluation** поверх baseline;
- какой **overhead** и какие искажения вносит сама инструментация.

### Режимы сравнения

| Режим | Название | Блоки | Что добавляет |
|-------|----------|-------|---------------|
| **A0** | Classical baseline | B | Нижняя граница: unit + integration + API + e2e |
| **A1** | Baseline + Ex-vivo | B + D | Регрессии из runtime-взаимодействий |
| **A2** | Baseline + FI + Obs | B + C + E + F | Fault detectability, diagnosability, overhead |
| **A3** | Combined | B + C + D + E + F | Синергия A1 и A2 |

Научная чистота схемы: **baseline (A0) обязателен**, остальные режимы — надстройки, эффект которых измеряется относительно A0.

---

## 2. Архитектура стенда (Блок A)

### Экспериментальный объект

Система **RTK Agent** — микросервисная система обработки заявок (тикетов) с LLM-интеграцией.

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent API (FastAPI)                      │
│  POST /tickets/intake  ·  GET /health  ·  GET /metrics      │
└──────────────┬──────────────────────────┬───────────────────┘
               │ HTTP/REST                │ MCP (stdio subprocess)
               ▼                          ▼
     ┌──────────────────┐     ┌───────────────────────────┐
     │   RAG Mock       │     │   MCP Server              │
     │  (FastAPI :8090) │     │  OrderService             │
     │  POST /query     │     │  OtrsService              │
     └──────────────────┘     │  (in-memory storage)      │
                               └───────────────────────────┘
                                          │
                               ┌──────────▼──────────┐
                               │   LLM Provider      │
                               │  Ollama / OpenRouter │
                               └─────────────────────┘
```

**Характеристики системы:**

- Несколько сервисов с чёткими границами (Agent API, RAG Mock, MCP Server, LLM Provider)
- HTTP/REST-взаимодействия (FastAPI)
- Межсервисные вызовы через MCP (Model Context Protocol)
- In-memory mock-хранилища: `LOGS_DB`, `ORDERS_DB`, `EISSD_DB`, `OTRS_TICKETS`
- Docker Compose для воспроизводимого развёртывания
- Prometheus-метрики на `/metrics`
- Изолируемое состояние для воспроизводимых тестов

### Почему именно эта система

Система полностью отвечает требованиям экспериментального объекта:
- несколько сервисов с реальными межсервисными вызовами;
- HTTP/REST-взаимодействия;
- состояние (ORDERS_DB, LOGS_DB) и зависимости (RAG, LLM);
- локальное развёртывание в контейнерах;
- возможность добавления инструментации и fault-сценариев.

---

## 3. Структура проекта

```
diplom/
├── README.md                        # Этот файл
├── requirements.txt                 # Зависимости Python
├── pytest.ini                       # Конфигурация тестов
├── docker-compose.yml               # Развёртывание сервисов
├── Dockerfile                       # Образ Agent API
│
├── scenarios/                       # Каталог сценариев (JSON)
│   ├── __init__.py                  # Загрузчик каталогов
│   ├── regression_catalog.json      # 5 регрессионных сценариев (REG-001…REG-005)
│   └── fault_catalog.json           # 8 fault-injection сценариев (FLT-001…FLT-008)
│
├── visualization/                   # Визуализация (top-level entry)
│   ├── plots/                       # Построители графиков
│   │   ├── build_verification.py    # Verification summary + test stack
│   │   ├── build_comparison.py      # Scenario matrix + A0/A1/A2/A3
│   │   ├── build_exvivo.py          # Ex-vivo funnel + vs baseline
│   │   ├── build_fault_obs.py       # Fault heatmap + TTD distribution
│   │   ├── build_overhead.py        # Overhead + Pareto + signal contribution
│   │   └── build_case_studies.py    # Incident timeline
│   ├── dashboard/                   # Dash dashboard
│   └── notebooks/                   # Jupyter notebooks для анализа
│
├── agent_api/                       # Agent API (FastAPI)
├── services/
│   ├── mcp_server/                  # MCP Server + in-memory хранилища
│   └── rag_mock/                    # RAG Mock сервис
├── pipeline/                        # Бизнес-логика пайплайна
├── providers/                       # LLM-провайдеры
├── common/                          # Общие модели, конфиг, метрики
│
├── tests/                           # Блок B: Baseline test suite
│   ├── conftest.py                  # Фикстуры, сброс состояния
│   ├── test_unit_models.py          # Unit-тесты моделей
│   ├── test_unit_pipeline.py        # Unit-тесты pipeline-логики
│   ├── test_integration_services.py # Integration-тесты
│   ├── test_api_contract.py         # API/contract-тесты
│   └── test_e2e.py                  # E2E/smoke-тесты
│
└── experiments/                     # Блоки C–F: Экспериментальный стенд
    ├── __main__.py                  # Единый entrypoint: python -m experiments
    ├── run_experiments.py           # Оркестрация матрицы экспериментов
    ├── sciexport.py                 # Экспорт артефактов для диплома
    ├── conftest.py                  # Общие фикстуры экспериментов
    │
    ├── data_contracts/              # Контракты данных
    │   └── schemas.py               # RawRunRecord, AggregatedResult, ScenarioSpec
    ├── dataset/                     # Запись/чтение датасета
    │   └── writer.py                # DatasetWriter (JSONL + CSV)
    ├── analysis/                    # Статистический анализ
    │   └── statistics.py            # Агрегации, CI, таблицы для диплома
    │
    ├── casestudy/                   # Case-study артефакты
    │   └── builder.py               # CaseStudyArtifact + timeline
    │
    ├── observability/               # Блок C: Observability O0/O1/O2
    │   ├── configs.py               # Конфигурации O0/O1/O2
    │   ├── collectors.py            # Сбор телеметрических сигналов
    │   └── detectors.py             # Детекторы аномалий
    ├── exvivo/                      # Блок D: Ex-vivo regression
    │   ├── capture.py               # Захват runtime-взаимодействий
    │   ├── normalize.py             # Нормализация (timestamps/IDs)
    │   ├── replay.py                # Движок replay + сравнение
    │   └── test_exvivo.py           # Тесты ex-vivo pipeline
    ├── fault_injection/             # Блок E: Fault injection
    │   ├── faults.py                # 6 классов сбоев
    │   ├── injector.py              # Механизм инъекции
    │   └── test_fault_observability.py  # Эксперименты
    ├── overhead/                    # Блок F: Overhead
    │   ├── benchmark.py             # Бенчмаркинг
    │   └── test_overhead.py         # Измерение overhead O0/O1/O2
    ├── visualization/               # Построение графиков (Plotly)
    │   ├── plots.py                 # 12 обязательных научных графиков
    │   └── export.py                # Экспорт PNG/SVG/HTML
    ├── dashboard/                   # Dash-дашборд
    │   └── app.py                   # Интерактивный дашборд
    └── comparison/                  # Сравнительный фреймворк A0–A3
        ├── runner.py                # Оркестрация экспериментов
        ├── metrics.py               # Стандартизированные метрики
        ├── report.py                # Генерация отчётов
        ├── run_matrix.py            # Алиас: python -m experiments.comparison.run_matrix
        └── test_comparison.py       # Интеграционные тесты
```

---

## 4. Быстрый старт

### Требования

- Python 3.10+
- pip

### Установка зависимостей

```bash
pip install -r requirements.txt
```

### Запуск всех тестов (проверка работоспособности стенда)

```bash
python -m pytest tests/ experiments/ -v
```

Ожидаемый результат: **128 passed**.

### Запуск с Docker

```bash
docker compose up --build
curl -s http://localhost:8080/health
curl -s http://localhost:8090/health
```

---

## 5. Блок B: Baseline-тестирование (A0)

Baseline — обязательная нижняя граница. Все последующие режимы сравниваются относительно него.

### Что реализовано

#### Unit-тесты (`tests/test_unit_models.py`, `tests/test_unit_pipeline.py`)

Покрывают:
- нормализацию статусов (`OrderStatus`, `OtrsStatus`);
- dataclass-конструкторы (`Ticket`, `ActionLogEntry`);
- MCP-сервисы (`OrderService`, `OtrsService`);
- pipeline-хелперы (`_unwrap_mcp_dict`, `build_final_comment`);
- валидацию Pydantic-моделей.

#### Integration-тесты (`tests/test_integration_services.py`)

Покрывают:
- сквозной workflow: `search_logs` → `get_order_status` → `check_eissd_status`;
- полный lifecycle OTRS-тикета;
- изоляцию состояния между тестами;
- мультизаказные операции.

#### API/contract-тесты (`tests/test_api_contract.py`)

Покрывают:
- валидацию схем `TicketIn` / `TicketOut`;
- контракты `RagRequest` / `RagResponse`;
- логику RAG mock endpoint;
- round-trip сериализации.

#### E2E/smoke-тесты (`tests/test_e2e.py`)

Покрывают:
- health endpoint (`GET /health`);
- metrics endpoint (`GET /metrics`);
- полный прогон `POST /tickets/intake` (mocked pipeline);
- обработку timeout → 504, internal error → 500;
- валидацию входных данных → 422.

### Как запустить

```bash
# Все baseline-тесты
python -m pytest tests/ -v

# Только unit
python -m pytest tests/test_unit_models.py tests/test_unit_pipeline.py -v

# Только integration
python -m pytest tests/test_integration_services.py -v

# Только API/contract
python -m pytest tests/test_api_contract.py -v

# Только E2E
python -m pytest tests/test_e2e.py -v
```

### Как проверить результаты

Успешный прогон выглядит так:

```
tests/test_unit_models.py ............  PASSED
tests/test_unit_pipeline.py .......     PASSED
tests/test_integration_services.py .... PASSED
tests/test_api_contract.py ......       PASSED
tests/test_e2e.py .....                 PASSED
```

**Ключевые свойства baseline:**
- стабильный: детерминированные моки, без внешних зависимостей;
- воспроизводимый: `conftest.py` сбрасывает состояние перед каждым тестом;
- одинаковый для всех последующих режимов.

---

## 6. Блок C: Observability-конфигурации

Наблюдаемость реализована как **три сравниваемые конфигурации** — это ключевой научный вклад блока. Одни и те же fault-сценарии прогоняются при разных уровнях observability, что позволяет измерить, сколько даёт каждый уровень инструментации.

### Конфигурации O0 / O1 / O2

| Параметр | O0 (минимальная) | O1 (средняя) | O2 (расширенная) |
|----------|-----------------|--------------|-----------------|
| Error counters | ✓ | ✓ | ✓ |
| Health checks | ✓ | ✓ | ✓ |
| Latency histograms | — | ✓ | ✓ |
| Structured logs | — | ✓ | ✓ |
| Basic traces | — | ✓ | ✓ |
| Span attributes | — | — | ✓ |
| Inter-service correlation | — | — | ✓ |
| Resource metrics | — | — | ✓ |
| Diagnostic signals | — | — | ✓ |
| **Signal depth** | **2/9** | **5/9** | **9/9** |

### Детекторы аномалий

| Детектор | Сигналы | Что определяет |
|----------|---------|----------------|
| `MetricDetector` | error rate, latency spikes | факт сбоя по метрикам |
| `LogDetector` | error patterns в structured logs | тип и источник ошибки |
| `TraceDetector` | error spans, correlation | сервис-источник по трассировке |
| `CombinedDetector` | все типы сигналов | агрегированная диагностика |

### Как запустить

```bash
python -m pytest experiments/observability/ -v
```

### Как проверить в коде

```python
from experiments.observability.configs import ObservabilityLevel, get_config

o0 = get_config(ObservabilityLevel.O0)
o1 = get_config(ObservabilityLevel.O1)
o2 = get_config(ObservabilityLevel.O2)

print(o0.signal_depth)  # 2
print(o1.signal_depth)  # 5
print(o2.signal_depth)  # 9

assert o0.signal_depth < o1.signal_depth < o2.signal_depth
```

---

## 7. Блок D: Ex-vivo regression (A1)

Ex-vivo regression — первый исследовательский усилитель baseline. Суть: захватить runtime-взаимодействия, нормализовать их и превратить в воспроизводимые регрессионные тесты.

### Этапы pipeline

```
Runtime / API вызовы
        │
        ▼
  [Capture]  — запись call_name, arguments, response, timestamp
        │
        ▼
  [Normalize] — удаление нестабильных полей:
                timestamps, IDs, nonces, UUIDs
        │
        ▼
  [Replay]   — воспроизведение с реальным dispatcher
                и структурное сравнение ответов
        │
        ▼
  [Compare]  — matched / mismatched / errors
                → regression_found count
```

### Ключевые возможности

- Детерминированное маппирование ID (одинаковый старый ID → одинаковый новый ID)
- JSON-сериализация/десериализация сценариев для воспроизводимости
- Tolerance для float-сравнений
- Trace context tracking
- Изолированная среда воспроизведения (state reset через conftest)

### Как запустить

```bash
python -m pytest experiments/exvivo/ -v
```

### Пример использования

```python
from experiments.exvivo.capture import InteractionCapture
from experiments.exvivo.normalize import InteractionNormaliser
from experiments.exvivo.replay import ReplayEngine
from services.mcp_server.services import OrderService
from services.mcp_server.models import SearchLogsRequest

# 1. Захват взаимодействий
cap = InteractionCapture()
cap.start_scenario("my_scenario")
cap.record_call(
    lambda: OrderService.search_logs(
        SearchLogsRequest(order_id="1800003902272", pattern="ORDER_STATUS_DENIED")
    ).model_dump(),
    call_name="search_logs",
    arguments_dict={"order_id": "1800003902272", "pattern": "ORDER_STATUS_DENIED"},
)
scenario = cap.finish_scenario()

# 2. Нормализация
norm = InteractionNormaliser()
clean_scenario = norm.normalise(scenario)

# 3. Replay
def dispatcher(call_name, args):
    if call_name == "search_logs":
        return OrderService.search_logs(SearchLogsRequest(**args)).model_dump()

engine = ReplayEngine(dispatcher=dispatcher)
result = engine.replay_scenario(clean_scenario)

print(f"Matched: {result.matched}/{result.total_interactions}")
print(f"Regressions: {result.mismatched}")
```

### Как проверить результаты

Успешный replay: `matched == total_interactions`, `mismatched == 0`.

При регрессии (изменился контракт сервиса): `mismatched > 0` → тест красный.

---

## 8. Блок E: Fault injection + observability (A2)

Fault injection — второй, научно более сильный, исследовательский усилитель. Позволяет сделать observability **измеримым и количественным** свойством системы.

### 6 классов сбоев

| Класс | Описание | Параметры |
|-------|----------|-----------|
| `LATENCY` | Искусственная задержка | `delay_ms` (по умолчанию 500) |
| `TIMEOUT` | Симуляция timeout | `delay_ms` (по умолчанию 5000) |
| `DEPENDENCY_FAILURE` | Отказ зависимости | `error_message`, `error_cls` |
| `PARTIAL_UNAVAILABLE` | Перемежающийся отказ | `failure_rate` (0.0–1.0) |
| `RESOURCE_DEGRADATION` | Нагрузка на CPU | `cpu_burn_ms` |
| `NETWORK_DEGRADATION` | Сетевая деградация | `jitter_ms`, `corruption_rate` |

### Механизм инъекции

`FaultInjector` — контролируемый, включаемый/выключаемый механизм:

```python
from experiments.fault_injection.faults import FaultClass, FaultSpec
from experiments.fault_injection.injector import FaultInjector

injector = FaultInjector()
injector.add_fault(FaultSpec(
    fault_class=FaultClass.LATENCY,
    target_call="get_order_status",   # только для этого вызова
    params={"delay_ms": 300},
))

# Инъекция активна
result = injector.call(my_service_func, call_name="get_order_status")

# Отключить
injector.deactivate_all()
result = injector.call(my_service_func, call_name="get_order_status")  # без задержки
```

### Observability experiments: одни fault-сценарии при разных O-уровнях

```python
from experiments.observability.configs import ObservabilityLevel, get_config
from experiments.observability.collectors import TelemetryCollector, SignalStore
from experiments.observability.detectors import CombinedDetector

for level in [ObservabilityLevel.O0, ObservabilityLevel.O1, ObservabilityLevel.O2]:
    config = get_config(level)
    store = SignalStore()
    collector = TelemetryCollector(config, store)

    collector.begin_trace()
    # ... прогон fault-сценария ...
    collector.end_trace()

    result = CombinedDetector().detect(store)
    print(f"{level}: detected={result.detected}, localized={result.localized}, "
          f"ttd={result.time_to_detect_ms}ms")
```

### Измеряемые характеристики fault observability

| Метрика | Описание |
|---------|----------|
| `detected` | обнаружен ли сбой |
| `localized` | локализован ли источник |
| `time_to_detect_ms` | время до обнаружения |
| `signal_types_used` | какие типы сигналов задействованы |
| `signal_usefulness_score` | агрегированная оценка полезности (0.0–1.0) |

### Как запустить

```bash
# Все fault injection эксперименты
python -m pytest experiments/fault_injection/ -v

# Конкретный тест
python -m pytest experiments/fault_injection/test_fault_observability.py -v -k "latency"
```

---

## 9. Блок F: Overhead-измерения

Инструментация — не нейтральный наблюдатель. Блок F измеряет, сколько стоит каждый уровень observability.

### Метрики overhead

| Метрика | Описание |
|---------|----------|
| `mean_latency_ms` | Среднее время вызова |
| `median_latency_ms` | Медианное время |
| `p95_latency_ms` | 95-й перцентиль задержки |
| `p99_latency_ms` | 99-й перцентиль задержки |
| `throughput_per_sec` | Пропускная способность |
| `error_rate` | Доля ошибок |
| `rss_delta_kb` | Прирост RSS памяти |
| `stdev_latency_ms` | Дисперсия задержек |

### Сравнение baseline vs O0 vs O1 vs O2

```python
from experiments.overhead.benchmark import run_benchmark, compare_overhead
from experiments.observability.configs import ObservabilityLevel
from services.mcp_server.services import OrderService
from services.mcp_server.models import GetOrderStatusRequest

def workload():
    return OrderService.get_order_status(GetOrderStatusRequest(order_id="1800003902272"))

# Baseline (без инструментации)
baseline = run_benchmark(workload, n_calls=100, label="baseline")

# Каждый уровень observability
for level in [ObservabilityLevel.O0, ObservabilityLevel.O1, ObservabilityLevel.O2]:
    comp = compare_overhead(workload, level, n_calls=100)
    print(comp.summary())
```

Вывод включает:
- `latency_overhead_ms` — абсолютный прирост задержки
- `latency_overhead_pct` — относительный прирост задержки (%)
- `throughput_overhead_pct` — потеря пропускной способности (%)
- `variance_growth` — рост дисперсии (коэффициент)

### Как запустить

```bash
python -m pytest experiments/overhead/ -v
```

---

## 10. Комбинированный режим A3

A3 объединяет ex-vivo (A1) и fault injection + observability (A2), позволяя проверить, есть ли синергия.

### Что исследуется в A3

- Даёт ли комбинация больше, чем каждый подход по отдельности?
- Или суммируются только сложности, но не преимущества?

### Как запустить

```bash
python -m pytest experiments/comparison/ -v
```

---

## 11. Метрики эксперимента

### Метрики тестирования (TestingMetrics)

| Метрика | Тип | Описание |
|---------|-----|----------|
| `defects_found` | int | Число обнаруженных дефектов |
| `defects_missed` | int | Число пропущенных дефектов |
| `false_positives` | int | Число ложных срабатываний |
| `detection_rate` | float | defects_found / (found + missed) |
| `false_positive_rate` | float | false_positives / total |
| `execution_time_ms` | float | Стоимость прогона тестов |
| `reproducibility_rate` | float | 1.0 = полностью воспроизводим |

### Метрики диагностики (DiagnosticMetrics)

| Метрика | Тип | Описание |
|---------|-----|----------|
| `fault_detected` | bool | Обнаружен ли сбой |
| `fault_localized` | bool | Локализован ли источник |
| `time_to_detect_ms` | float | Время до обнаружения (мс) |
| `time_to_localize_ms` | float | Время до локализации (мс) |
| `signal_types_used` | set | Какие типы сигналов задействованы |
| `signal_usefulness_score` | float | Агрегированная оценка 0.0–1.0 |

### Метрики overhead (OverheadMetrics)

| Метрика | Тип | Описание |
|---------|-----|----------|
| `latency_overhead_ms` | float | Абсолютный прирост задержки |
| `latency_overhead_pct` | float | Относительный прирост задержки (%) |
| `throughput_overhead_pct` | float | Потеря пропускной способности (%) |
| `resource_overhead_kb` | int | Прирост RSS памяти (КБ) |
| `variance_growth` | float | Коэффициент роста дисперсии |

### Метрики ex-vivo (ExVivoMetrics)

| Метрика | Тип | Описание |
|---------|-----|----------|
| `total_scenarios` | int | Число сценариев |
| `total_interactions` | int | Число захваченных взаимодействий |
| `matched_interactions` | int | Число совпавших при replay |
| `regressions_found` | int | Число найденных регрессий |
| `match_rate` | float | matched / total |
| `replay_time_ms` | float | Время воспроизведения (мс) |

---

## 12. Запуск всех экспериментов

### Полный прогон

```bash
# Установка зависимостей
pip install -r requirements.txt

# Все тесты (128 тестов): baseline + все эксперименты
python -m pytest tests/ experiments/ -v

# Только baseline (A0)
python -m pytest tests/ -v

# Только ex-vivo (A1)
python -m pytest experiments/exvivo/ -v

# Только fault injection (A2)
python -m pytest experiments/fault_injection/ -v

# Только overhead (F)
python -m pytest experiments/overhead/ -v

# Только сравнительный фреймворк (A0–A3)
python -m pytest experiments/comparison/ -v
```

### Матричный прогон (dataset + артефакты)

```bash
# Полный прогон: матрица × повторы → raw_runs.jsonl + aggregated.csv + таблицы + графики + case studies
python -m experiments

# С кастомным количеством повторов
python -m experiments --repeats 5

# Без экспорта графиков (быстрее, для CI)
python -m experiments --no-figures

# Альтернативный entrypoint
python -m experiments.comparison.run_matrix
```

После запуска появятся:

| Артефакт | Путь | Описание |
|----------|------|----------|
| Сырые данные | `experiments/results/raw_runs.jsonl` | Каждая строка — один прогон |
| Агрегаты | `experiments/results/aggregated.csv` | Средние по группам |
| Таблицы | `experiments/results/tables/*.csv` | Для вставки в диплом |
| Резюме | `experiments/results/summary/*.json` | Параметры + метаданные |
| Графики | `experiments/results/figures/*.png` | 12 научных графиков |
| Case studies | `experiments/results/casestudies/*.json` | REG + FLT кейсы |

### Запуск с разбивкой по маркерам

```bash
# Unit-тесты
python -m pytest tests/ -v -k "unit"

# Integration-тесты
python -m pytest tests/ -v -k "integration"

# Contract-тесты
python -m pytest tests/ -v -k "contract"

# E2E/smoke
python -m pytest tests/ -v -k "e2e"
```

---

## 13. Генерация отчёта и верификация результатов

### Текстовый отчёт сравнения режимов A0–A3

```bash
python -c "
from experiments.comparison.runner import run_a0, run_a1, run_a2, run_a3
from experiments.comparison.report import generate_text_report
results = [run_a0(), run_a1(), run_a2(), run_a3()]
print(generate_text_report(results))
"
```

Пример вывода:

```
================================================================================
EXPERIMENT COMPARISON REPORT
================================================================================

Mode: A0 (obs=)
  Testing: defects_found=0, detection_rate=0.0%, exec_time=X.Xms
  Diagnostic: detected=False, localized=False, ttd=None ms, signal_usefulness=0.000
  Overhead: latency=0.000ms (0.0%), throughput_loss=0.0%, variance_growth=1.00x
  ExVivo: regressions=0, match_rate=0.0%

Mode: A1 (obs=)
  Testing: defects_found=0, detection_rate=0.0%, exec_time=X.Xms
  Diagnostic: detected=False, localized=False, ttd=None ms, signal_usefulness=0.000
  Overhead: latency=0.000ms (0.0%), throughput_loss=0.0%, variance_growth=1.00x
  ExVivo: regressions=0, match_rate=100.0%

Mode: A2 (obs=O1)
  Testing: defects_found=0, detection_rate=0.0%, exec_time=X.Xms
  Diagnostic: detected=True, localized=True, ttd=X ms, signal_usefulness=0.850
  Overhead: latency=X.Xms (X.X%), throughput_loss=X.X%, variance_growth=X.XXx
  ExVivo: regressions=0, match_rate=0.0%

Mode: A3 (obs=O1)
  ...combined...
================================================================================
```

### JSON-отчёт (для программной обработки)

```bash
python -c "
from experiments.comparison.runner import run_a0, run_a1, run_a2, run_a3
from experiments.comparison.report import generate_json_report
results = [run_a0(), run_a1(), run_a2(), run_a3()]
print(generate_json_report(results))
" > report.json
```

### Как интерпретировать результаты

**Режим A0 (baseline):**
- `detection_rate` = доля пойманных дефектов в baseline-сценариях
- `execution_time_ms` = стоимость прогона baseline
- `reproducibility_rate` должна быть = 1.0

**Режим A1 vs A0:**
- `exvivo.match_rate` → высокий (>= 0.9) означает, что replay воспроизводим
- `exvivo.regressions_found > 0` → ex-vivo нашёл регрессии, которые baseline пропустил

**Режим A2 vs A0:**
- `diagnostic.detected = True` → fault injection обнаружен через observability
- `diagnostic.localized = True` → источник сбоя локализован
- `diagnostic.time_to_detect_ms` → меньше = observability быстрее реагирует
- `overhead.latency_overhead_pct` → overhead инструментации в %

**Режим A3 vs A1/A2:**
- Сравниваются метрики: есть ли синергия или только суммирование сложности

### Запуск конкретного observability-уровня в A2

```bash
python -c "
from experiments.comparison.runner import run_a2
from experiments.observability.configs import ObservabilityLevel

for level in [ObservabilityLevel.O0, ObservabilityLevel.O1, ObservabilityLevel.O2]:
    result = run_a2(obs_level=level)
    s = result.summary()
    print(f'{level.value}: detected={s[\"diagnostic\"][\"detected\"]}, '
          f'latency_oh={s[\"overhead\"][\"latency_pct\"]}%')
"
```

---

## 14. Артефакты дипломной работы

| № | Артефакт | Расположение | Описание |
|---|----------|-------------|----------|
| 1 | Описание экспериментального стенда | `experiments/README.md` | Подробная документация всех блоков |
| 2 | Baseline test suite (Блок B) | `tests/` | Unit, Integration, API/contract, E2E |
| 3 | Observability-конфигурации (Блок C) | `experiments/observability/configs.py` | O0/O1/O2 с signal_depth |
| 4 | Детекторы аномалий | `experiments/observability/detectors.py` | Metric/Log/Trace/Combined |
| 5 | Набор fault-сценариев (Блок E) | `experiments/fault_injection/faults.py` | 6 классов сбоев |
| 6 | Механизм fault injection | `experiments/fault_injection/injector.py` | Контролируемый FaultInjector |
| 7 | Ex-vivo pipeline (Блок D) | `experiments/exvivo/` | Capture → Normalize → Replay |
| 8 | Система сбора метрик | `experiments/comparison/metrics.py` | Testing/Diagnostic/Overhead/ExVivo |
| 9 | Генерация отчётов | `experiments/comparison/report.py` | Text/JSON отчёты |
| 10 | Оркестрация экспериментов | `experiments/comparison/runner.py` | run_a0/a1/a2/a3 |
| 11 | Методика overhead | `experiments/overhead/benchmark.py` | BenchmarkResult, OverheadComparison |
| 12 | Наблюдаемость в production | `agent_api/main.py` | Prometheus-метрики на /metrics |
| 13 | Docker Compose | `docker-compose.yml` | Воспроизводимое окружение |
| 14 | Каталоги сценариев | `scenarios/` | regression_catalog.json, fault_catalog.json |
| 15 | Data contract | `experiments/data_contracts/schemas.py` | RawRunRecord, AggregatedResult |
| 16 | Матричный runner | `experiments/run_experiments.py` | Прогон A0/A1/A2/A3 × сценарии × повторы |
| 17 | Dataset writer | `experiments/dataset/writer.py` | Запись raw_runs.jsonl + aggregated.csv |
| 18 | Статистический анализ | `experiments/analysis/statistics.py` | Агрегации, CI, diploma tables |
| 19 | Визуализация (12 графиков) | `experiments/visualization/plots.py` | Plotly-графики для всех метрик |
| 20 | Dash-дашборд | `experiments/dashboard/app.py` | Интерактивный дашборд |
| 21 | Case-study builder | `experiments/casestudy/builder.py` | Timeline + артефакты кейсов |
| 22 | Sciexport | `experiments/sciexport.py` | Таблицы + графики + метаданные для диплома |

---

## 15. Описание исходной системы (RTK Agent)

### Что это и как работает

Сервис `agent` принимает тикет (OTRS-поля) по HTTP, выполняет пайплайн и обновляет тикет через MCP-tools.

Пайплайн:

1. Precheck (обязательный): всегда ищет в логах `ORDER_STATUS_DENIED` за 30 дней через MCP tool `search_logs`.
2. RAG: отправляет в RAG (mock) объединённый запрос (precheck + subject + annotation + description), получает JSON-рекомендацию.
3. LLM: выбирает и вызывает нужные MCP-tools (режим `LLM_MODE=tools` или `LLM_MODE=json`).
4. Verify (контроль): делает цикл проверки статусов через MCP (`get_order_status`, `check_eissd_status`).
5. Final comment: формируется детерминированно кодом (шаблон `key=value`), без генерации LLM.
6. Finalize: добавляет комментарий в тикет и обновляет тикет (статус `OPEN`, `assignee=null`; очередь не меняется, если `ALLOW_QUEUE_CHANGE=0`).

### Компоненты и порты

- Agent API: [http://localhost:8080](http://localhost:8080)
  - Swagger UI: [http://localhost:8080/docs](http://localhost:8080/docs)
  - OpenAPI JSON: [http://localhost:8080/openapi.json](http://localhost:8080/openapi.json)
  - Health: [http://localhost:8080/health](http://localhost:8080/health)
  - Metrics: [http://localhost:8080/metrics](http://localhost:8080/metrics)

- RAG mock: [http://localhost:8090](http://localhost:8090)
  - Health: [http://localhost:8090/health](http://localhost:8090/health)

- Ollama на хосте: [http://localhost:11434](http://localhost:11434) (из контейнера agent: `http://host.docker.internal:11434`)

Важно: MCP-server работает по stdio и запускается внутри контейнера agent как subprocess. Отдельный сетевой MCP-сервис не требуется.

### Требования

- Docker + Docker Compose
- Ollama на хосте (модель `qwen3:8b` скачана)
- Свободные порты: 8080, 8090

### Конфигурация (.env)

Создай файл `.env` в корне (или задай переменные в compose). Минимальный набор:

```dotenv
DEBUG=0
REQUEST_TIME_BUDGET_SECONDS=180

MCP_SERVER_MODULE=services.mcp_server.mcp_server
MCP_DEBUG=0

RAG_BASE_URL=http://rag_mock:8090

LLM_MODE=tools
LLM_PROVIDER=ollama
LLM_MODEL_NAME=qwen3:8b
LLM_TIMEOUT_SECONDS=60
LLM_MAX_ITERATIONS=6
OLLAMA_HOST=http://host.docker.internal:11434

ALLOW_QUEUE_CHANGE=0
```

Рекомендуемо для Linux (чтобы `host.docker.internal` работал):

- в `docker-compose.yml` у agent должен быть `extra_hosts: ["host.docker.internal:host-gateway"]`.

### Запуск (Docker)

В корне репозитория:

```bash
docker compose up --build
```

Проверка что сервисы поднялись:

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8090/health
```

### Важно: agent иногда может не стартовать сам

Иногда контейнер `agent` не хочет поднимаеться.

Что делать:

1. Посмотреть логи или интерфейс docker:

```bash
docker compose logs -n 200 agent
```

2. Если контейнер жив, но сервера нет — запустить вручную внутри контейнера или нажать кнопку запуска в интерфейсе docker:

```bash
docker compose exec -T agent uvicorn agent_api.main:app --host 0.0.0.0 --port 8080
```

1. Если изменения не подхватываются — пересобрать без кэша:

```bash
docker compose down
docker compose build --no-cache agent
docker compose up
```

### Проверка доступности Ollama из контейнера agent

Команда:

```bash
docker compose exec -T agent python - <<'PY'
import os, httpx
host=os.getenv("OLLAMA_HOST")
print("OLLAMA_HOST:", host)
r=httpx.get(host + "/api/tags", timeout=5)
print("GET /api/tags:", r.status_code)
print(r.text[:200])
PY
```

Ожидаемо: `200` и список моделей, включая `qwen3:8b`.

### Как отправить тикет через Swagger UI

1. Открыть: [http://localhost:8080/docs](http://localhost:8080/docs)
2. Найти endpoint `POST /tickets/intake`.
3. Нажать `Try it out`.
4. В поле Request body вставить JSON (пример ниже).
5. Нажать `Execute`.
6. Смотреть:
   - HTTP code (должен быть 200)
   - Response body: `ticket_id`, `final_comment`, `summary` (+ `actions` только при DEBUG=1)

Пример запроса (кейс где precheck должен найти ошибку):

```json
{
  "id": "T-2",
  "order_id": "1800003902272",
  "subject": "Ошибка ORDER_STATUS_DENIED",
  "annotation": "Тест precheck true",
  "description": "ORDER_STATUS_DENIED по заявке 1800003902272",
  "region": "COMMON",
  "queue": "ОЦО.МРФ.Эксплуатация СУЛЗ.COMMON",
  "metadata": {}
}
```

### Как понять, что пайплайн отработал правильно (по final_comment)

В `final_comment` проверить ключевые поля:

- Precheck:
  - `precheck.pattern=ORDER_STATUS_DENIED`
  - `precheck.window_days=30`
  - `precheck.error_found=true|false`
  - `precheck.logs_full_count` (не пустое число)

- RAG:
  - `rag.required_actions_count`

- Verify:
  - `verify.sulz_db.status=...`
  - `verify.eissd.status=...`

- Диагностика:
  - `diag.count=0` (если не 0 — смотреть `diag.0`, `diag.1` и логи)

- Следующий шаг:
  - `next_step=IN_WORK_WAIT_CONFIRMATION` (когда ошибка обнаружена и actions.ok=true)

### Как понять, что LLM реально участвует

1. Логи `agent` должны содержать запросы к Ollama:
   - `POST http://host.docker.internal:11434/api/chat "HTTP/1.1 200 OK"`

2. Метрики:

```bash
curl -s http://localhost:8080/metrics | grep llm_fallback_total
```

Интерпретация:

- `llm_fallback_total{mode="tools_fallback"}` растёт: tools-режим не сработал (LLM не вернула tool_calls / ошибка), пошли в fallback-план.
- `llm_fallback_total{mode="fallback"}` растёт: включён `LLM_MODE=fallback` (LLM не используется).
- Если `llm_fallback_total` не растёт, а время запроса увеличилось и есть `/api/chat` в логах — LLM участвует без fallback.

### Как включить подробности действий (debug)

По умолчанию `/tickets/intake` не возвращает `actions`.

Чтобы вернуть `actions`:

- выставить `DEBUG=1` (в `.env` или env контейнера),
- перезапустить compose.

В ответе появится массив `actions[]`:

- tool name
- params
- ok/error/error_type
- duration_ms

### Типовые проблемы и что смотреть

### 12.1. LLM не работает (нет запросов к /api/chat)

Проверить:

- `OLLAMA_HOST` задан в env контейнера agent
- из контейнера: `/api/tags` возвращает 200 (см. раздел 7)

### 12.2. LLM работает, но падает в fallback

Смотреть:

- `llm_fallback_total`
- логи `agent` (ошибки `LLM call failed` / формат ответа)

Если qwen3:8b не даёт стабильный tool-calling:

- переключить `LLM_MODE=json` (план одним JSON), оставить `fallback` как резерв.

### 12.3. Кэш Docker не подхватил изменения

Решение: `docker compose build --no-cache agent`.

### 12.4. MCP tools не работают

Смотреть `MCP_DEBUG=1` и логи клиента MCP.

---

## 16. Каталог сценариев

Все сценарии эксперимента описаны в формальных JSON-каталогах:

| Каталог | Путь | Содержимое |
|---------|------|-----------|
| Регрессионные сценарии | `scenarios/regression_catalog.json` | 5 сценариев (REG-001…REG-005) |
| Fault-injection сценарии | `scenarios/fault_catalog.json` | 8 сценариев (FLT-001…FLT-008) |

Дополнительно в Python-коде определены 3 baseline-сценария (BAS-001…BAS-003) в `experiments/data_contracts/schemas.py`.

### Поля каждого сценария

| Поле | Описание |
|------|----------|
| `scenario_id` | Уникальный идентификатор (REG-001, FLT-003, …) |
| `scenario_group` | Группа: `regression`, `fault`, `baseline` |
| `description` | Описание на английском |
| `injection_point` | Точка инъекции неисправности |
| `expected_effect` | Ожидаемый эффект |
| `expected_detection` | Должен ли сценарий быть обнаружен |
| `expected_localization` | Должен ли быть локализован |
| `relevant_signals` | Релевантные сигналы наблюдаемости |
| `applicable_modes` | Режимы, в которых сценарий применим |
| `expected_strongest_mode` | Ожидаемый наиболее эффективный режим |

### Regression scenarios (REG-*)

| ID | Название | Тип |
|----|----------|-----|
| REG-001 | Incompatible response structure change | Contract regression |
| REG-002 | Hidden business regression | Business regression |
| REG-003 | Edge-case behavior change | Edge-case regression |
| REG-004 | Pipeline branch break | Pipeline-branch regression |
| REG-005 | Partial contract violation | Partial compatibility break |

### Fault scenarios (FLT-*)

| ID | Название | Класс |
|----|----------|-------|
| FLT-001 | Latency injection | latency |
| FLT-002 | Timeout | timeout |
| FLT-003 | Dependency failure | dependency_down |
| FLT-004 | Partial unavailability | partial_outage |
| FLT-005 | Resource degradation | resource_pressure |
| FLT-006 | Network degradation | network_fault |
| FLT-007 | Correlation loss | correlation_break |
| FLT-008 | Signal sparsity | signal_loss |

### Загрузка каталога из кода

```python
from scenarios import load_regression_catalog, load_fault_catalog, load_all_catalogs, scenario_by_id

reg = load_regression_catalog()          # 5 ScenarioSpec
flt = load_fault_catalog()               # 8 ScenarioSpec
all_sc = load_all_catalogs()             # 13 ScenarioSpec
idx = scenario_by_id(all_sc)             # dict[scenario_id → ScenarioSpec]
```

---

## 17. Запуск матричных экспериментов и генерация датасета

### Единый entrypoint

```bash
# Полная матрица: все сценарии × режимы × obs_levels × N повторов
python -m experiments

# Эквивалентный альтернативный entrypoint
python -m experiments.comparison.run_matrix
```

### Матрица эксперимента

| Режим | Сценарии | Obs levels | Повторы |
|-------|----------|-----------|---------|
| A0 | Все (BAS + REG + FLT) | — | N_REPEATS |
| A1 | Только REG-* | — | N_REPEATS |
| A2 | Только FLT-* | O0, O1, O2 | N_REPEATS |
| A3 | Только FLT-* | O1 | N_REPEATS |

По умолчанию `N_REPEATS = 3`. С 16 сценариями это даёт ~150 прогонов.

### Параметры CLI

```bash
python -m experiments --help

# --repeats N     # количество повторов (по умолчанию 3)
# --no-figures    # пропустить экспорт графиков
# --output DIR    # директория вывода (по умолчанию experiments/results)
```

### Что происходит при запуске

1. **Step 1/4**: Прогон матрицы экспериментов → `raw_runs.jsonl` + `aggregated.csv`
2. **Step 2/4**: Генерация таблиц и резюме → `tables/*.csv` + `summary/*.json` + `summary/*.md`
3. **Step 3/4**: Построение case studies → `casestudies/*.json`
4. **Step 4/4**: Экспорт научных графиков → `figures/*.png`

---

## 18. Data contract и структура результатов

### RawRunRecord — одна строка датасета

Каждый прогон записывается как строка в `raw_runs.jsonl` с полями:

| Поле | Тип | Описание |
|------|-----|----------|
| `run_id` | str | Уникальный ID прогона |
| `timestamp` | str | ISO-8601 timestamp |
| `git_sha` | str | Коммит, на котором запущено |
| `mode` | str | A0 / A1 / A2 / A3 |
| `obs_level` | str | O0 / O1 / O2 |
| `scenario_id` | str | REG-001, FLT-003, … |
| `scenario_group` | str | regression / fault / baseline |
| `fault_class` | str | Класс неисправности |
| `fault_target` | str | Цель инъекции |
| `workload_id` | str | Идентификатор нагрузки |
| `repeat_idx` | int | Номер повтора |
| `expected_detection` | bool | Ожидается ли обнаружение |
| `expected_localization` | bool | Ожидается ли локализация |
| `actual_detection` | bool | Фактически обнаружено |
| `actual_localization` | bool | Фактически локализовано |
| `time_to_detect_ms` | float? | Время до обнаружения |
| `time_to_localize_ms` | float? | Время до локализации |
| `signal_types_used` | str | Использованные сигналы (через запятую) |
| `signal_usefulness_score` | float | Полезность сигналов (0.0–1.0) |
| `regressions_found` | int | Найденные регрессии |
| `exvivo_match_rate` | float | Доля совпадений replay |
| `latency_mean_ms` | float | Средняя задержка |
| `latency_p95_ms` | float | P95 задержка |
| `latency_p99_ms` | float | P99 задержка |
| `throughput_rps` | float | Пропускная способность |
| `variance_growth` | float | Рост дисперсии |
| `resource_overhead_kb` | int | Overhead по памяти (KB) |
| `notes` | str | Пояснения |

### AggregatedResult

Агрегаты по группам `(mode, obs_level, scenario_group)`:

- `detection_rate` / `localization_rate`
- `mean_time_to_detect_ms` / `mean_time_to_localize_ms`
- `mean_signal_usefulness`
- `total_regressions_found` / `mean_exvivo_match_rate`
- `mean_latency_ms` / `p95_latency_ms` / `p99_latency_ms`
- `mean_throughput_rps` / `mean_variance_growth` / `mean_overhead_kb`
- `ci_detection_lower` / `ci_detection_upper` (95% CI)

### Структура выходных файлов

```
experiments/results/
├── raw_runs.jsonl            # Сырые данные прогонов
├── aggregated.csv            # Агрегированные результаты
├── tables/                   # CSV-таблицы для диплома
│   ├── detection_by_mode.csv
│   ├── detection_by_mode_obs.csv
│   ├── overhead_by_obs.csv
│   ├── scenario_matrix.csv
│   ├── fault_heatmap.csv
│   └── exvivo_match_rates.csv
├── summary/                  # Резюме и метаданные
│   ├── experiment_summary.json
│   ├── experiment_summary.md
│   └── reproducibility.json
├── figures/                  # Научные графики
│   ├── 01_verification_summary.png
│   ├── 02_test_stack_composition.png
│   ├── ...
│   └── 12_incident_timeline.png
└── casestudies/              # Case-study артефакты
    ├── REG-001_case_study.json
    └── FLT-003_case_study.json
```

---

## 19. Агрегация и таблицы для диплома

### Модуль агрегации

```python
from experiments.analysis.statistics import (
    detection_rate_by_mode,
    detection_rate_by_mode_obs,
    localization_rate_by_mode_obs,
    time_to_detect_distribution,
    exvivo_match_rates,
    fault_observability_heatmap_data,
    overhead_by_obs_level,
    signal_contribution,
    usefulness_vs_cost,
    scenario_matrix,
    verification_summary,
    generate_diploma_tables,
)

# Генерация всех 13 таблиц для диплома
tables = generate_diploma_tables("experiments/results")
```

### Группировки

Агрегация поддерживает группировки по:

- `mode` (A0, A1, A2, A3)
- `obs_level` (O0, O1, O2)
- `fault_class`
- `scenario_group` (regression, fault, baseline)
- `scenario_id`

### Экспорт таблиц

```python
from experiments.sciexport import export_diploma_tables
from experiments.dataset.writer import DatasetWriter

writer = DatasetWriter(output_dir="experiments/results")
records = writer.load_raw_runs()
paths = export_diploma_tables(records, output_dir="results/tables")
# → ['results/tables/detection_by_mode.csv', 'results/tables/scenario_matrix.csv', ...]
```

---

## 20. Визуализация и научные графики

### 12 обязательных графиков

| № | График | Функция |
|---|--------|---------|
| 1 | Verification Summary | `plot_verification_summary()` |
| 2 | Test Stack Composition | `plot_test_stack_composition()` |
| 3 | Scenario Detection Matrix | `plot_scenario_matrix()` |
| 4 | A0/A1/A2/A3 Comparative View | `plot_comparative_view()` |
| 5 | Ex-vivo Funnel | `plot_exvivo_funnel()` |
| 6 | Ex-vivo vs Baseline by Regression Type | `plot_exvivo_vs_baseline()` |
| 7 | Fault Observability Heatmap | `plot_fault_observability_heatmap()` |
| 8 | TTD / TTL Distributions | `plot_time_to_detect_distribution()` |
| 9 | Signal Contribution Plot | `plot_signal_contribution()` |
| 10 | Overhead by Observability Level | `plot_overhead_by_obs_level()` |
| 11 | Pareto: Usefulness vs Cost | `plot_pareto_usefulness_vs_cost()` |
| 12 | Incident Timeline / Case Study | `plot_incident_timeline()` |

### Использование из кода

```python
from experiments.visualization.plots import plot_comparative_view
from experiments.visualization.export import export_figure
import pandas as pd

df = pd.read_json("experiments/results/raw_runs.jsonl", lines=True)
fig = plot_comparative_view(df)
export_figure(fig, "comparative", output_dir="results/figures", formats=("png", "svg"))
```

### Экспорт всех графиков

```python
from experiments.visualization.export import export_all_plots
paths = export_all_plots(output_dir="results/figures", formats=("png", "svg"))
```

### Dash-дашборд

```bash
# Запуск интерактивного дашборда (http://localhost:8050)
python -c "from experiments.dashboard import run_dashboard; run_dashboard()"
```

Дашборд содержит 6 вкладок:
1. **Verification** — Summary + test stack composition
2. **Comparative** — Scenario matrix + A0/A1/A2/A3 сравнение (с фильтрами)
3. **Fault** — Fault heatmap + TTD distribution
4. **Ex-vivo** — Funnel + vs baseline
5. **Overhead** — Overhead + Pareto + signal contribution
6. **Case Study** — Incident timeline

### Структура модуля визуализации

```
visualization/                     # Top-level convenience package
├── plots/
│   ├── build_verification.py      # Verification + test stack
│   ├── build_comparison.py        # Scenario matrix + comparative
│   ├── build_exvivo.py            # Ex-vivo funnel + vs baseline
│   ├── build_fault_obs.py         # Fault heatmap + TTD
│   ├── build_overhead.py          # Overhead + Pareto + signals
│   └── build_case_studies.py      # Incident timeline
├── dashboard/                     # Re-exports Dash app
└── notebooks/                     # Jupyter analysis notebooks

experiments/visualization/         # Core implementations
├── plots.py                       # 12 plot functions (Plotly)
└── export.py                      # PNG/SVG/HTML export

experiments/dashboard/
└── app.py                         # Dash interactive dashboard
```

---

## 21. Case-study: анализ отдельных сценариев

### Минимальный набор

- **1 regression case** (по умолчанию REG-001): A1-режим
- **1 fault-localization case** (по умолчанию FLT-003): A2-режим

### Содержимое case-study артефакта

Каждый case-study (JSON) включает:

| Раздел | Описание |
|--------|----------|
| `scenario_id`, `scenario_group` | Идентификация |
| `run_ids`, `total_repeats` | Охват прогонов |
| `modes_tested`, `obs_levels_tested` | Какие режимы охвачены |
| `detection_rate`, `localization_rate` | Основные показатели |
| `mean_time_to_detect_ms`, `mean_time_to_localize_ms` | Временные метрики |
| `signal_types_used` | Использованные сигналы |
| `mean_latency_ms`, `mean_throughput_rps` | Нагрузочные показатели |
| `mean_resource_overhead_kb` | Overhead |
| `timeline` | Хронология событий (run → detection → localization) |

### Использование из кода

```python
from experiments.casestudy.builder import build_case_study, save_case_study
from experiments.dataset.writer import DatasetWriter

writer = DatasetWriter(output_dir="experiments/results")
records = writer.load_raw_runs()

# Построить case study для одного сценария
artifact = build_case_study(records, scenario_id="REG-001")
print(artifact.to_json())

# Сохранить как файл
save_case_study(artifact, output_dir="experiments/results/casestudies")
```

### Автоматическая генерация

При запуске `python -m experiments` case studies генерируются автоматически (Step 3/4).

---

## 22. Интерпретация результатов эксперимента

### Общие принципы

Результаты строятся **не по «128 passed»**, а по сравнительным данным A0/A1/A2/A3 и O0/O1/O2:

1. **Detection rate** по режимам → какой режим лучше обнаруживает
2. **Localization rate** → какой режим лучше локализует
3. **TTD/TTL** → как быстро обнаруживается / локализуется
4. **Overhead** → какова цена наблюдаемости по уровням O0/O1/O2
5. **Signal usefulness** → какие сигналы наиболее полезны
6. **Ex-vivo match rate** → воспроизводимость replay

### Ключевые вопросы исследования

| Вопрос | Где смотреть |
|--------|-------------|
| Добавляет ли A1 (ex-vivo) ценность сверх A0? | `exvivo_match_rates.csv`, ex-vivo funnel |
| Добавляет ли A2 (observability) ценность? | `detection_by_mode_obs.csv`, fault heatmap |
| Как уровень наблюдаемости влияет на detection? | `fault_heatmap.csv`, TTD distribution |
| Какова стоимость наблюдаемости? | `overhead_by_obs.csv`, Pareto chart |
| Есть ли синергия в A3 (combined)? | Comparative view, scenario matrix |
| Какие сигналы наиболее полезны? | Signal contribution plot |

### Пример интерпретации

**Detection by mode (из `detection_by_mode.csv`):**

| Mode | Total | Detected | Rate |
|------|-------|----------|------|
| A0 | 48 | 0 | 0.00 |
| A1 | 15 | 5 | 0.33 |
| A2 | 72 | 48 | 0.67 |
| A3 | 24 | 20 | 0.83 |

**Вывод**: A0 (baseline testing) не обнаруживает runtime-дефекты. A1 (ex-vivo) находит регрессии. A2 (observability + fault injection) обнаруживает большинство runtime-сбоев. A3 (combined) даёт наилучший результат за счёт синергии.

**Overhead by obs_level (из `overhead_by_obs.csv`):**

| Obs level | Mean latency | Mean throughput | Mean overhead KB |
|-----------|-------------|----------------|------------------|
| O0 | 5.2 ms | 180 rps | 0 |
| O1 | 8.1 ms | 155 rps | 64 |
| O2 | 14.3 ms | 120 rps | 256 |

**Вывод**: O2 даёт максимальную наблюдаемость, но ценой ~2.7× overhead по latency. O1 — оптимальный баланс.

---

## 23. Отчёт по исследовательскому слою

### Что реализовано

| Требование | Статус | Модуль |
|-----------|--------|--------|
| Data contract (RawRunRecord) | ✅ | `experiments/data_contracts/schemas.py` |
| Scenario catalog (JSON) | ✅ | `scenarios/regression_catalog.json`, `scenarios/fault_catalog.json` |
| Runner export (raw_runs.jsonl) | ✅ | `experiments/run_experiments.py` + `experiments/dataset/writer.py` |
| Aggregation layer | ✅ | `experiments/analysis/statistics.py` + `experiments/sciexport.py` |
| Повторы (N_REPEATS) | ✅ | `experiments/run_experiments.py` (default=3) |
| Матричный запуск | ✅ | `python -m experiments` |
| 12 научных графиков | ✅ | `experiments/visualization/plots.py` |
| Dash dashboard | ✅ | `experiments/dashboard/app.py` |
| Case studies (REG + FLT) | ✅ | `experiments/casestudy/builder.py` |
| Таблицы для диплома (CSV) | ✅ | `experiments/sciexport.py` |
| Reproducibility metadata | ✅ | `experiments/sciexport.py` |
| Summary (JSON + Markdown) | ✅ | `experiments/sciexport.py` |
| Статические графики (PNG/SVG) | ✅ | `experiments/visualization/export.py` |

### Критерии приёмки

| Критерий | Выполнен |
|---------|---------|
| После прогона появляются `raw_runs` и `aggregated_results` | ✅ |
| Есть формальный scenario catalog | ✅ (JSON + Python) |
| Эксперименты запускаются матрично | ✅ (A0/A1/A2/A3 × O0/O1/O2 × repeats) |
| Минимум 5 научных графиков | ✅ (12 графиков) |
| Минимум 1 regression + 1 fault case study | ✅ (REG-001 + FLT-003) |
| Таблицы и картинки для диплома без ручного копирования | ✅ |
| Выводы по сравнительным данным A0/A1/A2/A3 | ✅ |
