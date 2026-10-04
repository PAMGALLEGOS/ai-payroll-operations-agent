# CP4 QA — Correcciones F1–F7d y aviso visible de fallback

**Hallazgo de origen:** las respuestas generativas con Gemini terminaban en fallback (`route_source=fallback`, `answer_mode=safe_fallback` / `template`) y ni el log ni la evaluación lo mostraban.
**Preparado por:** Klaudio · **Fecha:** 3 de octubre de 2026
**Autorización:** F1–F5, aviso visible, F6b, F7a, F7c y F7d aprobados; estrategia de evidencia EV-1/EV-2 aprobada; los 56 casos con Gemini real se difieren a CP5 (EV-3). F7b pospuesta a CP5. F6a la aplicaron Pam/Zury en su `.env`. **CP5 NO autorizado** hasta la aprobación final del QA de CP4.
**Commits:** `6b12fb1` (F1–F5) · `cba5199` (F6b) · `350c8f8` (F7a) · `267bb9d` (F7c) · `c092e9d` (F7d)

---

## 1. Resumen

| # | Qué cambió | Resultado |
|---|---|---|
| F1 | El evento `llm_called` ahora incluye el **motivo** del error: tipo de error y mensaje, con un máximo de 300 caracteres y **la API key enmascarada** | Cuando Gemini falla, el log dice por qué (por ejemplo, `404 NOT_FOUND …`) |
| F2 | Nuevo evento `llm_fallback` con la tarea que falló (`intent`, `rag_answer`, `tool_rag_explain`). La respuesta incluye `versions.llm_degraded` con esas tareas | Se ve qué paso usó el respaldo determinista. **El comportamiento no cambió**: solo se emite (D4-08) |
| F3 | La evaluación se corrigió: (a) `ALLOW sin reescritura` cuenta **solo** textos que generó el LLM; (b) dos metas nuevas al 100 %: `intent_llm_rate` y `generation_success_rate`; (c) se reporta `llm_fallbacks` por tarea | El respaldo determinista **ya no puede** aprobar la evaluación por sí solo |
| F4 | Test canario con Gemini real: `generate_text` y `generate_json(IntentOutput)` directos, **sin respaldo** | Si Gemini falla, el test falla mostrando el error |
| F5 | `scripts/diagnose_llm.py`: verifica la configuración, lista los modelos de la key y prueba las llamadas. Es de solo lectura y nunca imprime la key | Con su salida propongo F6 |
| F6a | **Causa raíz confirmada:** el `.env` local tenía el nombre de la variable repetido dentro del valor (`GEMINI_MODEL=GEMINI_MODEL=gemini-3.8-flash`; lo mismo en `GEMINI_EMBEDDING_MODEL`). Pam/Zury lo corrigieron | El diagnóstico pasa: modelo disponible, embeddings con 768 dimensiones, `raw_minimal` OK, `text` OK |
| F6b | Validación al arrancar del formato del nombre del modelo, y diagnóstico con `repr` y el origen del valor | Un nombre mal escrito ya no se convierte en un fallback silencioso |
| Aviso | En el chat aparece `⚠️ LLM no disponible: se muestra información verificada (respuesta determinista).` (EN: *LLM unavailable: showing verified information (deterministic answer).*) | La degradación se ve sin abrir "Detalles técnicos" |

**No se tocaron:** Engine, reglas, documentos de conocimiento, umbrales de recuperación, contratos de ruteo, contratos del Auditor, comportamiento aprobado de CP1–CP3, `_config` de `GeminiLLMClient` (`temperature`, timeout, schema) ni los modelos elegidos.

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

### F6b — El nombre del modelo se valida al arrancar

| Archivo | Cambio |
|---|---|
| `app/core/model_names.py` (nuevo) | Exige el formato `^(models/)?[A-Za-z0-9][A-Za-z0-9._-]*$`. El mensaje muestra el valor con `repr`, el ejemplo correcto, y recuerda que una variable del sistema tiene prioridad sobre el `.env` |
| `app/llm/gemini_client.py` | Si `GEMINI_MODEL` no cumple el formato → `LLMConfigError` al construir el cliente |
| `app/rag/embeddings.py` | Si `GEMINI_EMBEDDING_MODEL` no cumple el formato → `EmbeddingsConfigError` |
| `scripts/diagnose_llm.py` | `configuration` muestra cada modelo con `repr` y su origen (variable del sistema o `.env`) y falla si el formato es inválido. Los errores 503 / 429 / timeout llevan una línea `hint` que dice que es un problema transitorio del proveedor, no de configuración |

