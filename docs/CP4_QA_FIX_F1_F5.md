# CP4 QA — Correcciones F1–F5 y aviso visible de fallback

**Hallazgo de origen:** las respuestas generativas con Gemini terminaban en fallback (`route_source=fallback`, `answer_mode=safe_fallback` / `template`) y ni el log ni la evaluación lo mostraban.
**Preparado por:** Klaudio · **Fecha:** 3 de octubre de 2026
**Autorización:** F1–F5 aprobadas y aviso visible aprobado. **F6 NO implementada.** **CP5 NO autorizado.**
**Commit:** `6b12fb1`

---

## 1. Resumen

| # | Qué cambió | Resultado |
|---|---|---|
| F1 | El evento `llm_called` ahora incluye el **motivo** del error: tipo de error y mensaje, con un máximo de 300 caracteres y **la API key enmascarada** | Cuando Gemini falla, el log dice por qué (por ejemplo, `404 NOT_FOUND …`) |
| F2 | Nuevo evento `llm_fallback` con la tarea que falló (`intent`, `rag_answer`, `tool_rag_explain`). La respuesta incluye `versions.llm_degraded` con esas tareas | Se ve qué paso usó el respaldo determinista. **El comportamiento no cambió**: solo se emite (D4-08) |
| F3 | La evaluación se corrigió: (a) `ALLOW sin reescritura` cuenta **solo** textos que generó el LLM; (b) dos metas nuevas al 100 %: `intent_llm_rate` y `generation_success_rate`; (c) se reporta `llm_fallbacks` por tarea | El respaldo determinista **ya no puede** aprobar la evaluación por sí solo |
| F4 | Test canario con Gemini real: `generate_text` y `generate_json(IntentOutput)` directos, **sin respaldo** | Si Gemini falla, el test falla mostrando el error |
| F5 | `scripts/diagnose_llm.py`: verifica la configuración, lista los modelos de la key y prueba las llamadas. Es de solo lectura y nunca imprime la key | Con su salida propongo F6 |
| Aviso | En el chat aparece `⚠️ LLM no disponible: se muestra información verificada (respuesta determinista).` (EN: *LLM unavailable: showing verified information (deterministic answer).*) | La degradación se ve sin abrir "Detalles técnicos" |

**No se tocaron:** Engine, reglas, documentos de conocimiento, umbrales de recuperación, contratos de ruteo, contratos del Auditor, comportamiento aprobado de CP1–CP3, ni la configuración de `GeminiLLMClient` (`_config`, modelo) — eso es F6.

---

## 2. Detalle por corrección

### F1 — Motivo del error, enmascarado
- Nuevo módulo `app/observability/redact.py`. Enmascara:
  - la key conocida;
  - cualquier texto con forma de key de Google (`AIza…`);
  - parámetros `key=`, `api_key=` y `token=`.

  Además compacta los espacios y trunca el resultado.
- `ObservedLLMClient` agrega el campo `error` al evento `llm_called` cuando la llamada falla. El campo tiene un máximo de 300 caracteres.
- `GeminiLLMClient` ahora arma el mensaje del error con la **clase** del error del SDK y su texto, y enmascara la key. El mensaje tiene un máximo de 2000 caracteres para que el diagnóstico vea el error completo; el log lo vuelve a recortar a 300.

Ejemplo de evento:
```json
{"event": "llm_called", "task": "intent", "ok": false, "error_type": "LLMError",
 "error": "Gemini task 'intent' failed after 2 attempts: ClientError: 404 NOT_FOUND … key=***"}
```

### F2 — Evento `llm_fallback`
| Dónde | Cuándo se emite |
|---|---|
| Clasificación de intención | El LLM falló y decidió el router de palabras clave |
| `_generate_audited` (RAG / TOOL_RAG) | La generación o la reescritura falló y se usó la plantilla |

Las secuencias de eventos aprobadas en CP4 **no cambian** cuando el LLM funciona: el evento solo aparece si hay fallback (los tests de observabilidad existentes pasan sin cambios).

`scripts/metrics_report.py` ahora muestra `LLM fallbacks by task` y los motivos de error del LLM agrupados.

### F3 — Evaluación corregida

| Métrica | Definición | Meta |
|---|---|---|
| `intent_llm_rate` | Respuestas cuya intención clasificó el LLM ÷ respuestas en las que se consultó al LLM. Se excluyen las rutas decididas por regla y las aclaraciones retomadas, porque ahí el LLM no participa | **100 %** |
| `generation_success_rate` | Respuestas RAG / TOOL_RAG con evidencia suficiente en las que el LLM generó el texto ÷ todas esas respuestas | **100 %** |
| `allow_without_rewrite_rate` | Solo textos generados por el LLM. **Ya no cuenta** las respuestas de respaldo | Se reporta |
| `llm_fallbacks` | Conteo por tarea | Se reporta |

Nota de diseño: un **BLOCK del Auditor** también termina en `safe_fallback`, pero ahí el LLM sí respondió. Por eso cuenta como generación exitosa (el que falló fue el contenido, no el LLM) y entra en el denominador de `ALLOW sin reescritura`.

Con proveedores fake, las 7 metas se cumplen al 100 % (ALLOW sin reescritura: 21 de 21 respuestas generadas).

### F4 — Canario
`tests/evaluation/test_gemini_canary.py` (marcador `eval`) hace dos pruebas:
- `test_gemini_canary_text`: el mismo camino que `rag_answer` / `tool_rag_explain`.
- `test_gemini_canary_json`: el prompt real de intención, el payload real y el schema `IntentOutput`; espera `policy_question` para "Who approves the payroll?".

