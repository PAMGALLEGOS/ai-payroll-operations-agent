# CP4: estrategia de evidencia final con 20 solicitudes de Gemini por día

**Preparado por:** Klaudio · **Fecha:** 4 de octubre de 2026
**Estado:** APROBADA (EV-1, EV-2, F7d; EV-3 diferida a CP5). F7c y F7d implementados (regresión 507 passed). Las metas, el Agent, `app/`, el modelo, la facturación y los casos originales no cambian.

---

## 1. El problema

| Dato | Valor |
|---|---|
| Cuota diaria del free tier (`gemini-3.8-flash`) | **20 solicitudes por día**, por proyecto y modelo (confirmado por `quotaId`) |
| Lo que pide una evaluación completa de 56 casos con Gemini | ≈ 75–85 solicitudes |
| Conclusión | La evaluación completa con Gemini **no cabe en un día**. Hacerla en ~5 días necesitaría reanudar corridas parciales (más código y más riesgo). Habilitar facturación queda fuera por decisión de ustedes |

Lo que sí cabe es separar **qué mide cada evidencia**.

---

## 2. Principio: dos capas, dos evidencias, las mismas metas

| Capa | Qué demuestra | Dónde se mide | Costo en cuota |
|---|---|---|---|
| **Determinista**: Engine, contratos de ruteo, plantillas, Auditor, fallback, guardia de cuota | Que la arquitectura es correcta y segura **sin depender del LLM** | Evaluación completa de 56 casos con proveedor fake, más 497 tests offline e inyección de fallas | 0 |
| **Contribución real de Gemini**: clasifica la intención, genera texto aceptado por el Auditor, responde en el idioma correcto, reescribe al inglés para el RAG | Que **Gemini real** cumple su parte del contrato | Un **subconjunto estratificado, definido antes de correrlo**, de los mismos `routing_cases.yaml` | ≈ 17 de 20 |

**Las 7 metas no cambian.** Se aplican igual al subconjunto real: ruteo ≥ 90 %, aclaraciones 100 %, fuera de alcance ≥ 90 %, consistencia con el Engine 100 %, detección del Auditor 100 %, **intención por LLM 100 %** y **generación exitosa 100 %**. En un subconjunto pequeño, una meta de 100 % es **más exigente**, no menos: una sola falla de Gemini hace fallar la corrida.

---

## 3. El subconjunto real: regla fijada antes de correr

**Regla:** de `routing_cases.yaml`, sin modificarlo, se toma **el primer caso de cada combinación categoría × idioma**. Para "fuera de alcance" se agrega **el primer caso que decide el LLM**, porque el primero es una acción prohibida, la decide una regla antes del LLM y no ejercita a Gemini.

La regla se escribe en el código y en este documento **antes** de ver resultados. Es reproducible y cubre las 5 rutas en los 2 idiomas, así que no hay selección a conveniencia.

Calculé el costo con el proveedor fake contando las llamadas al LLM:

| Caso | Categoría | Idioma | Ruta esperada | Llamadas a Gemini |
|---|---|---|---|---|
| EN-R01 "What is the net pay tolerance?" | rag | EN | RAG | 2 |
| ES-R01 "¿Cuál es la tolerancia del pago neto?" | rag | ES | RAG | 2 (además **verifica N10**: búsqueda con reescritura al inglés) |
| EN-T01 "Did EMP024 pass validation?" | tool | EN | TOOL | 1 |
| ES-T01 "¿EMP024 pasó la validación?" | tool | ES | TOOL | 1 |
| EN-X01 "Why did EMP024 fail?" | tool_rag | EN | TOOL_RAG | 2 |
| ES-X01 "¿Por qué falló EMP024?" | tool_rag | ES | TOOL_RAG | 2 |
| EN-C01 / ES-C01 "Why did the employee fail?" | clarify_missing_employee | EN / ES | CLARIFY | 1 + 1 |
| EN-C04 / ES-C04 "Compare EMP023 and EMP024" | clarify_other | EN / ES | CLARIFY | 1 + 1 |
| EN-O01 / ES-O01 "Approve the payroll" | out_of_scope (regla) | EN / ES | OUT_OF_SCOPE | 0 + 0 |
| EN-O04 / ES-O04 "What is the capital of France?" | out_of_scope (LLM) | EN / ES | OUT_OF_SCOPE | 1 + 1 |
| **14 casos** | | | | **16** |

Presupuesto del día:

| Concepto | Solicitudes |
|---|---|
| Verificación previa (F7c) | 1 |
| 14 casos | 16 |
| Margen para una reescritura del Auditor o un reintento | 3 |
| **Total** | **20** |

