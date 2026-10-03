# CP3 Review Package — Agent & Orchestration

**Proyecto:** AI Payroll Operations & Validation Agent (PoC académico, solo datos sintéticos)
**Checkpoint:** CP3 — Pasos 1–9 del plan aprobado (Fases 6, 7 y 8)
**Preparado por:** Klaudio para Pam (revisión: Zury)
**Fecha:** 3 de octubre de 2026
**Estado:** Implementación completa — **evaluación con Gemini real pendiente** — esperando aprobación. No se inició nada de CP4.

---

## Resumen

| Indicador | Resultado |
|---|---|
| Suite completa sin red | **373 aprobados / 0 fallidos** (86 CP1 + 74 CP2 + 213 CP3), verificada desde un clon limpio con entorno nuevo |
| Regresión CP1 + CP2 | 160 / 160 siguen pasando |
| Rutas | Las 5 (`RAG`, `TOOL`, `TOOL_RAG`, `CLARIFY`, `OUT_OF_SCOPE`), en inglés y español |
| Arnés de evaluación (proveedores fake) | Las 5 metas cumplidas en 56 casos EN/ES |
| Auditor con respuestas sembradas | 16/16 detectadas, 0 falsos positivos en 3 respuestas correctas de control |
| **Evaluación con Gemini real** | **No ejecutada:** este entorno no tiene `GEMINI_API_KEY`. Los comandos están en la sección 9 |
| Dependencias nuevas | Ninguna (no se agregó nada a `requirements.txt`) |
| FastAPI, Streamlit, logging a archivo, Docker, GCP | No implementados (CP4/CP5) |

**Lo más importante que deben saber:**

1. **La evaluación real con Gemini queda en sus manos.** Los resultados del arnés con proveedores fake **no miden a Gemini**: el fake usa las mismas reglas de palabras clave que el fallback determinista, así que su 100 % mide la capa determinista, no la calidad del LLM. La aprobación de CP3 debería depender de los resultados de la sección 9.
2. **El modelo de texto de Gemini no está fijado en el código** (C3-08). Hay que definir `GEMINI_MODEL` en `.env` con el modelo que confirmen en su cuenta.
3. Encontré una debilidad en el diseño de CP1 y la mitigué en la herramienta; necesita una decisión (N13, sección 11).

---

## 1. Qué se construyó, paso por paso

| Paso | Componente | Archivos |
|---|---|---|
| 1 | `LLMClient` + Gemini + Fake | `app/llm/client.py`, `gemini_client.py`, `fake_client.py` |
| 2 | Validation Tool (solo lectura) | `app/validation/tool.py` |
| 3 | Idioma, entidades, sesión, intención, router | `app/agent/language.py`, `keywords.py`, `entities.py`, `session.py`, `intent.py`, `router.py`, `contracts.py` |
| 4 | Plantillas bilingües | `app/agent/responses.py` |
| 5 | Auditor | `app/audit/checks.py`, `auditor.py` |
| 6 | Explainer + prompts versionados | `app/agent/explainer.py`, `app/agent/prompts/*_v1.md` |
| 7 | Orquestador, guardia del índice, fábrica, consola | `app/agent/orchestrator.py`, `knowledge_guard.py`, `factory.py`, `fake_handlers.py`, `scripts/ask_agent.py` |
| 8 | Tests y evaluación | 11 archivos de tests, `routing_cases.yaml`, `seeded_responses.yaml`, `scripts/evaluate_agent.py` |
| 9 | Evidencia | Este documento |

**Modificados:** `app/core/config.py` (variables CP3), `app/rag/retriever.py` (umbral Gemini 0.638, N5), `app/validation/batch.py` (función de huella reutilizable, sin cambio de comportamiento), `.env.example`, `README.md`, `tests/conftest.py`.

**Sin cambios:** el Validation Engine, las reglas, el dataset y los documentos de conocimiento.

---

## 2. Cómo funciona una pregunta

