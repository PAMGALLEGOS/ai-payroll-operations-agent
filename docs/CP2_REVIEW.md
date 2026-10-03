# CP2 Review Package — Knowledge & RAG

**Proyecto:** AI Payroll Operations & Validation Agent (PoC académico, solo datos sintéticos)
**Checkpoint:** CP2 — Fases 4 y 5 (conocimiento sintético + RAG)
**Preparado por:** Klaudio para Pam (revisión: Zury)
**Fecha:** 3 de octubre de 2026
**Estado:** Completo — **esperando aprobación**. No se inició nada de CP3.

---

## Resumen

La capa de conocimiento funciona de punta a punta con el proveedor de prueba:

- **160 de 160 tests pasan, 0 fallan** (86 de CP1 + 74 de CP2), verificados desde un clon limpio con entorno nuevo en Python 3.11.
- 9 documentos sintéticos → **50 chunks** indexados con metadatos completos.
- El control documentación ↔ `validation_rules.yaml` está automatizado: **0 inconsistencias** hoy, y se probó que falla cuando se cambia una tolerancia solo en el YAML.
- Gemini Embeddings está implementado detrás de una interfaz y probado sin red. **La evaluación con Gemini real no se ha ejecutado** porque no hay API key en este entorno (sección 13).

Hay **cinco decisiones nuevas para aprobar** (sección 14). La más importante es N5: el umbral de similitud para Gemini es provisional y se calibra con la evaluación real.

---

## 1. Archivos creados o modificados

| Grupo | Archivos | Estado |
|---|---|---|
| Conocimiento sintético | 9 documentos en `knowledge/sops/`, `knowledge/rules/`, `knowledge/blueprint/` | Nuevos |
| RAG | `app/rag/documents.py`, `chunking.py`, `embeddings.py`, `vector_index.py`, `ingest.py`, `retriever.py`, `consistency.py` | Nuevos |
| Configuración | `app/core/config.py` (settings desde `.env`) | Nuevo |
| Scripts | `scripts/ingest_knowledge.py`, `search_knowledge.py`, `evaluate_retrieval.py` | Nuevos |
| Tests | 6 archivos en `tests/unit/`, `tests/evaluation/retrieval_cases.yaml`, `tests/evaluation/test_retrieval_eval.py` | Nuevos |
| Soporte | `.gitattributes` | Nuevo |
| Modificados | `app/core/paths.py`, `app/rag/__init__.py`, `requirements.txt`, `.env.example`, `pyproject.toml`, `README.md` | Modificados |

No se modificó nada del Validation Engine de CP1.

## 2. Estructura del repositorio de conocimiento

```
knowledge/
├── sops/
│   ├── payroll_validation_process.md      SOP-001
│   ├── exception_review_process.md        SOP-002
│   └── four_eyes_approval_process.md      SOP-003
├── rules/
│   ├── gross_pay_rule.md                  RULE-001
│   ├── total_deductions_rule.md           RULE-002
│   ├── net_pay_rule.md                    RULE-003
│   ├── tolerances_and_pass_fail.md        RULE-004
│   └── data_quality_rules.md              RULE-005
└── blueprint/
    └── validation_blueprint.md            BP-001
```

Cada documento empieza con un bloque de metadatos (front matter):

```yaml
---
doc_id: RULE-003
title: Net Pay Validation Rule
doc_type: rule
version: "1.0"
rules_version: "1.0.0"        # solo en reglas y blueprint
validation_type: net_pay      # solo en las tres reglas de cálculo
synthetic: true               # obligatorio
---
```

**Control de gobierno:** el loader rechaza cualquier documento sin `synthetic: true`, o cuyo `doc_type` no coincida con su carpeta. Así, un documento corporativo real que alguien copie por error en `knowledge/` nunca se indexa.

## 3. Documentos sintéticos

