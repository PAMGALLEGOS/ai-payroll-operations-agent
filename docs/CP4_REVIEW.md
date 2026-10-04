# CP4 Review Package — Demo end-to-end (API + interfaz web + observabilidad)

**Proyecto:** AI Payroll Operations & Validation Agent (PoC académico, solo datos sintéticos)
**Checkpoint:** CP4 — Fases 9, 10 y 11 de la spec
**Preparado por:** Klaudio para Pam (revisión: Zury)
**Fecha:** 3 de octubre de 2026
**Estado:** Implementación completa — **esperando QA de Pam/Zury**. No se inició nada de CP5.

---

## Resumen

| Indicador | Resultado |
|---|---|
| Suite completa sin red | **443 aprobados / 0 fallidos** (373 de CP1–CP3 + 70 de CP4), verificada desde un clon limpio con entorno nuevo |
| Regresión CP1–CP3 | 373 / 373 |
| Demo en vivo (proveedores fake) | `run_demo.py --prepare` crea la corrida y el índice, levanta API y UI; `/health` = ok; UI responde 200; chat y métricas funcionan |
| Endpoints | Los 4 de la spec, con contratos en `/docs` |
| Interfaz | Dashboard + Chat, español por defecto con selector EN/ES (D4-10), probada headless con `streamlit.testing` |
| Observabilidad | Un evento JSON por paso con un solo `trace_id`, sin contenido del usuario, prompts ni respuestas (D4-09) |
| Decisiones D4-01 a D4-13 | Implementadas |
| **Pendiente de su lado** | Demo con Gemini real (`run_demo.py`) y capturas de pantalla: este entorno no tiene credenciales ni navegador |

---

## 1. Cómo correr el demo

```bash
# Offline, sin credenciales (respaldo para la presentación)
python scripts/run_demo.py --provider fake --prepare

# Con Gemini real (.env con GEMINI_API_KEY, GEMINI_MODEL=gemini-3.8-flash,
# GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001)
python scripts/run_demo.py --prepare
```

- API: http://127.0.0.1:8000 · contratos interactivos en http://127.0.0.1:8000/docs
- Interfaz: http://localhost:8501 (se abre sola)
- Ctrl+C detiene ambos procesos.

`--prepare` crea, solo si faltan, la corrida de validación (`run_validation.py`) y el índice del proveedor elegido (`ingest_knowledge.py`). Lo hace el script de arranque, nunca el Agent ni la API (C3-09, D4-12). Sin `--prepare`, el script dice exactamente qué falta y no arranca.

### Guion sugerido (cubre el Definition of Done de la spec)

| # | En la interfaz | Lo que debe verse |
|---|---|---|
| 1–2 | Abrir → Dashboard | 90 validaciones · 76 PASS · 14 FAIL · 14 excepciones · 8 empleados; tabla y gráfica por reason code; filtrar por `FAIL` |
| 3 | "¿Quién aprueba la nómina?" | Ruta `RAG`, fuentes de SOP-003 |
| 4 | "¿EMP001 pasó la validación?" | Ruta `TOOL`, tabla del Engine, sin LLM |
| 5 | "¿Por qué falló EMP024?" | `TOOL_RAG`: hechos + explicación citada + aviso human-in-the-loop |
| 6 | "¿Cuál fue la diferencia?" | +350.00 SYN de EMP024, resuelto por la sesión |
| 7 | "Nueva conversación" → "¿Por qué falló el empleado?" | `CLARIFY` |
| 8 | "Aprueba la nómina" | `OUT_OF_SCOPE` |
| 9 | (técnico) | `tests/integration/test_e2e_definition_of_done.py` muestra el BLOCK; en vivo no se puede forzar un error de Gemini |
| 10 | Copiar el `trace_id` de "Detalles técnicos" → buscarlo en `logs/agent.jsonl` | La secuencia completa de eventos |
| — | `python scripts/metrics_report.py` | KPIs por ruta, latencias, veredictos |

Todas las preguntas del guion están como botones en la barra lateral, en ambos idiomas.

---

## 2. Archivos creados y modificados

### Nuevos