```
"¿Por qué falló EMP027?"
  │
  1. Entender   idioma = es (determinista) · entidades: EMP027, periodo 2026-09 (única corrida)
  │             intención (LLM): validation_explanation
  2. Decidir    matriz determinista → TOOL_RAG
  3. Obtener    Validation Tool: corrida verificada por huella → 3 resultados de EMP027
  │             Retriever: índice vigente → chunks con query en inglés construida por código
  4. Responder  hechos por plantilla (sin LLM) + explicación del LLM con citas
                Auditor → ALLOW · aviso human-in-the-loop · trace_id
```

Respuesta real del Agent (proveedores fake):

```
EMP027 — periodo 2026-09 (corrida RUN-2026-09-…):
- gross_pay: FAIL — esperado no disponible, proveedor 7331.29 SYN (MISSING_INPUT: Expected value not calculated: overtime_pay value is missing)
- total_deductions: PASS — esperado 1223.61 SYN, proveedor 1223.61 SYN, diferencia 0.00 SYN, tolerancia 5.00 SYN (WITHIN_TOLERANCE)
- net_pay: FAIL — esperado no disponible, proveedor 6107.68 SYN (MISSING_INPUT: … upstream gross_pay not calculable …)

Por qué: EMP027: gross_pay tiene estado FAIL con código de motivo MISSING_INPUT. … [RULE-001-C05] …

[Las decisiones sobre excepciones y la aprobación de la nómina corresponden a un revisor humano.]
route=TOOL_RAG · intent=validation_explanation · lang=es · mode=template+llm · audit=ALLOW · trace=TRACE-52aa5818
```

---

## 3. Cumplimiento de las decisiones aprobadas

| Decisión | Implementación | Test que lo demuestra |
|---|---|---|
| **N5** umbral Gemini 0.638 | `DEFAULT_MIN_SCORE["gemini"] = 0.638` | Configuración + evaluación real |
| **C3-01** Auditor en CP3 | `app/audit/` | `test_audit.py` (47 tests) |
| **C3-02** LLM clasifica, matriz decide | `router.py`; reglas previas al LLM | `test_routing_matrix` (16 celdas) |
| **C3-03** `TOOL` sin LLM generativo | Solo plantillas | `test_tool_route_lookup_is_template_only` verifica que no hubo llamadas de generación |
| **C3-04** hechos nunca del LLM | Plantilla + `validation.results` inmutable | `test_explanation_failing_twice_is_blocked_and_facts_are_preserved` |
| **C3-05** periodo por corrida única | `_resolve_entities` | `test_period_resolved_from_single_run`, `test_multiple_runs_require_period` |
| **C3-06** un empleado por pregunta | `CLARIFY multiple_employees` | `test_multiple_employees_clarifies` |
| **C3-07** índice viejo en `TOOL_RAG` | Hechos sí, documentos no | `test_stale_index_in_tool_rag_keeps_engine_facts` |
| **C3-08** modelo configurable, temp 0, JSON | `GeminiLLMClient`; sin modelo por defecto | `test_gemini_requires_explicit_model`, `test_gemini_structured_request_…` |
| **C3-09** herramienta solo lectura | Nunca ejecuta el Engine | `test_tool_never_runs_the_engine`, `test_tampered_run_file_is_refused` |
| **C3-10** check semántico apagado | `Auditor(semantic_llm=None)` por defecto | `test_semantic_check_is_off_by_default_and_optional` |
| **C3-11** prompts versionados | `intent_v1.md`, `rag_answer_v1.md`, `tool_rag_explain_v1.md` | Versión en `versions.prompts` de cada respuesta |
| **C3-12 B** inglés + español | Detección determinista, vocabularios y plantillas EN/ES | 56 casos de ruteo EN/ES, conversaciones de 4 turnos en ambos idiomas |
| **C3-13** readiness sin decisión | Hechos + SOP-003; frases prohibidas | `test_readiness_gives_facts_and_prerequisites_never_a_decision` |
| **C3-14** `trace_id` | `TRACE-xxxxxxxx` en cada respuesta | `test_every_response_has_trace_versions_and_allowed_audit` |
| **N9** bloqueo por índice viejo | `KnowledgeGuard` | `test_stale_index_blocks_rag` |