| ID | Documento | Contenido |
|---|---|---|
| SOP-001 | Payroll Validation Process | Propósito, alcance, roles (Preparer, Reviewer, Engine, asistente de IA), pasos, evidencia, re-ejecución |
| SOP-002 | Exception Review Process | Identificación, investigación por reason code, opciones de resolución, escalamiento, límites del asistente |
| SOP-003 | Four-Eyes Payroll Approval Process | Segregación de funciones, prerrequisitos de aprobación, pasos, rol del asistente |
| RULE-001 | Gross Pay Validation Rule | Fórmula, inputs, tolerancia, causas típicas, efecto en net pay |
| RULE-002 | Total Deductions Validation Rule | Fórmula, deducciones sintéticas, tolerancia, causas típicas |
| RULE-003 | Net Pay Validation Rule | Fórmula, por qué usa valores calculados, tolerancia, interpretación del signo |
| RULE-004 | Tolerances and PASS / FAIL Criteria | Definición de la diferencia, tabla de tolerancias, límite inclusivo, precisión monetaria |
| RULE-005 | Data-Quality Rules | Faltantes, inválidos, combinados, propagación, resultado |
| BP-001 | Payroll Validation Engine Blueprint | Propósito, fuente única de verdad, flujo, tabla de reglas, reason codes, contrato de resultado, evidencia, versionado |

Todos repiten explícitamente que el asistente de IA **no calcula valores autoritativos, no cambia resultados y no aprueba nómina**. Así, en CP3 el Agent podrá citar esa regla desde la evidencia documental.

## 4. Ejemplo de documento

`knowledge/rules/net_pay_rule.md` (extracto):

```markdown
## Definition

Net pay is the amount the employee actually receives: gross pay minus total
deductions.

**Formula:** `net_pay = gross_pay - total_deductions`

## Tolerance

**Tolerance:** 10.00 SYN

The net pay tolerance is wider than the gross pay and deductions tolerances
because net pay accumulates the differences of both components. ...
```

Las líneas `**Formula:**` y `**Tolerance:**` tienen un formato fijo a propósito: es lo que permite que el control de consistencia las verifique automáticamente contra el YAML.

## 5. Estrategia de chunking

`app/rag/chunking.py` — **un chunk por sección del documento**:

| Regla | Por qué |
|---|---|
| Cada `##` o `###` inicia un chunk; el `#` es el título del documento | Los documentos están escritos para que cada sección responda una pregunta ("Tolerance", "Approval Prerequisites"). Así una regla y su explicación quedan juntas |
| Un `###` conserva la ruta de su padre (`Parent > Child`) | La sección completa queda como metadato citable |
| Si una sección supera 1,200 caracteres, se divide por párrafos, nunca a mitad de frase | Evita chunks con ideas cortadas. Hoy ninguna sección lo supera (máximo 718) |
| El aviso "Synthetic…" al inicio de cada documento no se indexa | No contiene conocimiento y solo agregaría 9 chunks casi idénticos que ensucian las búsquedas |
| Se embebe `título > sección + contenido`, pero se guarda solo el contenido | Una sección corta como "Tolerance" conserva el contexto de qué regla es |

Resultado: **50 chunks**, entre 142 y 718 caracteres.

## 6. Ejemplo de chunk indexado y sus metadatos

Cada entrada de `data/vector_index/<proveedor>/index.json`:

```json
{
  "chunk_id": "RULE-003-C03",
  "content": "**Tolerance:** 10.00 SYN\n\nThe net pay tolerance is wider than the gross pay and deductions tolerances because net pay accumulates the differences of both components. ...",
  "metadata": {
    "chunk_id": "RULE-003-C03",
    "chunk_index": 2,
    "doc_id": "RULE-003",
    "source_document": "knowledge/rules/net_pay_rule.md",
    "document_type": "rule",
    "document_title": "Net Pay Validation Rule",
    "document_version": "1.0",
    "section": "Tolerance",
    "section_part": "1/1",
    "char_count": 314
  },
  "vector": [ ... 1024 valores con el proveedor fake, 768 con Gemini ... ]
}
```

Cubre los mínimos de la autorización (documento fuente, tipo de documento, sección, identificador del chunk) y agrega título, versión y posición.

## 7. Implementación de embeddings

`app/rag/embeddings.py` — una interfaz y dos implementaciones:

```
EmbeddingProvider (interfaz)
├── embed_documents(texts)   → se llama UNA vez, en la ingesta
└── embed_query(text)        → se llama por cada pregunta
    │
    ├── GeminiEmbeddingProvider   proveedor aprobado (D2)
    └── FakeEmbeddingProvider     doble de prueba determinista, sin red
```

**Por qué dos métodos:** los modelos de retrieval embeben documentos y preguntas de forma distinta. Gemini lo llama `RETRIEVAL_DOCUMENT` y `RETRIEVAL_QUERY`, y usar el correcto en cada lado mejora el ranking.

**Gemini:**
- Modelo por defecto `gemini-embedding-001`, 768 dimensiones, configurable en `.env`.
- Se envía en lotes de 100 textos.
- Los vectores se normalizan (largo 1), porque este modelo solo los devuelve normalizados en 3,072 dimensiones.
- Si Gemini responde con un número de vectores o un tamaño incorrecto, se detiene con un error claro; los errores del SDK se convierten en un solo tipo de error.
- La librería de Gemini se importa solo al usarla: los tests nunca la necesitan.

**Fake (solo para tests y demos sin credenciales):** convierte cada palabra y cada par de palabras en una posición del vector mediante SHA-256. Es determinista: el mismo texto da siempre el mismo vector. **Mide coincidencia de palabras, no significado**: sirve para probar que el pipeline funciona, no para medir la calidad real del retrieval.

**Sin credenciales:** si el proveedor configurado es Gemini y falta `GEMINI_API_KEY`, el sistema se detiene antes de procesar nada, con este mensaje:

```
ERROR: Gemini embeddings need GEMINI_API_KEY. Set it in .env (see .env.example),
or use the offline test double with EMBEDDINGS_PROVIDER=fake.
```

## 8. Implementación del índice vectorial

`app/rag/vector_index.py`:

- **Un solo archivo JSON** por proveedor (`data/vector_index/fake/index.json`, `data/vector_index/gemini/index.json`). Se puede abrir y ver exactamente qué se indexó y con qué modelo.
- **Similitud coseno escrita en Python simple** (`(a · b) / (|a| × |b|)`), sin numpy. Para 50 chunks una búsqueda lineal es instantánea, y la matemática queda visible.
- **Orden estable:** por puntaje descendente; los empates se resuelven por `chunk_id`.
- **Encabezado de auditoría:** proveedor, modelo, dimensiones, número de chunks, fecha y **huella SHA-256 del conocimiento indexado**.
- **Controles:**
  - Un índice construido con un proveedor o modelo distinto al de la pregunta se rechaza (los vectores de modelos distintos no son comparables).
  - Si un documento cambia después de construir el índice, se detecta como desactualizado y el script de búsqueda avisa que hay que reindexar.
  - Los embeddings de los documentos se calculan una sola vez; un test cuenta las llamadas y comprueba que las preguntas no vuelven a embeber documentos.

## 9. Ejemplo de retrieval semántico

```
python scripts/search_knowledge.py "What is the net pay tolerance?" --provider fake --top-k 3 --json
```

```json
{
  "query": "What is the net pay tolerance?",
  "sufficient_evidence": true,
  "top_score": 0.6779,
  "min_score": 0.13,
  "embeddings_provider": "fake",
  "embeddings_model": "fake-hashing-v1",
  "results": [
    { "chunk_id": "RULE-003-C03", "score": 0.6779,
      "metadata": { "source_document": "knowledge/rules/net_pay_rule.md", "section": "Tolerance", "...": "..." } },
    { "chunk_id": "RULE-003-C02", "score": 0.5122,
      "metadata": { "source_document": "knowledge/rules/net_pay_rule.md", "section": "Inputs", "...": "..." } },
    { "chunk_id": "RULE-001-C05", "score": 0.4795,
      "metadata": { "source_document": "knowledge/rules/gross_pay_rule.md", "section": "Effect on Other Validations", "...": "..." } }
  ]
}
```

Una pregunta sin respuesta documentada:

```
Question  : What is the capital of France?
Evidence  : INSUFFICIENT (top score 0.0000, threshold 0.13)
No chunk reached the similarity threshold: the knowledge base has no documented answer.
```

`sufficient_evidence = false` es la señal que el Agent usará en CP3 para decir "no tengo una respuesta documentada" en lugar de inventarla.

**Evaluación con el proveedor fake** (16 preguntas con respuesta + 5 fuera de alcance):

| Métrica | Resultado fake |
|---|---|
| hit@1 | 88 % |
| hit@4 | 100 % |
| MRR | 0.938 |
| Preguntas con respuesta marcadas como sin evidencia | 0 |
| Preguntas fuera de alcance rechazadas | 100 % |

Estos números **no miden la calidad real**: las preguntas de evaluación comparten palabras con los documentos, y el fake solo mide eso. El margen entre la pregunta relevante con menor puntaje (0.137) y la irrelevante con mayor puntaje (0.126) es muy estrecho. La medición válida es la de Gemini (sección 13).

## 10. Resultado del control documentación ↔ Engine

`app/rag/consistency.py` compara los documentos contra `config/validation_rules.yaml`:

| Qué verifica | Dónde |
|---|---|
| `rules_version` | Las 5 reglas y el blueprint |
| Fórmula exacta | Cada documento de regla (`**Formula:**`) y cada fila de tabla |
| Tolerancia y moneda | Cada documento de regla (exactamente una línea `**Tolerance:**`) y cada fila de tabla |
| Cobertura | Un documento por `validation_type`; el blueprint lista los tres tipos |
| Límite PASS/FAIL | El blueprint y RULE-004 dicen `abs(difference) <= tolerance` y definen `difference = actual_value - expected_value`; ningún documento dice `<` estricto |
| Reason codes | El blueprint documenta los 4 códigos que emite el Engine |

**Resultado actual: 0 inconsistencias.**

**Se probó que el control realmente falla** (8 tests de mutación):

| Cambio simulado | Detectado |
|---|---|
| Tolerancia de net_pay cambiada solo en el YAML (10.00 → 15.00) | ✅ en 3 lugares: regla, tabla de tolerancias y tabla del blueprint |
| Fórmula de gross_pay cambiada solo en el YAML | ✅ |
| `rules_version` subida sin actualizar documentos | ✅ en los 6 documentos |
| Tolerancia cambiada solo en el documento | ✅ |
| Límite escrito como `<` estricto | ✅ |
| Frase del límite borrada del blueprint | ✅ |
| Reason code faltante en el blueprint | ✅ |
| Nueva validación en el YAML sin documento | ✅ |

Además, cambié temporalmente la tolerancia de net_pay en el YAML real: el test de consistencia falló y volvió a pasar al restaurarla.

## 11. Resumen de ejecución de tests

```
python -m pytest -q
160 passed, 3 deselected
```

Los 3 "deselected" son los tests de evaluación con Gemini real, que solo corren con `pytest -m eval`.

| Archivo | Tests | Qué cubre |
|---|---|---|
| `test_rag_documents.py` | 9 | Carga de los 9 documentos, guardia `synthetic`, carpeta vs tipo, front matter faltante, IDs duplicados, carpeta vacía, finales de línea de Windows |
| `test_rag_chunking.py` | 7 | Un chunk por sección, aviso omitido, ruta `Parent > Child`, división por párrafos, metadatos completos, IDs únicos, determinismo |
| `test_embeddings.py` | 18 | Interfaz, fake determinista y normalizado, fábrica, **Gemini sin key**, proveedor desconocido, tipos de tarea de Gemini, lotes, normalización, errores de respuesta y del SDK |
| `test_vector_index.py` | 13 | Coseno (iguales, ortogonales, opuestos, vector cero, tamaños distintos), orden, desempate, top-k, guardar/cargar, índice faltante o malformado |
| `test_rag_ingest_retrieval.py` | 18 | Índice completo, indexación determinista, **documentos embebidos una sola vez**, índice desactualizado, proveedor incompatible, documento relevante recuperado (6 preguntas), orden y metadatos, preguntas sin respuesta, umbral, pregunta vacía, RAG no devuelve resultados de validación, script de evaluación |
| `test_doc_consistency.py` | 9 | Consistencia actual + 8 mutaciones |