| Grupo | Archivos |
|---|---|
| API | `app/api/main.py`, `schemas.py`, `state.py`, `dependencies.py`, `errors.py`, `routes/chat.py`, `routes/validation.py`, `routes/documents.py`, `routes/health.py` |
| Interfaz | `app/web/streamlit_app.py`, `api_client.py`, `views.py`, `i18n.py`, `.streamlit/config.toml` |
| Observabilidad | `app/observability/context.py`, `events.py`, `logger.py`, `llm.py` |
| Scripts | `scripts/run_demo.py`, `scripts/metrics_report.py` |
| Tests | `tests/api/` (39), `tests/web/` (19), `tests/observability/` (11), `tests/integration/test_e2e_definition_of_done.py` (1) |

### Modificados

| Archivo | Cambio | Decisión |
|---|---|---|
| `app/agent/orchestrator.py` | Llamadas `observer.emit(...)`; reutiliza el `trace_id` de la petición HTTP; `replace_retriever()` con lock. **Sin cambios de lógica:** los 373 tests previos pasan y un test compara respuestas con y sin observador | D4-08, D4-07 |
| `app/agent/factory.py` | Parámetro `observer`; `load_knowledge()` reutilizable para la ingesta | D4-07, D4-08 |
| `app/rag/retriever.py` | Compara nombres de modelo sin el prefijo `models/` | D4-02 |
| `app/core/config.py`, `.env.example` | `models/gemini-embedding-001`; modelo de texto confirmado como comentario; `API_BASE_URL`, `LOG_FILE`, `LOG_LEVEL`, `INGEST_TOKEN` | D4-02, D4-03, D4-06 |
| `tests/unit/test_embeddings.py` | El valor por defecto esperado ahora es `models/gemini-embedding-001` | D4-02 |
| `tests/conftest.py` | Fixtures de la API compartidos | — |
| `requirements.txt` | `fastapi`, `uvicorn`, `streamlit`, `httpx` con versión fijada | D4-13 |
| `pyproject.toml` | Filtro de un aviso de deprecación de Starlette en tests | — |
| `README.md` | Inicio rápido del demo | — |

**Sin cambios:** Engine, reglas, dataset, documentos, chunking, embeddings, router, palabras clave, plantillas, Auditor y prompts.

---

## 3. API (spec §14)

| Endpoint | Comportamiento verificado |
|---|---|
| `POST /chat` | Las 5 rutas en EN/ES; `session_id` generado si falta y reutilizable (D4-04); respuesta idéntica a la del Agent directo; header `X-Trace-Id` igual al `trace_id` de la respuesta |
| `GET /validation` | Idéntico a la Validation Tool; filtros por periodo, empleado, tipo y estado; **cero llamadas al LLM**; periodo inexistente → 404; corrida alterada → 503 sin resultados; varias corridas sin periodo → 400 |
| `POST /documents/ingest` | Reindexa `knowledge/`; con índice viejo, el Agent pasa a `ok` **sin reiniciar** y conserva las conversaciones (D4-07); rechaza archivos subidos (D15); token obligatorio si está configurado (D4-06); dos ingestas simultáneas → 409 |
| `GET /health` | Estado por componente; `degraded` con índice viejo o sin corrida; **nunca expone secretos**; si el Agent no se pudo construir (por ejemplo, sin API key), la API arranca igual, `/health` explica el motivo, `/chat` responde 503 y el dashboard sigue funcionando |

**Errores:** siempre `{"error", "message", "trace_id"}`. Las entradas inválidas responden 422 sin repetir el texto enviado. Una excepción inesperada responde 500 genérico: un test inyecta un error con una "contraseña" en el mensaje y verifica que no aparece en la respuesta.

Ejemplo real:

```
POST /chat {"message": "¿Por qué falló EMP027?"}
→ 200 · route=TOOL_RAG · language=es · audit=ALLOW · trace_id=TRACE-98faf884 · X-Trace-Id: TRACE-98faf884
```

---

## 4. Interfaz web (spec §13)

**Navegación:** selector en la barra lateral (Dashboard / Chat), idioma, estado del sistema, preguntas de ejemplo, "Mostrar detalles técnicos" y "Nueva conversación".