**Qué pasa ahora con un nombre inválido** (lo verifiqué con el valor exacto del hallazgo):
- La API arranca igual que con cualquier error de configuración de CP4.
- `/health` muestra `agent: unavailable` con el mensaje claro y `llm: unavailable`.
- El chat no responde con plantillas como si todo estuviera bien.
- La key nunca aparece.

**Qué no cambia:**
- No se corrige nada en silencio (no se quitan espacios ni comillas).
- El modo `fake` y los tests offline siguen igual.
- **Las fallas reales del proveedor en tiempo de ejecución (503, 429, timeouts) mantienen el fallback determinista aprobado** y ahora son visibles (F1, F2 y el aviso).

**Sobre el 503 de `intent_json`:**
- Es una condición de disponibilidad del proveedor ("high demand"), no un defecto de configuración. No se cambió el modelo.
- El cliente ya hace un reintento inmediato. **No agregué espera ni reintentos adicionales**: no estaba aprobado y cambiaría la latencia. Si el 503 se repite en la evaluación, lo propongo como decisión aparte (por ejemplo, un reintento con espera de 1–2 s).

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
491 passed, 14 deselected
```

(Con F7c: **497 passed**; con F7d: **507 passed, 14 deselected**; ver las secciones 4b y 4c.)

F7a agregó 15 tests a los 476 de F6b:
- 12 en `tests/unit/test_eval_pacing.py`: sin pausa por defecto; máximo 5 solicitudes en cualquier ventana de 60 s con una pausa de 13 s; el reintento del cliente también espera; la variable de entorno; la clasificación de errores; la regla PASS / FAIL / INCONCLUSIVE.
- 3 de integración: un 429 da INCONCLUSIVE; un 400 da FAIL; un LLM que funciona da PASS.

Hay 18 tests más que en la entrega de F1–F5:
- 16 en `tests/unit/test_model_name_validation.py`: nombres válidos, con y sin el prefijo `models/`; ocho formatos inválidos (nombre repetido, espacios, comillas, comentario); embeddings; el factory falla en lugar de degradar; el modo fake no se afecta.
- 2 en el diagnóstico: nombre inválido con `repr` y origen; `hint` de error transitorio para un 503.

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

## 4. F7a — Evaluación con ritmo controlado (cuota de 5 solicitudes por minuto)

**Causa confirmada por Pam/Zury:** `quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, `quotaValue: 5`, modelo `gemini-3.8-flash`. Es un límite **por minuto** del free tier; no es una cuota diaria ni un defecto del Agent o de la configuración.

### Qué se implementó (solo el arnés de evaluación)

| Archivo | Cambio |
|---|---|
| `scripts/eval_pacing.py` (nuevo) | Un `Pacer` mantiene al menos N segundos entre el **inicio** de cada solicitud `generate_content` a Gemini. Se aplica envolviendo el cliente del SDK, así que **el reintento interno del cliente también respeta la pausa**. Hay un solo `Pacer` por proceso, compartido por todos los tests de evaluación. **Por defecto, 0: sin pausa** |
| `scripts/eval_pacing.py` | Clasifica los errores del proveedor en `quota_429`, `unavailable_503`, `timeout` u `other`, a partir del evento `llm_called` (F1) |
| `scripts/evaluate_agent.py` | Opción `--min-interval` (o variable `EVAL_LLM_MIN_INTERVAL_SECONDS`), campo `provider_errors` y `status` = **PASS / FAIL / INCONCLUSIVE**. Código de salida: 0, 1 o 2 |
| `tests/evaluation/test_agent_eval.py` | Usa la pausa. Con `EVAL_AGENT_REPORT=<json>` **reutiliza** el reporte de `evaluate_agent.py` en lugar de repetir las ≈ 75 solicitudes. Las metas que dependen del LLM, si fallan por cuota, se reportan como `SKIPPED: INCONCLUSIVE …` |
| `tests/evaluation/test_gemini_canary.py` | Usa la pausa. Un 429 / 503 / timeout se reporta como `INCONCLUSIVE`; un 400, 404 o error de schema **sigue fallando** |