Cobertura de la lista mínima de la autorización:

| Requisito | Cubierto en |
|---|---|
| Carga de documentos | `test_rag_documents.py` |
| Generación de chunks | `test_rag_chunking.py` |
| Preservación de metadatos | `test_rag_chunking.py`, `test_rag_ingest_retrieval.py` |
| Indexación determinista | `test_indexing_is_deterministic` |
| Similitud coseno | `test_vector_index.py` |
| Orden del retrieval | `test_search_orders_by_score_descending`, `test_results_are_ordered_...` |
| Recuperación del documento relevante | `test_relevant_document_is_retrieved` (6 casos) |
| Preguntas desconocidas o con poco soporte | `test_unrelated_query_reports_insufficient_evidence` |
| Consistencia documentación ↔ YAML | `test_doc_consistency.py` |
| Abstracción del proveedor | `test_embeddings.py` |
| Comportamiento sin credenciales de Gemini | `test_factory_refuses_gemini_without_api_key`, `test_gemini_requires_api_key` |

## 12. Tests aprobados / fallidos

**160 aprobados, 0 fallidos** (86 de CP1 + 74 de CP2). Verificado desde un clon limpio con entorno virtual nuevo en Python 3.11. Los 3 tests de evaluación con Gemini se omiten sin API key, como está diseñado.

## 13. Estado de la evaluación con Gemini real

**No ejecutada.** Este entorno no tiene `GEMINI_API_KEY`. El código de Gemini está probado con un cliente simulado (qué se envía y cómo se procesa la respuesta), pero **ninguna llamada real a Gemini se ha hecho todavía**.

Pasos que **requieren Gemini real**:

| Paso | Comando | Qué valida |
|---|---|---|
| 1. Construir el índice con Gemini | `python scripts/ingest_knowledge.py --provider gemini` | Conexión, modelo, dimensiones, lotes |
| 2. Búsqueda de prueba | `python scripts/search_knowledge.py "Who approves the payroll?" --provider gemini` | Retrieval semántico real |
| 3. Evaluación completa | `python scripts/evaluate_retrieval.py --provider gemini` | hit@1, hit@4, MRR, rechazo fuera de alcance, **calibración del umbral** |
| 4. Tests de evaluación | `python -m pytest -m eval -v` | Metas de aceptación (N5) |

Recomiendo correr estos cuatro pasos en tu máquina antes de aprobar CP2, o aprobar CP2 con la condición de que se corran al inicio de CP3. El paso 3 dirá qué umbral usar para Gemini.

## 14. Decisiones técnicas nuevas que requieren aprobación

### N5 — Umbral de similitud y metas de evaluación
Los puntajes de similitud no son comparables entre modelos, así que cada proveedor tiene su propio umbral:
- **Fake: 0.13**, calibrado con los casos de evaluación.
- **Gemini: 0.60 provisional.** Debe calibrarse con el paso 3 de la sección 13 y fijarse en `.env` (`RAG_MIN_SCORE`).

Metas de aceptación propuestas para Gemini: **hit@4 ≥ 90 %**, **rechazo fuera de alcance ≥ 80 %** y **cero preguntas con respuesta marcadas como sin evidencia**.

### N6 — Configuración de Gemini Embeddings
`gemini-embedding-001`, 768 dimensiones, con `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`. `gemini-embedding-2` se **rechaza explícitamente**: no acepta tipo de tarea y requiere otro formato de entrada que no se ha validado. Es mejor rechazarlo con un mensaje claro que soportarlo a medias.

### N7 — Estrategia de chunking
Un chunk por sección, máximo 1,200 caracteres con división por párrafos, aviso sintético omitido, y título + sección incluidos en el texto que se embebe (sección 5).