- **No corremos `diagnose_llm.py` ni los canarios directos ese día.** El subconjunto ya ejercita las dos llamadas del canario: la intención (JSON) y la generación (texto).
- **Si se gasta el margen:** el guardia de F7c detiene la corrida, que queda `INCONCLUSIVE`, nunca un falso FAIL. Se repite al día siguiente.

---

## 4. Paquete de evidencia final de CP4

| # | Evidencia | Muestra | Estado actual |
|---|---|---|---|
| E1 | Regresión offline | 497 tests | ✅ |
| E2 | Evaluación completa de la capa determinista (proveedor fake) | 56 casos EN/ES, 7 metas | ✅ PASS |
| E3 | Inyección de fallas: un LLM que falla **no puede** aprobar la evaluación; la cuota agotada da INCONCLUSIVE y corta la corrida | Tests de F3, F7a y F7c | ✅ |
| E4 | **Gemini real, subconjunto estratificado**: las mismas 7 metas, más el chequeo N10 | 14 casos | ⏳ un día de cuota |
| E5 | Log de esa corrida: `llm_fallback` = 0, `provider_errors` vacío, `quota_guard` sin activarse | — | ⏳ junto con E4 |
| E6 | Diagnóstico de la causa raíz F6 (nombre del modelo) y de la cuota (`PerDay`, 20) | — | ✅ (salidas de Pam/Zury) |

**Limitación declarada**, que va así en la evidencia de CP4:

> La contribución de Gemini se midió con 14 casos reales estratificados (todas las rutas, ambos idiomas) con las metas originales. La capa determinista se midió con los 56 casos. Con 14 casos, una sola falla de ruteo cambia la tasa en ~7 puntos, así que el resultado demuestra que Gemini cumple el contrato en cada ruta e idioma. No estima con precisión su tasa de error en la población completa. La evaluación de los 56 casos con Gemini queda pendiente de una cuota mayor (decisión para CP5) y se corre con el mismo comando.

**Resultados de CP3 con Gemini:** las métricas que dependían del LLM se marcan como **reemplazadas por E4** (se invalidaron en el hallazgo de CP4). Las deterministas de CP3 siguen siendo válidas.

---

## 5. F7d (solo el arnés) — implementado

| Cambio | Archivo |
|---|---|
| Opción `--case-set stratified`, que aplica la regla de la sección 3 sobre `routing_cases.yaml` sin modificarlo. Por defecto, `full`, con el comportamiento actual | `scripts/evaluate_agent.py` |
| El reporte incluye `case_set`, la lista de ids corridos y el presupuesto estimado frente a las solicitudes usadas | `scripts/evaluate_agent.py` |
| Chequeo N10 dentro del reporte: para los casos RAG en español, la consulta de búsqueda es inglés. Se lee con un espía de solo lectura, como el test N10 actual | `scripts/evaluate_agent.py` |
| Tests offline: la regla elige exactamente esos 14 ids; el costo con el fake es 16; `full` no cambia; el chequeo N10 se reporta | `tests/` |

**Sin cambios:** las metas (las mismas constantes `TARGETS`), los casos, el Agent y `app/`.

**Comando del día** (con F7c, F7a y F7d):

```bash
python scripts/evaluate_agent.py --provider gemini --case-set stratified --min-interval 13 --out cp4_gemini_stratified.json
```

Dura ≈ 4 minutos. Después, `EVAL_AGENT_REPORT=cp4_gemini_stratified.json python -m pytest -m eval -k "not canary" -v` valida las metas y N10 desde el JSON, **sin gastar cuota de generación**.

---

## 6. Decisiones

| # | Decisión | Opciones |
|---|---|---|
| EV-1 | Estrategia de dos capas (E1–E6) como evidencia final de CP4 | **Aprobar** / Ajustar |
| EV-2 | Regla del subconjunto (primer caso por categoría × idioma + un caso de fuera de alcance decidido por el LLM) | **Aprobar** / Otra regla (antes de correr) |
| F7d | `--case-set stratified` + chequeo N10 en el reporte (solo el arnés) | **Aprobar** / No aprobar |
| EV-3 | Evaluación completa de 56 casos con Gemini | **Diferir a CP5** (requiere cuota mayor) / Otra |

**F7c y F7d implementados. La corrida real con Gemini la hacen Pam/Zury tras el reinicio de la cuota (ver `CP4_QA_FIX_F1_F7d.md`, sección 5). CP5 no autorizado.**