Regla de `INCONCLUSIVE`:

| Situación | Estado |
|---|---|
| Se cumplen las 7 metas | **PASS** |
| No se cumple alguna meta que depende del LLM (ruteo, aclaraciones, fuera de alcance, `intent_llm_rate`, `generation_success_rate`) **y** hubo 429 / 503 / timeouts | **INCONCLUSIVE**: se repite la corrida |
| No se cumple una meta determinista (consistencia con el Engine, detección del Auditor) | **FAIL**, aunque haya errores de cuota |
| No se cumple alguna meta y el error no es transitorio (400, 404…) | **FAIL** |

Las metas no cumplidas **se siguen reportando como no cumplidas**; `INCONCLUSIVE` solo evita leerlas como un problema de calidad del Agent.

**No cambió:** el Agent, `GeminiLLMClient`, el fallback determinista, los modelos, la facturación ni CP5. F7b (no reintentar un 429 en producción) queda para CP5. **Ningún archivo de `app/` se modificó en F7a.**

### Cálculo del ritmo

| Concepto | Valor |
|---|---|
| Cuota | 5 solicitudes por minuto por modelo |
| Pausa | **13 s** (60 / 5 = 12, más 1 s de margen). Inicios en 0, 13, 26, 39 y 52 s: como máximo 5 en cualquier ventana de 60 s (verificado con un test) |
| Solicitudes de una evaluación completa | ≈ 75. Pueden ser algunas más si el Auditor pide una reescritura o el cliente reintenta; esas también esperan su turno |
| Duración | ≈ **17–20 minutos** |
| Embeddings | Son otro modelo, con otra cuota, y no se pausan. Si alguna vez dieran 429, sería una decisión aparte |

---

## 4b. F7c — Protección de cuota en el arnés (cuota diaria de 20 solicitudes)

**Causa confirmada por Pam/Zury:** `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`, modelo `gemini-3.8-flash`. El límite diario de 20 solicitudes es menor que las ≈ 75–85 que necesita una evaluación completa.

**Verificación de F7a** (reproducción con un Gemini simulado y reloj virtual): la pausa de 13 s cubre **todas** las solicitudes, incluidos el reintento del cliente y la reescritura del Auditor. Nunca hubo más de 5 solicitudes en 60 s. El SDK `google-genai` 2.28.0 no reintenta por su cuenta con nuestra configuración. Los embeddings usan otro modelo y otra cuota.

| Cambio (solo el arnés: `scripts/eval_pacing.py`, `scripts/evaluate_agent.py` y los tests de evaluación) | Efecto |
|---|---|
| **Verificación previa:** una sola solicitud pausada antes de los casos | Si da 429 / 503, la corrida termina **sin gastar casos**: `INCONCLUSIVE`, código 2, error completo enmascarado. Un 400 / 404 da `FAIL`, código 1 |
| **Corte temprano:** tras **3 respuestas 429 seguidas**, el guardia se activa | Las solicitudes siguientes se rechazan **localmente, sin HTTP**. El arnés deja de correr casos y el reporte parcial queda `INCONCLUSIVE` con `cases_run` / `cases` |
| **Muestra del error:** `quota_guard.error_samples` guarda el primer mensaje completo de cada categoría, enmascarado y de hasta 2000 caracteres | El `quotaId` (`PerMinute` / `PerDay`) queda en el JSON |
| La evaluación de Gemini **siempre** pasa por el cliente de evaluación, con pausa opcional (por defecto 0) y guardia. Los tests `-m eval` comparten el mismo guardia | Un canario no puede gastar cuota si la evaluación ya detectó que se agotó |

**Sin cambios:** `app/`, el Agent, `GeminiLLMClient`, el fallback, los modelos, la facturación, las metas y la regla PASS / FAIL / INCONCLUSIVE. Una corrida cortada nunca puede salir PASS.