**Validation Dashboard:**
- Aviso visible: los datos vienen del Engine y el tablero no usa el LLM.
- Metadatos de la corrida: `run_id`, fecha, versiones y huella.
- Filtros por empleado, tipo y estado. Cada filtro consulta `GET /validation`, así que **los conteos los calcula el servidor**, no la interfaz.
- Cinco indicadores, la tabla de resultados del Engine (montos tal cual, `—` cuando no hay valor) y una gráfica de excepciones por reason code.

**Chat:**
- Etiqueta de ruta con color.
- La respuesta del Agent.
- **La tabla de resultados del Engine, tomada de `validation.results`, no del texto.**
- Fuentes documentales (chunk, documento, sección, similitud).
- Aviso human-in-the-loop.
- Detalles técnicos plegables: ruta, intención, idioma, modo, evidencia, veredicto del Auditor, checks fallidos, `trace_id`, latencia y versiones.

**Si la API está caída**, la interfaz muestra "No se pudo conectar con la API. Inicia el demo con `python scripts/run_demo.py`", sin errores de Python.

**Pruebas sin navegador** (`streamlit.testing`, la interfaz real contra la API real en el mismo proceso): métricas en español por defecto; el filtro FAIL muestra 14 y 0 PASS; el cambio a inglés funciona; el chat muestra respuesta, tabla y fuentes; un botón de ejemplo lleva al chat y responde; el seguimiento conserva la sesión; la interfaz sobrevive con la API caída.

---

## 5. Observabilidad (spec §15)

Secuencia real de una pregunta `TOOL_RAG`, todas las líneas con el mismo `trace_id`:

```
request_received → llm_called(intent) → intent_identified → tool_called → engine_result
→ rag_retrieved → llm_called(tool_rag_explain) → auditor_result → route_decided
→ response_completed → api_request
```

| Control | Verificado por test |
|---|---|
| Un solo `trace_id` por interacción, compartido entre la API y el Agent | `test_event_sequence_per_route`, e2e |
| Secuencia correcta por ruta (RAG, TOOL, TOOL_RAG, OUT_OF_SCOPE) | 4 casos |
| `TOOL`, `CLARIFY` y `OUT_OF_SCOPE` no generan llamadas de generación al LLM | `test_generation_llm_not_called_for_template_routes` |
| Fallback de intención y reescritura del Auditor visibles en los eventos | `test_fallback_and_rewrite_are_visible` |
| Observar no cambia las respuestas | `test_observers_never_change_answers` |
| **El log no contiene** el texto del usuario, las respuestas ni los prompts; sí longitud, idioma y hash | `test_log_file_has_json_lines_and_no_content` |
| KPIs correctos sobre un log real | `test_metrics_report_from_real_log` |

**Reporte de KPIs** (`scripts/metrics_report.py`): interacciones por ruta, latencia p50/p95/máx por ruta, modos de respuesta, veredictos finales del Auditor y tasa de reescritura, llamadas y errores de la herramienta, resultados del retrieval, llamadas al LLM por tarea (éxito y duración), fallbacks, errores contenidos y peticiones HTTP.

---

## 6. Criterios de aceptación

### Definition of Done de la spec

| # | Escenario | Estado | Evidencia |
|---|---|---|---|
| 1 | Abrir la aplicación web | ✅ | Demo en vivo (UI 200) + `test_streamlit_app.py` |
| 2 | Ver resultados de validación | ✅ | Dashboard + e2e |
| 3 | Pregunta de procedimiento con RAG | ✅ | e2e + tests de chat |
| 4 | Resultado determinista de un empleado | ✅ | e2e: resultados idénticos a `/validation` |
| 5 | Por qué falló (Engine + RAG) | ✅ | e2e |
| 6 | Seguimiento multi-turno | ✅ | e2e + API + interfaz |
| 7 | Pregunta ambigua → aclaración | ✅ | e2e |
| 8 | Fuera de alcance | ✅ | e2e |
| 9 | Respuesta contradictoria detectada | ✅ | e2e: BLOCK y hechos preservados |
| 10 | Seguir una interacción por `trace_id` | ✅ | e2e + log real |
| 11 | Correr las pruebas | ✅ | 443/443 |
| 12 | Correr la aplicación en local | ✅ fake · ⏳ Gemini | `run_demo.py` en vivo con fake; con Gemini, de su lado |
| 13 | Despliegue / readiness GCP | — | CP5 |

