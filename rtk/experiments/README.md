# Экспериментальный стенд: Сравнительное исследование testing ↔ monitoring

## 1. Обзор

Данный экспериментальный стенд реализует сравнительный анализ четырёх режимов
обеспечения качества микросервисной системы:

| Режим | Описание | Блоки |
|-------|----------|-------|
| **A0** | Классический baseline-тестирование | B |
| **A1** | Baseline + ex-vivo regression | B + D |
| **A2** | Baseline + fault injection + observability | B + C + E + F |
| **A3** | Комбинированный (все блоки) | B + C + D + E + F |

## 2. Структура проекта

```
experiments/
├── observability/           # Блок C: Observability-контур
│   ├── configs.py           # Три конфигурации O0/O1/O2
│   ├── collectors.py        # Сбор телеметрических сигналов
│   └── detectors.py         # Детекторы аномалий по метрикам/логам/трейсам
│
├── exvivo/                  # Блок D: Ex-vivo regression
│   ├── capture.py           # Захват runtime-взаимодействий
│   ├── normalize.py         # Нормализация (timestamps, IDs, nonces)
│   ├── replay.py            # Движок воспроизведения + сравнение
│   └── test_exvivo.py       # Тесты ex-vivo pipeline
│
├── fault_injection/         # Блок E: Fault injection
│   ├── faults.py            # 6 классов сбоев
│   ├── injector.py          # Механизм контролируемой инъекции
│   └── test_fault_observability.py  # Эксперименты fault observability
│
├── overhead/                # Блок F: Overhead
│   ├── benchmark.py         # Бенчмаркинг производительности
│   └── test_overhead.py     # Измерение overhead O0/O1/O2
│
├── comparison/              # Сравнительный фреймворк
│   ├── runner.py            # Оркестрация экспериментов A0–A3
│   ├── metrics.py           # Стандартизированные метрики
│   ├── report.py            # Генерация отчётов
│   └── test_comparison.py   # Интеграционные тесты сравнения
│
└── conftest.py              # Общие фикстуры

tests/                       # Блок B: Baseline test suite
├── conftest.py              # Фикстуры и reset storage
├── test_unit_models.py      # Unit-тесты моделей и сервисов
├── test_unit_pipeline.py    # Unit-тесты pipeline-логики
├── test_integration_services.py  # Integration-тесты сервисов
├── test_api_contract.py     # API/contract-тесты
└── test_e2e.py              # E2E/smoke-тесты
```

## 3. Блок A: Экспериментальный объект

**Система**: RTK Agent — микросервисная система обработки тикетов с LLM-интеграцией.

**Характеристики**:
- Несколько сервисов: Agent API, RAG Mock, MCP Server, LLM Provider
- HTTP/REST-взаимодействия (FastAPI)
- Межсервисные вызовы через MCP (Model Context Protocol)
- In-memory mock-хранилище (LOGS_DB, ORDERS_DB, EISSD_DB, OTRS_TICKETS)
- Docker Compose для развёртывания
- Prometheus-метрики

## 4. Блок B: Baseline test suite

### Unit-тесты (`tests/test_unit_models.py`, `test_unit_pipeline.py`)
- Нормализация статусов (OrderStatus, OtrsStatus)
- Dataclass-конструкторы (Ticket, ActionLogEntry)
- MCP-сервисы (OrderService, OtrsService)
- Pipeline-хелперы (_unwrap_mcp_dict, build_final_comment)
- Валидация Pydantic-моделей

### Integration-тесты (`tests/test_integration_services.py`)
- Cross-service workflow: search → update → verify
- OTRS ticket lifecycle
- Storage isolation between tests
- Multi-order operations

### API/contract-тесты (`tests/test_api_contract.py`)
- TicketIn / TicketOut schema validation
- RagRequest / RagResponse contracts
- RAG mock endpoint logic
- Serialisation round-trips

### E2E/smoke-тесты (`tests/test_e2e.py`)
- Health endpoint
- Metrics endpoint
- Full ticket intake (mocked pipeline)
- Timeout → 504, Error → 500
- Input validation → 422

## 5. Блок C: Observability-конфигурации

### O0 — Минимальная
- Error counters
- Health checks
- **Signal depth**: 2/9

### O1 — Средняя
- + Latency histograms
- + Structured logs
- + Basic traces
- **Signal depth**: 5/9

### O2 — Расширенная
- + Span attributes
- + Inter-service correlation
- + Resource metrics
- + Diagnostic signals
- **Signal depth**: 9/9