**Tests nuevos (6):**
- el guardia se activa tras 3 errores 429 y la 4.ª llamada no llega al proveedor;
- un éxito u otro error reinicia el contador;
- la muestra conserva el `quotaId` sin la key;
- la verificación previa envía exactamente 1 solicitud, distingue 429 de 400 y funciona con éxito;
- integración: cuota agotada a mitad de corrida → 4 respuestas + 3 rechazos y nada más, `INCONCLUSIVE`, `PerDay` en el reporte.

Regresión offline: **497 passed, 14 deselected**.

## 4c. F7d — Subconjunto estratificado y chequeo N10 (solo el arnés)

**Aprobado (EV-1, EV-2, F7d):** la evidencia final de CP4 tiene dos capas:
- la capa determinista se mide con los 56 casos, sin LLM;
- la contribución de Gemini se mide con un subconjunto de 14 casos definido antes de correr.

**Las metas son las mismas.** Los casos originales **no se modifican**.

| Cambio | Archivo |
|---|---|
| `--case-set full\|stratified` (por defecto `full`, sin cambios). `select_cases()` aplica la regla: el primer caso de cada categoría × idioma, más el primer caso de fuera de alcance que decide el LLM, en cada idioma | `scripts/evaluate_agent.py` |
| El reporte incluye `case_set`, `case_ids`, `cases_run` y `estimated_llm_calls` (`full` = 75, `stratified` = 16, medidos con el LLM fake) | `scripts/evaluate_agent.py` |
| `n10_check`: en las preguntas en español que van por RAG, la consulta de búsqueda debe ser la reescritura al inglés. Se lee con un espía de solo lectura de `_retrieve`. Se reporta; **no es una meta** | `scripts/evaluate_agent.py` |
| Con `EVAL_AGENT_REPORT`, el test N10 lee `n10_check` del reporte **sin llamar a Gemini**. El reporte debe ser de Gemini; uno del fake se rechaza | `tests/evaluation/test_agent_eval.py` |

**Subconjunto (14):** EN-R01, EN-T01, EN-X01, EN-C01, EN-C04, EN-O01, EN-O04, ES-R01, ES-T01, ES-X01, ES-C01, ES-C04, ES-O01, ES-O04.
- Cubre las 5 rutas, las 12 combinaciones categoría × idioma y los dos tipos de "fuera de alcance": por regla y por LLM.
- Presupuesto: 16 solicitudes de Gemini + 1 de verificación previa = 17 de 20, con 3 de margen.

**Tests nuevos (10):** la regla elige exactamente esos 14 ids sobre los casos originales; `full` no cambia; el costo real con el fake coincide con la estimación (16 y 75); las metas son idénticas; el chequeo N10 detecta una consulta que sigue en español; 4 casos de la heurística N10.

Regresión offline: **507 passed, 14 deselected**.

## 5. Corrida final aprobada de CP4: Gemini real, subconjunto estratificado (la corren Pam/Zury)

**Cuándo:** después del reinicio de la cuota diaria (según Google, medianoche del Pacífico; confírmenlo en AI Studio). Nada más debe usar la key durante la corrida: ni la interfaz ni otras terminales. **No corran `diagnose_llm.py` antes:** la verificación previa de F7c lo reemplaza y ahorra 3 solicitudes.

**Paso 1 — la única corrida con Gemini** (≈ 4 minutos, ≈ 17 solicitudes):
```bash
python scripts/evaluate_agent.py --provider gemini --case-set stratified --min-interval 13 --out cp4_gemini_stratified.json
```

**Paso 2 — tests de evaluación desde el reporte** (0 solicitudes de generación; la recuperación usa embeddings, que son otro modelo y otra cuota):

PowerShell:
```powershell
$env:EVAL_AGENT_REPORT = "cp4_gemini_stratified.json"
python -m pytest -m eval -k "not canary" -v
Remove-Item Env:EVAL_AGENT_REPORT
```
bash:
```bash
EVAL_AGENT_REPORT=cp4_gemini_stratified.json python -m pytest -m eval -k "not canary" -v
```
Resultado esperado: **12 passed**: 7 metas, 1 de métricas reportadas, N10 y 3 de recuperación.