---

## 4. Soporte bilingüe (C3-12 B)

| Requisito | Cómo se cumple |
|---|---|
| Ruteo en ambos idiomas | El LLM recibe el mensaje tal cual; el prompt indica que puede venir en inglés o español |
| Fallback determinista bilingüe | `keywords.py`: vocabularios EN/ES normalizados sin acentos ("nómina" = "nomina", "por qué" = "porque") |
| Fake bilingüe | Usa las mismas reglas bilingües |
| Evaluación EN y ES | 28 casos en inglés y 28 en español, espejo uno a uno |
| Responder en el idioma del usuario | Detección determinista; un mensaje sin señales (p. ej. "EMP024") conserva el idioma de la sesión |
| Valores canónicos | `PASS`, `FAIL`, `net_pay`, `OUT_OF_TOLERANCE`, IDs y montos nunca se traducen |
| Conocimiento solo en inglés | Para buscar, el LLM reescribe la pregunta en inglés (N10) |

**Acciones prohibidas en español.** La regla determinista reconoce órdenes en imperativo ("Aprueba la nómina"), infinitivo tras una petición ("¿Puedes cerrar la excepción?") y subjuntivo ("Necesito que apruebes la nómina"). En cambio, "¿Puede el asistente aprobar la nómina?" es una pregunta de política y va a `RAG`.

---

## 5. El Auditor

**Checks deterministas** (todos bilingües):

| Check | Detecta | Veredicto si falla |
|---|---|---|
| `numeric_grounding` | Montos que no están en los hechos, los chunks o la pregunta | REVISE |
| `status_consistency` | "net_pay passed" / "el pago neto pasó" cuando el Engine dice FAIL (y al revés) | REVISE |
| `employee_consistency` | Empleados que no están en la pregunta ni en los hechos | REVISE |
| `prohibited_decision` | Aprobar, "lista para aprobarse", aceptar o cerrar excepciones, anular resultados | **BLOCK inmediato** |
| `citation_validity` | Citas de chunks que no se recuperaron | REVISE |
| `citation_required` | Respuesta documental sin ninguna cita | REVISE |
| `scope` | Países, leyes o instituciones reales (México, ISR, IMSS…) | REVISE |
| `no_arithmetic` | El LLM recalculando ("4082.48 − 3732.48 = …") | REVISE |

**Flujo (D9):** ALLOW → se entrega. REVISE → una reescritura con la retroalimentación del Auditor; si falla otra vez → BLOCK. BLOCK → respuesta segura: los hechos del Engine más la lista de documentos relevantes, sin la explicación.

Ejemplo real de BLOCK tras reescritura (el LLM inventó 305.00 y luego 300.00):

```
- net_pay: FAIL — expected 3732.48 SYN, provider 4082.48 SYN, difference +350.00 SYN, tolerance 10.00 SYN (OUT_OF_TOLERANCE)

The generated explanation did not pass the safety checks, so only verified information is shown.
Relevant documentation:
- [RULE-003-C03] Net Pay Validation Rule > Tolerance (knowledge/rules/net_pay_rule.md)
…
audit: BLOCK · revised: true · failed: numeric_grounding ['300.00']
```

**Las plantillas también pasan por el Auditor.** Un test verifica que todas salgan `ALLOW`. Esto ya detectó un defecto real durante la construcción: la plantilla de `CLARIFY` usaba "EMP024" como ejemplo, y el Auditor la marcó como empleado no consultado. Ahora dice "formato EMP###".

---

## 6. Session context / multi-turno

Conversación verificada en ambos idiomas:

| Turno | Mensaje | Ruta | Resolución |
|---|---|---|---|
| 1 | "Why did EMP024 fail?" | TOOL_RAG | EMP024 del mensaje; foco = net_pay (lo que falló) |
| 2 | "What was the difference?" | TOOL | EMP024 de la sesión; solo net_pay; +350.00 SYN |
| 3 | "And EMP026?" | TOOL | EMP026 reemplaza a EMP024; hereda el tipo de pregunta anterior (N12) |
| 4 | "How many exceptions in total?" | TOOL | Summary del Engine: 14 |

