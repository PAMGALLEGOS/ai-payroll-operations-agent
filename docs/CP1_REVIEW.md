# CP1 Review Package — Núcleo determinista de validación

**Proyecto:** AI Payroll Operations & Validation Agent (PoC académico, solo datos sintéticos)
**Checkpoint:** CP1 — Fases 1, 2 y 3
**Preparado por:** Klaudio para Pam (revisión: Zury)
**Fecha:** 3 de octubre de 2026
**Estado:** Completo — **esperando aprobación**. No se inició nada de CP2.

---

## Resumen

El núcleo determinista funciona de punta a punta. Desde un clon limpio, con un entorno virtual nuevo en Python 3.11:

- **86 de 86 tests pasan, 0 fallan.**
- El batch valida 30 empleados × 3 validaciones = **90 resultados**: 76 PASS y 14 FAIL (14 excepciones).
- Cada resultado coincide con el escenario diseñado para ese empleado.
- No se necesita ninguna API key.

Hay **cuatro decisiones nuevas que requieren aprobación** (sección 12). La más importante es N1: con las reglas aprobadas, el campo `exception` siempre vale lo mismo que `status == FAIL`.

---

## 1. Estructura final del repositorio

```
ai-payroll-agent/
├── app/
│   ├── core/
│   │   ├── contracts.py        # ValidationResult, ValidationStatus, ReasonCode, RunContext
│   │   └── paths.py            # rutas canónicas del repo
│   ├── validation/             # ← CP1: el Validation Engine
│   │   ├── __init__.py         # ENGINE_VERSION
│   │   ├── rules_loader.py     # lee y valida config/validation_rules.yaml
│   │   ├── money.py            # parseo exacto con Decimal
│   │   ├── data_loader.py      # lee los CSV sintéticos (solo estructura)
│   │   ├── engine.py           # cálculo → comparación → tolerancia → resultado
│   │   └── batch.py            # corrida batch, resumen, persistencia versionada
│   ├── llm/  rag/  agent/  audit/  observability/  api/  web/   # vacíos (CP2–CP4)
├── config/
│   └── validation_rules.yaml   # fuente única de verdad (D16)
├── data/
│   ├── synthetic_payroll/      # inputs, valores del proveedor, manifiesto de escenarios
│   └── validation_results/     # corridas batch (generadas localmente, no se versionan)
├── knowledge/{sops,rules,blueprint}/   # vacíos (CP2)
├── tests/
│   ├── conftest.py, helpers.py
│   ├── unit/                   # 8 archivos, 86 tests
│   ├── integration/  evaluation/        # vacíos (CP3–CP5)
├── scripts/
│   ├── generate_synthetic_data.py
│   └── run_validation.py
├── docs/CP1_REVIEW.md          # este documento
├── logs/
├── pyproject.toml              # configuración de pytest
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 2. Archivos creados

Todo es nuevo; no se modificó nada existente. El repo tiene un commit inicial de git.

| Grupo | Archivos |
|---|---|
| Configuración y entorno | `requirements.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `README.md` |
| Reglas | `config/validation_rules.yaml` |
| Contratos | `app/core/contracts.py`, `app/core/paths.py` |
| Engine | `app/validation/__init__.py`, `rules_loader.py`, `money.py`, `data_loader.py`, `engine.py`, `batch.py` |
| Scripts | `scripts/generate_synthetic_data.py`, `scripts/run_validation.py` |
| Datos sintéticos | `data/synthetic_payroll/payroll_inputs_2026-09.csv`, `provider_results_2026-09.csv`, `scenario_manifest_2026-09.csv` |
| Tests | `tests/conftest.py`, `tests/helpers.py`, 8 archivos en `tests/unit/` |
| Placeholders | `__init__.py` de una línea en `app/llm`, `rag`, `agent`, `audit`, `observability`, `api`, `web`; `.gitkeep` en carpetas vacías |
| Revisión | `docs/CP1_REVIEW.md` |