## 6. Блок D: Ex-vivo pipeline

### Этапы
1. **Capture** — запись runtime-взаимодействий (call_name, arguments, response)
2. **Normalize** — удаление нестабильных полей (timestamps, IDs, nonces)
3. **Replay** — воспроизведение сценариев и сравнение ответов
4. **Compare** — обнаружение регрессий через структурное сравнение

### Ключевые возможности
- JSON-сериализация/десериализация сценариев
- Trace context tracking
- Deterministic ID mapping
- Deep structural comparison с tolerance для float

## 7. Блок E: Fault injection

### 6 классов сбоев
| Класс | Описание | Параметры |
|-------|----------|-----------|
| `LATENCY` | Искусственная задержка | `delay_ms` |
| `TIMEOUT` | Симуляция timeout | `delay_ms` |
| `DEPENDENCY_FAILURE` | Отказ зависимости | `error_message`, `error_cls` |
| `PARTIAL_UNAVAILABLE` | Перемежающийся отказ | `failure_rate` |
| `RESOURCE_DEGRADATION` | Нагрузка на ресурсы | `cpu_burn_ms` |
| `NETWORK_DEGRADATION` | Сетевая деградация | `jitter_ms`, `corruption_rate` |

### Детекторы
- **MetricDetector** — error rate, latency spikes
- **LogDetector** — error patterns in structured logs
- **TraceDetector** — error spans, correlation analysis
- **CombinedDetector** — агрегация всех типов сигналов

### Измеряемые характеристики
- Detectability (обнаружен ли сбой)
- Time to detect (время до обнаружения)
- Localisability (локализован ли источник)
- Signal usefulness (какие сигналы помогли)

## 8. Блок F: Overhead

### Метрики
- Mean / Median / P95 / P99 latency
- Throughput (calls/sec)
- RSS delta (KB)
- Variance growth
- Error rate

### Сравнение
- Baseline (без инструментации) vs O0 vs O1 vs O2
- Latency overhead (ms, %)
- Throughput overhead (%)
- Variance growth factor

## 9. Метрики эксперимента

### Testing metrics
- `defects_found`, `defects_missed`, `false_positives`
- `detection_rate`, `false_positive_rate`
- `execution_time_ms`, `reproducibility_rate`

### Diagnostic metrics
- `time_to_detect_ms`, `time_to_localize_ms`
- `diagnosis_accuracy`, `signal_usefulness_score`
- Signal types used

### Overhead metrics
- `latency_overhead_ms/pct`, `throughput_overhead_pct`
- `resource_overhead_kb`, `outlier_growth`, `variance_growth`

### ExVivo metrics
- `match_rate`, `regression_rate`
- `replay_time_ms`, `replay_errors`

## 10. Запуск экспериментов

```bash
# Установка зависимостей
pip install -r requirements.txt
pip install pytest pytest-asyncio

# Запуск всех тестов
python -m pytest tests/ experiments/ -v

# Только baseline (A0)
python -m pytest tests/ -v -m "unit or integration or contract or e2e"

# Только ex-vivo (A1)
python -m pytest experiments/exvivo/ -v -m exvivo

# Только fault injection (A2)
python -m pytest experiments/fault_injection/ -v -m fault

# Только overhead (F)
python -m pytest experiments/overhead/ -v -m overhead

# Сравнительный фреймворк (A0–A3)
python -m pytest experiments/comparison/ -v

# Генерация отчёта
python -c "
from experiments.comparison.runner import run_a0, run_a1, run_a2, run_a3
from experiments.comparison.report import generate_text_report
results = [run_a0(), run_a1(), run_a2(), run_a3()]
print(generate_text_report(results))
"
```

## 11. Артефакты

| Артефакт | Расположение |
|----------|-------------|
| Описание стенда | `experiments/README.md` |
| Baseline test suite | `tests/` |
| Observability-конфигурации | `experiments/observability/configs.py` |
| Fault-сценарии | `experiments/fault_injection/faults.py` |
| Ex-vivo pipeline | `experiments/exvivo/` |
| Система сбора метрик | `experiments/comparison/metrics.py` |
| Генерация отчётов | `experiments/comparison/report.py` |
| Методика fault observability | `experiments/observability/detectors.py` |
| Методика overhead | `experiments/overhead/benchmark.py` |
| Оркестрация экспериментов | `experiments/comparison/runner.py` |