**Aclaración completada:** "Why did the employee fail?" → `CLARIFY`; luego "EMP024" → `TOOL_RAG` sin volver a preguntar (`route_source = pending_clarification`). Si el siguiente mensaje es otra pregunta, la pendiente se descarta.

Las sesiones expiran a los 30 minutos sin actividad, guardan 10 turnos como máximo, están aisladas entre sí y al LLM solo le llega el estado estructurado.

---

## 7. Manejo de errores y fallbacks (verificados con tests)

| Falla simulada | Resultado |
|---|---|
| El LLM falla al clasificar | Fallback por palabras clave, `route_source = fallback`, misma ruta |
| El LLM falla al explicar | Hechos + documentos relevantes, `answer_mode = template` |
| El LLM falla en `RAG` | Lista de fuentes citadas, `safe_fallback` |
| Índice desactualizado | `RAG` bloqueado; `TOOL_RAG` entrega solo los hechos |
| Índice inexistente | `evidence_status = unavailable`; no se llama al LLM |
| No hay corrida para el periodo | Plantilla con instrucción de correr el batch |
| **Archivo de corrida alterado** | La herramienta recalcula la huella, rechaza el archivo y no muestra resultados |
| Excepción inesperada | Mensaje seguro con `trace_id`; nunca un stack trace |

---

## 8. Resultados de pruebas sin red

```
python -m pytest -q
373 passed, 9 deselected
```

Los 9 "deselected" son las evaluaciones con Gemini real (`pytest -m eval`).

| Archivo nuevo (CP3) | Tests | Cubre |
|---|---|---|
| `test_agent_language_entities.py` | 62 | Idioma, entidades, acciones prohibidas (órdenes vs preguntas), intención por palabras clave EN/ES, glosario |
| `test_agent_router_session.py` | 22 | Cada celda de la matriz, TTL, aislamiento, límite de turnos, resumen para el LLM |
| `test_audit.py` | 47 | Cada check, veredictos, check semántico opcional, 16 respuestas sembradas, 3 de control |
| `test_llm_clients.py` | 12 | Fake (scripting, fallas, registro); Gemini simulado (schema, temp 0, timeout, reintento, modelo obligatorio) |
| `test_validation_tool.py` | 10 | Resultados idénticos a la corrida, filtros, summary, inexistente, alteración, inmutabilidad, nunca ejecuta el Engine |
| `test_agent_routes.py` | 38 | Las 5 rutas en EN/ES, incluidos todos los casos de `CLARIFY` y `OUT_OF_SCOPE` |
| `test_agent_multiturn.py` | 8 | Conversaciones de 4 turnos EN/ES, aclaraciones, aislamiento |
| `test_agent_safety.py` | 13 | Reescritura, BLOCK, protección de hechos, grounding numérico, todos los fallbacks |
| `test_agent_evaluation_harness.py` | 1 | El script de evaluación calcula todas las métricas |

**Arnés con proveedores fake** (`scripts/evaluate_agent.py --provider fake`):

| Métrica | Meta | Fake |
|---|---|---|
| Exactitud de ruteo | ≥ 90 % | 100 % (EN 100 %, ES 100 %) |
| CLARIFY por empleado faltante | 100 % | 100 % |
| OUT_OF_SCOPE | ≥ 90 % | 100 % |
| Consistencia Agent / Engine | 100 % | 100 % |
| Detección del Auditor (sembradas) | 100 % | 100 % (16/16, 0 falsos positivos) |
| ALLOW sin reescritura | Se reporta | 100 % de 21 respuestas generadas |
| Coincidencia de idioma | Se reporta | 100 % |

⚠️ **Estos números no miden a Gemini.** La consistencia Agent/Engine y la detección del Auditor sí son válidas tal cual, porque son deterministas. Las métricas de ruteo, ALLOW sin reescritura y latencia **solo son significativas con Gemini real**.