### N8 — Convención de escritura de los documentos
- Front matter obligatorio con `synthetic: true`.
- Las reglas usan líneas fijas `**Formula:**` y `**Tolerance:**`, y tablas `| tipo | `fórmula` | X SYN |`.

Esta convención es lo que hace automático el control de consistencia: cualquier documento nuevo de reglas debe seguirla.

### N9 — Índice desactualizado: avisar, no bloquear
Hoy, si un documento cambió después de construir el índice, el script de búsqueda **avisa** pero sigue respondiendo. Propongo que en CP3 el Agent **bloquee** el uso de un índice desactualizado, porque ahí sí habría riesgo de citar texto que ya no existe.

## 15. Desviaciones respecto a la arquitectura aprobada

Ninguna desviación funcional. Ajustes técnicos:

1. **No se usa numpy** aunque D13 lo aprobó. La similitud coseno en Python simple basta para 50 chunks y es más transparente. Una dependencia menos.
2. **Dependencias nuevas:** `pydantic-settings` (aprobada en D13) y `google-genai` (D1/D2). `google-genai` instala a su vez dependencias propias (httpx, pydantic, google-auth y otras); solo se fijan las dos directas.
3. **Scripts adicionales** `search_knowledge.py` y `evaluate_retrieval.py`, para que puedas verificar CP2 sin el Agent.
4. **Casos de evaluación de retrieval** (`tests/evaluation/retrieval_cases.yaml`) creados ya en CP2. La spec los ubica en la Fase 12; aquí solo cubren retrieval.
5. **El control de consistencia vive en `app/rag/consistency.py`**, no solo en los tests, para poder reutilizarlo después (por ejemplo, en un health check).
6. **`.gitattributes`** para mantener finales de línea LF en cualquier sistema operativo, y normalización de finales de línea de Windows al leer documentos. Sin esto, las huellas SHA-256 y el test de dataset idéntico de CP1 podrían fallar en Windows.
7. **`pytest` excluye por defecto los tests de evaluación** (`-m 'not eval'`).

## 16. Comandos para verificar CP2 localmente

```bash
cd ai-payroll-agent
python3.11 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. Todos los tests (sin API key)
python -m pytest -v                    # 160 passed

# 2. Pipeline completo con el proveedor de prueba
python scripts/ingest_knowledge.py --provider fake
python scripts/search_knowledge.py "Is a difference exactly equal to the tolerance a PASS?" --provider fake
python scripts/search_knowledge.py "What is the capital of France?" --provider fake
python scripts/evaluate_retrieval.py --provider fake

# 3. Comportamiento sin credenciales (debe terminar con un error claro)
python scripts/ingest_knowledge.py --provider gemini

# 4. Con Gemini real
cp .env.example .env                   # Windows: copy .env.example .env  — luego pon tu GEMINI_API_KEY
python scripts/ingest_knowledge.py --provider gemini
python scripts/search_knowledge.py "Who approves the payroll?" --provider gemini
python scripts/evaluate_retrieval.py --provider gemini
python -m pytest -m eval -v
```

---

## Checklist del Definition of Done de CP2

| Criterio | Estado |
|---|---|
| Existen documentos sintéticos de conocimiento | ✅ 9 documentos |
| Los documentos se pueden ingerir | ✅ |
| Los documentos se dividen en chunks | ✅ 50 chunks |
| Los chunks conservan metadatos de origen | ✅ |
| Los embeddings se generan a través de la abstracción aprobada | ✅ Gemini + fake detrás de `EmbeddingProvider` |
| Las representaciones vectoriales se indexan | ✅ |
| El retrieval semántico funciona | ✅ con fake · ⏳ pendiente con Gemini real |
| Se devuelven chunks relevantes con metadatos | ✅ |
| La documentación se verifica automáticamente contra las reglas del Engine | ✅ |
| Los tests automatizados pasan | ✅ 160/160 |
| No hay información real de nómina o corporativa | ✅ |
| No se implementó funcionalidad del Agent | ✅ |
| No hay credenciales de Gemini en el repositorio | ✅ |

**Detenido. Esperando aprobación de CP2 y de N5–N9 antes de iniciar CP3.**