## 3. Dataset sintético

Tres archivos, generados por un script con semilla fija: volver a correrlo produce archivos idénticos byte a byte (hay un test que lo verifica).

| Archivo | Qué es | Rol en el patrón |
|---|---|---|
| `payroll_inputs_2026-09.csv` | 30 empleados con inputs crudos: `base_salary`, `overtime_pay`, `deduction_tax`, `deduction_social_security`, `deduction_benefits` | Lo que el Engine usa para **calcular** |
| `provider_results_2026-09.csv` | Valores que "reportó" el proveedor sintético (29 registros) | Contra lo que el Engine **compara** |
| `scenario_manifest_2026-09.csv` | El resultado **diseñado** por empleado y validación | Oráculo independiente para los tests |

- País `SYNTHETIC`, moneda `SYN`, periodo `2026-09`.
- **Sin nombres ni atributos personales**: solo `EMP001`–`EMP030`. Un test verifica que las columnas sean exactamente las permitidas.
- Los montos son aleatorios con semilla fija; los porcentajes de deducción son sintéticos y no representan ninguna legislación.

**Escenarios:**

| Empleado | Escenario | Gross | Deductions | Net |
|---|---|---|---|---|
| EMP001–018 | Coincidencia exacta | PASS | PASS | PASS |
| EMP019 | Diferencia positiva dentro de tolerancia (+2.50) | PASS | PASS | PASS |
| EMP020 | Diferencia negativa dentro de tolerancia (−4.99) | PASS | PASS | PASS |
| EMP021 | **Exactamente en la tolerancia** de gross (+5.00) | PASS | PASS | PASS |
| EMP022 | **Exactamente en la tolerancia** de net, negativa (−10.00) | PASS | PASS | PASS |
| EMP023 | Un centavo arriba de la tolerancia de gross (+5.01) | FAIL | PASS | PASS |
| EMP024 | Net 350.00 arriba (sobrepago) | PASS | PASS | FAIL |
| EMP025 | Deducciones 120.00 abajo | PASS | FAIL | FAIL |
| EMP026 | Gross 250.00 abajo (diferencia negativa) | FAIL | PASS | FAIL |
| EMP027 | `overtime_pay` vacío | FAIL `MISSING_INPUT` | PASS | FAIL `MISSING_INPUT` |
| EMP028 | Proveedor no reportó net pay | PASS | PASS | FAIL `MISSING_INPUT` |
| EMP029 | `deduction_benefits` negativo | PASS | FAIL `INVALID_INPUT` | FAIL `INVALID_INPUT` |
| EMP030 | Sin registro del proveedor | FAIL `MISSING_INPUT` | FAIL `MISSING_INPUT` | FAIL `MISSING_INPUT` |

Los escenarios de límite (EMP020–EMP023) se calculan a partir de las tolerancias del YAML, no están fijados a mano.

## 4. Reglas implementadas

Todas viven en `config/validation_rules.yaml` (`rules_version: 1.0.0`).

| validation_type | Fórmula | Campo del proveedor | Tolerancia |
|---|---|---|---|
| `gross_pay` | `base_salary + overtime_pay` | `provider_gross_pay` | 5.00 SYN |
| `total_deductions` | `deduction_tax + deduction_social_security + deduction_benefits` | `provider_total_deductions` | 5.00 SYN |
| `net_pay` | `gross_pay − total_deductions` | `provider_net_pay` | 10.00 SYN |

- `difference = actual_value − expected_value`, con signo conservado.
- `abs(difference) <= tolerance` → **PASS**. El límite exacto es PASS.
- Todo el dinero se maneja en `Decimal`. Las tolerancias van entre comillas en el YAML para que nunca pasen por `float`; el loader rechaza una tolerancia sin comillas.
- Las fórmulas no se ejecutan como código: el YAML declara una operación (`sum` o `subtract`) y el Engine solo implementa esas dos. Una operación desconocida, una tolerancia negativa o una regla de tolerancia distinta a la aprobada hacen que el loader se detenga con un error claro.
- `net_pay` usa los valores **calculados** de gross y deductions, nunca los del proveedor (hay un test para esto).