**No corran** los canarios directos ni la interfaz ese día: el subconjunto ya ejercita las dos llamadas (intención en JSON y generación de texto).

| Resultado del paso 1 | Qué hacer |
|---|---|
| `STATUS: PASS` y N10 `True` | Compártanme `cp4_gemini_stratified.json` y la salida del paso 2. Actualizo la evidencia de CP3 y CP4 para la aprobación final |
| `PREFLIGHT INCONCLUSIVE` o `STOPPED EARLY` | Cuota o disponibilidad del proveedor: el `quotaId` sale en pantalla y en el JSON. Esperar al siguiente reinicio y repetir **solo el paso 1** |
| `STATUS: FAIL` o N10 `False` | Hallazgo real: compártanme el JSON |

## 5b. (Referencia) Corrida completa de 56 casos con Gemini — diferida a CP5 (EV-3)

> **Nota F7c:** con la cuota diaria de 20 solicitudes, la corrida completa de esta sección **no cabe en un día**. La estrategia de evidencia final está en `CP4_EVIDENCIA_FINAL_PROPUESTA.md`.

**Antes de empezar:**
- No usar la key en paralelo: con la interfaz abierta haciendo preguntas, con otra terminal o con el diagnóstico. Todo comparte las 5 solicitudes por minuto.
- Esperar **al menos 60 s** desde el último uso.

**Paso 1 — Evaluación completa, una sola vez** (≈ 17–20 min):
```bash
python scripts/evaluate_agent.py --provider gemini --min-interval 13 --out cp4_gemini_eval.json
```
Al final imprime `STATUS: PASS` (código de salida 0), `FAIL` (1) o `INCONCLUSIVE` (2).

**Paso 2 — Esperar 60 s** (la pausa es por proceso; los dos pasos son procesos distintos).

**Paso 3 — Tests de evaluación, reutilizando el reporte** (≈ 1–2 min; solo los canarios y N10 llaman a Gemini, ≈ 4 solicitudes):

PowerShell:
```powershell
$env:EVAL_LLM_MIN_INTERVAL_SECONDS = "13"
$env:EVAL_AGENT_REPORT = "cp4_gemini_eval.json"
python -m pytest -m eval -v
Remove-Item Env:EVAL_AGENT_REPORT; Remove-Item Env:EVAL_LLM_MIN_INTERVAL_SECONDS
```
bash:
```bash
EVAL_LLM_MIN_INTERVAL_SECONDS=13 EVAL_AGENT_REPORT=cp4_gemini_eval.json python -m pytest -m eval -v
```
Resultado esperado: **14 passed**.

**Paso 4 — Prueba manual en la interfaz** (opcional). Esperar 60 s después del paso 3 y hacer **máximo 2 preguntas por minuto**: cada respuesta usa unas 2 solicitudes.

| Pregunta | Resultado esperado |
|---|---|
| `¿Quién aprueba la nómina?` | `route_source=llm_intent`, `answer_mode=llm`, **sin** aviso ⚠️ |
| `Why did EMP024 fail?` | `TOOL_RAG`, `template+llm`, explicación con fuentes |

**Cómo leer el resultado:**

| Estado | Qué hacer |
|---|---|
| **PASS** | Compártanme `cp4_gemini_eval.json` y la salida del paso 3. Actualizo la evidencia de CP3 y CP4 para la aprobación final |
| **INCONCLUSIVE** | Revisar `provider_errors`. Esperar unos minutos y repetir **solo el paso 1**. Si se repite con 13 s, se puede subir a `--min-interval 15` |
| **FAIL** | Compártanme el JSON: es un hallazgo real |

---

## 6. Siguiente paso

1. Pam/Zury corren el QA final con Gemini real.
2. Con los resultados, actualizo los documentos de revisión de CP3 y CP4. Las métricas de CP3 que dependían del LLM se reemplazan por la nueva corrida.
3. Aprobación final de CP4 → autorización de CP5.

**Detenido. CP5 no autorizado.**