También se agregó `test_spanish_rag_uses_english_retrieval_query` (`eval`): con Gemini funcionando, `¿Quién aprueba la nómina?` debe buscar con la reescritura en inglés (N10).

### F5 — Diagnóstico
`python scripts/diagnose_llm.py` (o `--json`). Hace estos chequeos, en orden:

| Chequeo | Qué prueba |
|---|---|
| `configuration` | Muestra `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` y el timeout, y si la key está presente (**nunca su valor**) |
| `models` / `model_available` | Lista los modelos con `generateContent` para esa key e indica si `GEMINI_MODEL` está en la lista |
| `embeddings` | Hace un embedding de prueba (confirma key y red) |
| `raw_minimal` | Llama a `generate_content` **sin configuración**: aísla el modelo de nuestros parámetros |
| `text` | `GeminiLLMClient.generate_text` con la configuración de producción |
| `intent_json` | `generate_json(IntentOutput)` con el prompt real de intención |

Si la respuesta llega vacía, muestra `finish_reason` y los tipos de partes (por ejemplo, solo `thought`). Termina con código de salida 0 si todo pasa y 1 si algo falla.

**Cómo leer el resultado** (esto define F6):

| Patrón | Causa probable | F6 probable |
|---|---|---|
| `model_available` FAIL y/o `raw_minimal` falla con 404 | El modelo no está disponible para la key | Cambiar `GEMINI_MODEL` en `.env` (sin código) |
| `raw_minimal` falla con 403 / 429 | Permisos o cuota | Habilitación o cuota en Google (sin código) |
| `raw_minimal` OK, `text` falla con 400 | Un parámetro de `_config` es rechazado | Ajuste puntual en `GeminiLLMClient._config` |
| `text` OK, `intent_json` falla | Structured output / schema | Ajuste del schema o del modo JSON |
| Respuesta vacía con partes `thought` | La respuesta no trae parte de texto | Leer las partes de texto de la respuesta |

### Aviso visible en la interfaz
- La función pura `views.llm_degraded(response)` devuelve verdadero si se cumple alguna de estas condiciones:
  - `versions.llm_degraded` no está vacío;
  - `route_source == "fallback"`;
  - la respuesta es RAG o TOOL_RAG, con evidencia suficiente y `answer_mode = template`.
- **Ajuste respecto a lo aprobado:** `safe_fallback` por sí solo **no** muestra el aviso, porque también ocurre cuando el Auditor bloquea un texto que el LLM sí generó. Decir "LLM no disponible" en ese caso sería falso. El caso del hallazgo (`safe_fallback` por falla del LLM) **sí** muestra el aviso, porque trae `llm_degraded` y `route_source=fallback`. Si prefieren el criterio literal, es un cambio de una línea.

---

## 3. Regresión offline

```
python -m pytest -q
458 passed, 14 deselected
```

- Antes eran 443 tests; se agregaron 15.
- Los 14 *deselected* son las evaluaciones con Gemini real (`-m eval`): las 9 de antes, más 2 metas nuevas, el test N10 y los 2 canarios.
- Sin key, `pytest -m eval` da 14 *skipped*.

Tests nuevos:

| Test | Verifica |
|---|---|
| `test_redact_masks_keys_and_truncates` | Enmascarado y truncado |
| `test_llm_error_detail_is_logged_and_redacted` | `llm_called` trae el motivo; la key no aparece en ningún evento |
| `test_gemini_client_error_message_keeps_reason_and_masks_key` | El mensaje de `GeminiLLMClient` conserva el código (400/404) y enmascara la key |
| `test_fallback_events_are_emitted` | `llm_fallback` por tarea, `versions.llm_degraded` y degradación idéntica a la anterior |
| `test_no_fallback_event_when_llm_works` | Sin falla, no hay evento extra |
| `test_evaluation_flags_llm_failures` | Con un LLM que siempre falla: `intent_llm_rate` y `generation_success_rate` = 0 % y metas **no** cumplidas, mientras el ruteo sigue en 100 % (justo lo que ocultaba la falla) |
| `test_allow_without_rewrite_excludes_fallbacks` | Las respuestas de respaldo no cuentan como generadas |
| `test_generation_failure_alone_is_detected` | Intención OK pero generación caída: se detecta |
| `test_llm_degraded_helper` | Reglas del aviso, incluido que un BLOCK del Auditor no lo dispara |
| `test_chat_warns_when_llm_unavailable` / `test_chat_has_no_warning_when_llm_works` | Streamlit real (AppTest) |
| `tests/unit/test_diagnose_llm.py` (4) | Diagnóstico offline con fakes: todo OK; fallas reportadas sin la key; respuesta vacía explicada; key faltante |

---

## 4. Qué necesito de ustedes

Desde la carpeta del proyecto, con el `.env` del QA:

```bash
python scripts/diagnose_llm.py
```

Compártanme la salida completa. Ya viene enmascarada, pero revísenla antes de enviarla.

Opcional, pero útil:
```bash
python -m pytest -m eval tests/evaluation/test_gemini_canary.py -v
```

**No es necesario** repetir todavía `evaluate_agent.py --provider gemini`: con Gemini fallando, las metas nuevas van a marcar NO, que es lo esperado. La evaluación completa se repite **después de F6**.

---

## 5. Siguiente paso

1. Pam/Zury corren el diagnóstico y comparten la salida.
2. Klaudio propone la corrección exacta de F6 y **espera aprobación**.
3. Después de F6: se repite la evaluación con Gemini (7 metas, incluidas las nuevas) y se actualizan los resultados de CP3 y CP4.

**Detenido. F6 no implementada. CP5 no autorizado.**