**Cómo fluye un resultado** (`app/validation/engine.py`, una función por paso del patrón aprobado):

```
inputs crudos ──► calculate_expected ──┐
                                       ├─► compare (actual − expected) ──► evaluate_tolerance ──► ValidationResult
valor proveedor ─► read_provider_value ┘
        (si falta o es inválido en cualquier lado → FAIL + exception + reason_code de calidad de datos)
```

## 5. Ejemplo de resultado PASS

```json
{
  "employee_id": "EMP001",
  "country": "SYNTHETIC",
  "currency": "SYN",
  "period": "2026-09",
  "validation_type": "net_pay",
  "expected_value": "3544.28",
  "actual_value": "3544.28",
  "difference": "0.00",
  "tolerance": "10.00",
  "status": "PASS",
  "exception": false,
  "reason_code": "WITHIN_TOLERANCE",
  "detail": "abs(difference) 0.00 <= tolerance 10.00",
  "engine_version": "0.1.0",
  "rules_version": "1.0.0",
  "run_id": "RUN-2026-09-20261003T212752Z",
  "run_timestamp": "2026-10-03T21:27:52Z"
}
```

## 6. Ejemplo de resultado FAIL

```json
{
  "employee_id": "EMP024",
  "country": "SYNTHETIC",
  "currency": "SYN",
  "period": "2026-09",
  "validation_type": "net_pay",
  "expected_value": "3732.48",
  "actual_value": "4082.48",
  "difference": "350.00",
  "tolerance": "10.00",
  "status": "FAIL",
  "exception": true,
  "reason_code": "OUT_OF_TOLERANCE",
  "detail": "abs(difference) 350.00 > tolerance 10.00",
  "engine_version": "0.1.0",
  "rules_version": "1.0.0",
  "run_id": "RUN-2026-09-20261003T212752Z",
  "run_timestamp": "2026-10-03T21:27:52Z"
}
```

## 7. Ejemplo de excepción de calidad de datos

EMP027 tiene `overtime_pay` vacío. El gross no se puede calcular:

```json
{
  "employee_id": "EMP027",
  "validation_type": "gross_pay",
  "expected_value": null,
  "actual_value": "7331.29",
  "difference": null,
  "tolerance": "5.00",
  "status": "FAIL",
  "exception": true,
  "reason_code": "MISSING_INPUT",
  "detail": "Expected value not calculated: overtime_pay value is missing",
  "...": "country, currency, period, versiones y run igual que arriba"
}
```

Y el problema se **propaga** a `net_pay`, con la causa raíz en el `detail`:

```
"reason_code": "MISSING_INPUT",
"detail": "Expected value not calculated: upstream gross_pay not calculable (overtime_pay value is missing)"
```

`total_deductions` del mismo empleado sí se valida normalmente (PASS): un input faltante solo afecta a las validaciones que dependen de él.

## 8. Dónde quedan los resultados batch

```
data/validation_results/
├── validation_run_2026-09-20261003T212752Z.json   # archivo de la corrida, inmutable
└── latest_2026-09.json                            # apunta a la corrida más reciente
```

Cada archivo de corrida tiene tres partes:

- **`run`** — encabezado de auditoría: `run_id`, `run_timestamp`, `engine_version`, `rules_version`, SHA-256 del YAML de reglas y de los dos CSV, y `results_fingerprint`.
- **`summary`** — conteos deterministas (D14): empleados validados, total, PASS, FAIL, excepciones, empleados con excepción, conteo por `reason_code` y por `validation_type`, y registros del proveedor sin empleado correspondiente.
- **`results`** — los 90 resultados estructurados.

Dos controles de auditoría:

- **Inmutabilidad:** un archivo de corrida nunca se sobrescribe; si ya existe, el batch se detiene.
- **Repetibilidad:** el `results_fingerprint` es un hash de los resultados **sin** `run_id` ni `run_timestamp`. Dos corridas con los mismos inputs, reglas y versión del Engine dan el mismo fingerprint aunque se ejecuten en momentos distintos. Si cambia un solo resultado, el fingerprint cambia.

## 9. Resumen de ejecución de tests

```
python -m pytest -q
86 passed in 0.17s
```

| Archivo | Tests | Qué cubre |
|---|---|---|
| `test_money.py` | 13 | Decimal exacto, faltante, no numérico, negativo, exceso de decimales sin redondeo silencioso |
| `test_rules_loader.py` | 11 | Carga del YAML; rechazo de tolerancia sin comillas, negativa, operación desconocida, regla de tolerancia no soportada, referencias fuera de orden, duplicados, llaves faltantes |
| `test_engine_calculations.py` | 8 | Cálculo de gross, deductions y net; net usa valores calculados; signo de la diferencia; diferencia negativa; contrato del resultado |
| `test_tolerance.py` | 26 | Debajo, exactamente en, y arriba de la tolerancia, en positivo y negativo, para los 3 tipos |
| `test_exceptions.py` | 9 | `MISSING_INPUT`, `INVALID_INPUT`, propagación, valor del proveedor faltante, sin registro del proveedor, `exception` vs `status`, reason codes |
| `test_repeatability_and_batch.py` | 8 | Repetibilidad, fingerprint, orden estable, persistencia versionada, puntero, inmutabilidad, consistencia del resumen |
| `test_synthetic_dataset.py` | 5 | Tamaño, sin datos personales, todos los escenarios presentes, generador determinista, **Engine vs escenarios diseñados** |
| `test_data_loader.py` | 6 | Archivo faltante, columnas faltantes, duplicados, periodos mezclados |

**Control adicional:** cambié temporalmente la regla de límite de `<=` a `<` para confirmar que los tests detectan el error. Fallaron 9 tests y volvieron a pasar al restaurar el código.

Cobertura de la lista mínima de la sección 9 de la autorización:

| Requisito | Cubierto en |
|---|---|
| Cálculo de gross / deductions / net | `test_engine_calculations.py` |
| Cálculo de la diferencia | `test_difference_is_actual_minus_expected` |
| PASS debajo / exactamente en / FAIL arriba de la tolerancia | `test_tolerance.py` |
| Diferencia negativa | `test_negative_difference_keeps_its_sign` + casos negativos en `test_tolerance.py` |
| Input requerido faltante | `test_exceptions.py` |
| Comportamiento de excepción y reason codes | `test_exceptions.py` |
| Carga de la configuración | `test_rules_loader.py` |
| Repetibilidad determinista | `test_repeatability_and_batch.py`, `test_generator_is_deterministic` |

## 10. Tests aprobados / fallidos

**86 aprobados, 0 fallidos.** Verificado desde un clon limpio con un entorno virtual nuevo en Python 3.11.

## 11. Desviaciones respecto a la autorización

Ninguna desviación funcional. Ajustes técnicos menores:

1. **`requirements.txt` solo tiene `PyYAML` y `pytest`.** D13 listaba también FastAPI, Streamlit, numpy, etc. Los agregaré en el checkpoint que los use, para que cada dependencia entre con su justificación. Siguen fijadas por versión.
2. **Archivos de soporte no listados en la spec:** `pyproject.toml` (configuración de pytest), `app/core/paths.py`, `tests/helpers.py`, `scripts/__init__.py` y `docs/`.
3. **Contratos con `dataclasses` y no con Pydantic.** Así el Engine no depende de ningún framework web. En CP4, la API traducirá estos contratos a modelos Pydantic.
4. **El resumen de conteos (D14) ya se genera en CP1**, dentro de cada archivo de corrida. Está aprobado en D14 y es parte del Engine determinista, por eso lo incluí ahora.
5. **Los archivos de corrida no se versionan en git** (están en `.gitignore`): se generan localmente. Los CSV sintéticos sí se versionan.