---

## 7. Cierre de ejecución real y despliegue en GCP — 4 de octubre de 2026

### 7.1 Resultado de la evaluación estratificada con Gemini

La evaluación real estratificada de 14 casos fue ejecutada posteriormente. La corrida alcanzó 11 de 14 casos antes de detenerse por errores del proveedor/cuota.

Resultados observados antes de la detención:

- Routing accuracy: 100 %
- Clarify handling: 100 %
- Out-of-scope handling: 100 %
- Agent ↔ Validation Engine consistency: 100 %
- Seeded Auditor detection: 100 %
- N10 (reescritura para recuperación RAG): PASS
- Intent LLM rate: 33.3 %
- Generation success rate: 50 %

La corrida se clasificó como **INCONCLUSIVE**, no como FAIL de calidad, debido a errores del proveedor (HTTP 429 y HTTP 503) y al mecanismo de early stop después de tres errores 429 consecutivos.

La evidencia original se conserva en:

`cp4_gemini_stratified_INCONCLUSIVE_2026-10-04.json`

Por integridad de la evidencia, esta corrida no se reinterpretó posteriormente como PASS.

### 7.2 Despliegue funcional en Google Cloud Run

El PoC fue desplegado exitosamente en Google Cloud Run utilizando el paquete de despliegue preparado para el proyecto.

- Service: `payroll-agent`
- Region: `us-central1`
- Revision: `payroll-agent-00001-5pd`
- Traffic: 100 %
- Public application URL: `https://payroll-agent-190772421839.us-central1.run.app`
- Runtime: Cloud Run
- Secret management: Google Secret Manager
- Gemini API key: inyectada en runtime mediante Secret Manager; no almacenada en el repositorio
- Maximum instances: 1
- Application topology: Streamlit público → FastAPI/Uvicorn interno → Agent / Engine / RAG / Auditor

El dashboard desplegado cargó correctamente el dataset sintético y mostró el estado general del sistema como operativo.

### 7.3 Prueba end-to-end real en Cloud Run

Después de habilitar el entorno pagado de Gemini API, se ejecutó una prueba controlada en la aplicación desplegada:

**Pregunta:** `¿Por qué falló EMP024?`

**Resultado:** respuesta exitosa mediante la ruta `TOOL_RAG`.

La traza de Cloud Run confirmó la siguiente secuencia:

`request_received → llm_called (intent) → intent_identified → tool_called → engine_result → rag_retrieved → llm_called → auditor_result → route_decided → response_completed`

Datos principales de la ejecución:

- Trace ID: `TRACE-4f596f6a`
- Intent: `validation_explanation`
- Employee: `EMP024`
- Engine result found: `true`
- Engine FAIL count: `1`
- Final route: `TOOL_RAG`
- HTTP status: `200`

Esta ejecución demuestra de forma integrada que el LLM interpreta la intención, el Validation Engine conserva la autoridad sobre los resultados determinísticos, RAG aporta grounding documental, el Auditor participa antes de la salida y el Agent orquesta la respuesta final.

La evidencia técnica completa fue exportada desde Cloud Logging como:

`TRACE-4f596f6a_TOOL_RAG_SUCCESS.json`

### 7.4 Resiliencia observada

Antes de habilitar el saldo prepago requerido por Gemini API, una ejecución real recibió HTTP 402 (`RESOURCE_EXHAUSTED / prepayment credits depleted`).

La aplicación no modificó resultados ni fabricó una respuesta. El sistema:

- identificó el fallo del proveedor,
- preservó el resultado determinístico del Validation Engine,
- degradó la ruta de forma segura,
- activó el safe fallback,
- devolvió HTTP 200 a la aplicación sin provocar un crash.

Este comportamiento constituye evidencia adicional de los guardrails y del diseño fail-safe del PoC.

### 7.5 Estado final

El PoC queda demostrado en dos niveles complementarios:

1. **Capa determinística y controles:** validada mediante pruebas offline, evaluación determinística, pruebas de integración e inyección de fallas.
2. **Integración real en cloud:** demostrada mediante deployment funcional en Google Cloud Run y una ejecución end-to-end exitosa con Gemini + Validation Engine + RAG + Auditor + Agent.

La evaluación estratificada histórica permanece correctamente clasificada como **INCONCLUSIVE** y no se utiliza para afirmar una tasa global de calidad de Gemini.

La prueba end-to-end posterior demuestra funcionamiento integrado del sistema, pero no sustituye una evaluación estadística completa de los 56 casos con Gemini real.