### Criterios técnicos del plan

| Criterio | Estado |
|---|---|
| 4 endpoints con contratos en `/docs` | ✅ |
| `/validation` idéntico a la herramienta y sin LLM | ✅ |
| `/chat` igual al Agent | ✅ |
| Ingesta en caliente; 401 sin token cuando está configurado | ✅ |
| Errores sin trazas internas, todos con `trace_id` | ✅ |
| Dashboard sin LLM; números iguales a `/validation` | ✅ |
| Tablas del chat desde `validation.results` | ✅ |
| Interfaz estable con la API caída | ✅ |
| Secuencia de eventos con un `trace_id` | ✅ |
| Sin contenido en los logs | ✅ |
| KPIs desde los logs | ✅ |
| Regresión CP1–CP3 | ✅ 373/373 |
| Sin dependencias prohibidas, credenciales, Docker ni GCP | ✅ |

---

## 7. Desviaciones respecto al plan

| # | Desviación | Por qué |
|---|---|---|
| 1 | Navegación con un selector en la barra lateral, no con pestañas | Streamlit no permite cambiar de pestaña por código; con el selector, un botón de ejemplo lleva directo al chat |
| 2 | El filtro por reason code se reemplazó por la gráfica de reason codes | `GET /validation` no tiene ese filtro, y agregarlo ampliaría la API de la spec. Los filtros que sí existen (empleado, tipo, estado) consultan al servidor |
| 3 | `GET /health` responde siempre HTTP 200, con `status: degraded` cuando algo falta | Es la verificación de vida para el demo. Ver N16 para CP5 |
| 4 | Si el Agent no se puede construir, la API arranca de todos modos | El dashboard y `/health` siguen disponibles y explican el problema, en vez de que el proceso termine |
| 5 | Las llamadas al LLM se registran con un envoltorio (`ObservedLLMClient`) creado en la fábrica | No hubo que tocar los clientes de Gemini ni el fake |
| 6 | `.streamlit/config.toml` desactiva el envío de estadísticas de uso de Streamlit | Privacidad del demo |
| 7 | Capturas de pantalla no incluidas | Este entorno no tiene navegador ni puede descargar uno. La interfaz se verificó con `streamlit.testing` y el demo en vivo respondió HTTP 200 |

---

## 8. Decisiones nuevas que requieren aprobación

| # | Decisión | Recomendación |
|---|---|---|
| **N16** | **`/health` en Cloud Run:** hoy siempre responde 200. Para CP5 puede convenir una verificación de readiness que responda 503 cuando el estado sea `degraded` | Mantener 200 en CP4 y decidir en CP5 junto con la configuración de Cloud Run |
| **N17** | **Historial del chat en la interfaz:** vive en la sesión del navegador; al recargar la página se pierde la vista, aunque el servidor conserva el contexto 30 minutos. "Nueva conversación" empieza de cero | Aceptar para el PoC (spec §11: sin memoria de largo plazo) |
| **N18** | **Logs de acceso de uvicorn:** salen en texto plano por stdout junto a los eventos JSON. El evento `api_request` ya cubre esa información, y `metrics_report.py` ignora las líneas que no son JSON | Aceptar en local; en CP5, arrancar uvicorn con `--no-access-log` para que Cloud Logging reciba solo JSON |

---

## 9. Lo que necesitamos de Pam / Zury para el QA

1. **Demo con Gemini real:** `python scripts/run_demo.py --prepare` (con el índice Gemini de CP2 o creándolo), recorrer el guion de la sección 1 en español y en inglés, y revisar el `trace_id` de una respuesta en `logs/agent.jsonl`.
2. **Capturas de pantalla** del dashboard y del chat para el paquete final de CP5.
3. Correr `python -m pytest -q` (443) y `python -m pytest -m eval -v` (9) en su máquina.
4. Decidir N16–N18.

**Detenido. Esperando QA de CP4 antes de iniciar CP5.**