## 12. Decisiones técnicas nuevas que requieren aprobación

### N1 — `exception` siempre coincide con `status == FAIL`
Con las reglas aprobadas, toda excepción de datos se marca FAIL (la autorización mantiene solo PASS y FAIL). Por lo tanto, `exception` nunca difiere de `status == FAIL`; lo que distingue un problema de tolerancia de uno de datos es el `reason_code`. Es la misma redundancia que señalé en C2.
**Recomendación:** mantener el campo por compatibilidad con el contrato, y documentar que la distinción vive en `reason_code`. No hace falta cambiar código.

### N2 — Valores de tolerancia
La autorización aprobó el *tipo* de tolerancia, no los montos. Propuse **5.00 SYN** para gross y deductions, y **10.00 SYN** para net (net acumula dos componentes). Son sintéticos y se cambian solo en el YAML.
**Recomendación:** aprobar estos valores.

### N3 — Campos adicionales en el resultado
- `reason_code = WITHIN_TOLERANCE` para PASS. Así todo resultado tiene un motivo explícito, no solo los fallidos.
- `detail`: explicación legible del `reason_code` (por ejemplo, qué input falta). Lo necesitará el Agent para explicar sin recalcular.
- `run_id`: liga cada resultado con su corrida.

**Recomendación:** aprobar.

### N4 — Reglas de calidad de datos
- Inputs con más de 2 decimales → `INVALID_INPUT`. **No se redondean en silencio.**
- Montos negativos → `INVALID_INPUT` (configurable en el YAML).
- Si hay un problema inválido y uno faltante a la vez, gana `INVALID_INPUT`.
- El dinero se guarda como **texto** en el JSON (`"350.00"`), no como número, para no perder exactitud.

**Recomendación:** aprobar.

## 13. Comandos para correr CP1 localmente

Requiere Python 3.11.

```bash
cd ai-payroll-agent

python3.11 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate

pip install -r requirements.txt

python -m pytest -v                    # 86 tests

python scripts/run_validation.py --period 2026-09

# Opcional: regenerar el dataset (sale idéntico)
python scripts/generate_synthetic_data.py --period 2026-09
```

Salida esperada del batch:

```
Employees         : 30
Validations       : 90
PASS / FAIL       : 76 / 14
Exceptions        : 14
By reason code    : {'INVALID_INPUT': 2, 'MISSING_INPUT': 6, 'OUT_OF_TOLERANCE': 6, 'WITHIN_TOLERANCE': 76}
```

---

## Checklist del Definition of Done de CP1

| # | Criterio | Estado |
|---|---|---|
| 1 | Estructura del repositorio | ✅ |
| 2 | Entorno Python y dependencias definidos | ✅ Python 3.11, versiones fijadas |
| 3 | Dataset sintético | ✅ 30 empleados, 3 archivos |
| 4 | Configuración de reglas | ✅ `config/validation_rules.yaml` |
| 5 | El Engine ejecuta correctamente | ✅ |
| 6 | Expected calculado desde inputs crudos | ✅ |
| 7 | Valores del proveedor comparados contra expected | ✅ |
| 8 | PASS / FAIL determinista | ✅ |
| 9 | Diferencias y tolerancias en los resultados | ✅ |
| 10 | Excepciones y reason codes correctos | ✅ |
| 11 | Resultados batch persistidos y versionados | ✅ |
| 12 | Tests unitarios pasan | ✅ 86/86 |
| 13 | Sin credenciales de Gemini/API | ✅ |
| 14 | Sin datos reales de nómina o empleados | ✅ |
| 15 | Dentro del alcance aprobado | ✅ |

**Detenido. Esperando aprobación de CP1 y de N1–N4 antes de iniciar CP2.**