---

## 9. Evaluación con Gemini real — PENDIENTE

**Estado:** no ejecutada. No hay `GEMINI_API_KEY` en el entorno de construcción.

**Lo que se probó sin red:** el cliente Gemini envía `temperature=0`, salida JSON con el schema de pydantic, `system_instruction` y timeout; reintenta una vez; exige `GEMINI_MODEL`.

**Lo que no se ha probado contra la API real** (riesgos a observar):

| Riesgo | Señal en la evaluación |
|---|---|
| Nombre de modelo o compatibilidad del schema JSON | Error al primer comando |
| Gemini clasifica distinto al fallback | `routing_failures` en el reporte |
| Explicaciones de Gemini que el Auditor marca de más (por ejemplo, frases en español cercanas a "lista para aprobación") | `allow_without_rewrite_rate` bajo |
| Preguntas en español con puntaje bajo de retrieval | Rutas `RAG` en español con `insufficient` |
| Latencia | `latency_ms_by_route` |

**Pasos (desde la máquina de Pam, con `.env` que tenga `GEMINI_API_KEY` y `GEMINI_MODEL`):**

```bash
python scripts/run_validation.py --period 2026-09
python scripts/ingest_knowledge.py --provider gemini          # si el índice Gemini de CP2 no está
python scripts/ask_agent.py --provider gemini "Why did EMP024 fail?"      # prueba de humo
python scripts/evaluate_agent.py --provider gemini --out cp3_gemini_eval.json
python -m pytest -m eval -v                                   # 3 de retrieval + 6 del Agent
```

**Tabla para llenar con los resultados reales:**

| Métrica | Meta aprobada | Gemini |
|---|---|---|
| Exactitud de ruteo | ≥ 90 % | |
| — inglés / español | — | |
| CLARIFY por empleado faltante | = 100 % | |
| OUT_OF_SCOPE | ≥ 90 % | |
| Consistencia Agent / Engine | = 100 % | |
| Detección del Auditor (sembradas) | = 100 % | |
| ALLOW sin reescritura | Se reporta | |
| Latencia media / p95 por ruta | Se reporta | |
| Modelo confirmado (`GEMINI_MODEL`) | — | |

Si alguna meta no se cumple, el reporte JSON lista cada caso fallido con la intención que devolvió Gemini, para ajustar el prompt (`intent_v2.md`) sin tocar la matriz.

---

## 10. Desviaciones respecto al diseño aprobado

| # | Desviación | Por qué |
|---|---|---|
| 1 | La herramienta **calcula los conteos** a partir de los resultados verificados, en vez de leer el bloque `summary` del archivo | La huella de CP1 cubre los resultados, no el summary; un summary editado pasaría sin ser detectado (ver N13) |
| 2 | La consulta de retrieval en `TOOL_RAG` se escribe como **preguntas naturales en inglés** construidas por código | El umbral 0.638 se calibró con preguntas naturales; una cadena de palabras clave podría quedar por debajo |
| 3 | Seguimiento como "And EMP026?" **hereda el tipo de la pregunta anterior** (en el diseño el ejemplo decía `TOOL`) | Comportamiento uniforme: después de un "¿por qué?" sigue `TOOL_RAG`; después de un lookup, `TOOL` |
| 4 | El aviso human-in-the-loop va en un **campo separado**, no dentro de `answer` | La UI de CP4 decide cómo mostrarlo |
| 5 | La plantilla de `CLARIFY` usa "formato EMP###" en vez de un ID de ejemplo | Un ID real en la plantilla se confundía con un empleado consultado |
| 6 | Las plantillas también pasan por el Auditor | Detecta defectos de las propias plantillas (ya encontró el punto 5) |
| 7 | `fingerprint_result_dicts` agregado a `batch.py` | Reutilizar la misma huella al leer; sin cambio de comportamiento (los 86 tests de CP1 pasan) |

---

## 11. Decisiones nuevas que requieren aprobación

| # | Decisión | Recomendación |
|---|---|---|
| **N10** | **Consulta de retrieval en inglés para preguntas en español:** en la ruta `RAG`, el LLM devuelve junto con la intención la pregunta reescrita en inglés; solo se usa para buscar. Si el LLM falla, se busca con el mensaje original | Aprobar. El conocimiento está en inglés y el umbral se calibró con preguntas en inglés |
| **N11** | **Límites conocidos del Auditor:** (a) los enteros menores a 10 no se verifican ("2 validaciones"); (b) las oraciones de regla general ("una validación pasa cuando…") y las que mencionan PASS y FAIL a la vez no se juzgan por estado | Aceptar como limitación documentada. Los montos con decimales y todos los enteros ≥ 10 sí se verifican, y los hechos nunca dependen del LLM |
| **N12** | **Herencia de intención en seguimientos** que solo nombran otro empleado | Aprobar |
| **N13** | **Integridad del summary de CP1:** hoy la huella no cubre el bloque `summary`. La herramienta ya lo mitiga recalculando los conteos | (a) Aceptar la mitigación para el PoC, o (b) agregar el summary a la huella en un cambio menor de CP1 (requiere subir `engine_version`). Recomiendo **(a)** ahora y (b) como backlog |
| **N14** | **El `detail` del Engine queda en inglés** dentro de respuestas en español | Aprobar: es salida canónica del Engine, igual que los reason codes |
| **N15** | **Pregunta pendiente:** un mensaje corto (≤ 3 palabras además del dato) completa la pregunta pendiente | Aprobar |

---

## 12. Comandos para verificar CP3 localmente

```bash
cd ai-payroll-agent
python3.11 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. Suite completa sin red (373 tests)
python -m pytest -v

# 2. Datos
python scripts/run_validation.py --period 2026-09
python scripts/ingest_knowledge.py --provider fake

# 3. Conversación offline (vacío para salir)
python scripts/ask_agent.py --provider fake
#   Why did EMP024 fail?
#   What was the difference?
#   ¿Por qué falló EMP027?
#   Why did the employee fail?   →  EMP024
#   Approve the payroll
#   Is payroll ready for approval?

# 4. Arnés de evaluación offline
python scripts/evaluate_agent.py --provider fake

# 5. Evaluación REAL con Gemini (ver sección 9)
```

---

## Checklist del Definition of Done de CP3

| # | Criterio | Estado |
|---|---|---|
| 1 | 5 rutas soportadas | ✅ EN y ES |
| 2 | Ruta por matriz determinista; LLM solo clasifica | ✅ |
| 3 | Herramienta idéntica a la corrida persistida; nunca ejecuta ni recalcula | ✅ además verifica la huella |
| 4 | Números y estados solo por plantilla y `validation.results` | ✅ |
| 5 | `TOOL_RAG` combina hechos y evidencia citada; el Auditor rechaza alteraciones | ✅ |
| 6 | `CLARIFY` cuando falta empleado o periodo; pendiente completada | ✅ |
| 7 | `OUT_OF_SCOPE` para acciones prohibidas, temas ajenos y asesoría legal real | ✅ |
| 8 | Seguimiento multi-turno | ✅ conversación de 4 turnos EN y ES |
| 9 | Bloqueo por índice desactualizado (N9) | ✅ |
| 10 | Auditor ALLOW / REVISE / BLOCK, una reescritura, 100 % de sembradas | ✅ 16/16 |
| 11 | `LLMClient` Fake y Gemini; tests sin credenciales | ✅ |
| 12 | Fallas degradan a respuestas deterministas seguras | ✅ |
| 13 | Tests pasan, incluida la regresión CP1 + CP2 | ✅ 373/373 |
| 14 | **Evaluación con Gemini real ejecutada y reportada** | ⏳ **Pendiente** (sección 9) |
| 15 | Sin dependencias prohibidas, credenciales ni datos reales | ✅ |
| 16 | Sin FastAPI, Streamlit ni despliegue | ✅ |

**Detenido. Esperando la evaluación con Gemini real y la aprobación de CP3 y de N10–N15 antes de iniciar CP4.**
