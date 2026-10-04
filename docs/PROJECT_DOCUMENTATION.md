# AI Payroll Operations & Validation Agent

**Programa:** AI-LLM Solution Architect  
**Curso:** 5 - Proyecto Final de Arquitectura e Integración AI/LLM  
**Documento:** Plantilla Oficial de Documentación del Proyecto  
**Versión:** v1.0.0  
**Estado:** Completado - Academic PoC  
**Fecha de entrega:** 04/10/2026  
**Participante:** Pam GR  
**Instructor:** Andrew  
**Repositorio:** https://github.com/PAMGALLEGOS/ai-payroll-operations-agent  
**Cloud:** Google Cloud Platform - Cloud Run  
**Servicio:** `payroll-agent`, región `us-central1`, revisión `payroll-agent-00001-5pd`  
**Aplicación desplegada:** https://payroll-agent-190772421839.us-central1.run.app  
**Stack principal:** Python, FastAPI, Streamlit, Google Gemini, RAG, Docker, Google Cloud Run, Secret Manager

> **Nota de privacidad:** el PoC utiliza exclusivamente datos y documentación sintéticos. No contiene datos reales de empleados ni información corporativa confidencial.

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Análisis y Especificación de Requerimientos](#2-análisis-y-especificación-de-requerimientos)
3. [Diseño de Arquitectura AI/LLM](#3-diseño-de-arquitectura-aillm)
4. [Diseño de APIs y Conectores](#4-diseño-de-apis-y-conectores)
5. [Seguridad, Cumplimiento y Ética](#5-seguridad-cumplimiento-y-ética)
6. [Implementación y Configuración de Infraestructura](#6-implementación-y-configuración-de-infraestructura)
7. [Estrategia de Pruebas y Resultados](#7-estrategia-de-pruebas-y-resultados)
8. [Despliegue, Escalabilidad y Costos](#8-despliegue-escalabilidad-y-costos)
9. [Observabilidad y Monitoreo](#9-observabilidad-y-monitoreo)
10. [Resultados, Conclusiones y Trabajo Futuro](#10-resultados-conclusiones-y-trabajo-futuro)
11. [Rúbrica de Evaluación - Autoevaluación](#11-rúbrica-de-evaluación---autoevaluación)
12. [Referencias y Bibliografía](#12-referencias-y-bibliografía)
13. [Anexos](#anexos)

---

# 1. Resumen Ejecutivo

## 1.1 Propuesta de Valor y Problema que Resuelve

Las operaciones de Payroll en entornos multipaís requieren coordinar procesamiento, validación, análisis de excepciones, conocimiento operativo y colaboración con múltiples actores dentro de ventanas de tiempo estrictas. Cuando estas actividades dependen de revisiones manuales y conocimiento distribuido, aumenta la dependencia de especialistas y disminuye el tiempo disponible para análisis y mejora continua.

**AI Payroll Operations & Validation Agent** es un Proof of Concept que combina una capa determinística de validación con capacidades AI/LLM. El objetivo no es permitir que un modelo de lenguaje calcule o apruebe nómina, sino utilizar el LLM donde aporta valor: comprensión de intención, orquestación, recuperación de conocimiento y explicación contextual.

El principio arquitectónico central es:

> **LLM understands -> Code decides -> Engine validates -> RAG grounds -> Auditor controls -> Human approves.**

El Payroll Validation Engine mantiene la autoridad sobre cálculos, tolerancias, estados PASS/FAIL y excepciones. RAG recupera evidencia documental sintética. El Agent decide qué capacidades utilizar y Gemini genera explicaciones únicamente a partir de hechos y contexto suministrados. Un Auditor determinístico verifica grounding, consistencia, alcance y decisiones prohibidas antes de presentar la respuesta. La aprobación final permanece en manos humanas.

El PoC fue desplegado en Google Cloud Run y se verificó una ejecución real end-to-end en cloud. La consulta controlada **“¿Por qué falló EMP024?”** recorrió Gemini para intención, Validation Engine, RAG, generación, Auditor y ruta `TOOL_RAG`, finalizando con HTTP 200 y el trace `TRACE-4f596f6a`.

## 1.2 Alcance y Delimitación

| EN SCOPE | OUT OF SCOPE |
|---|---|
| Agente conversacional especializado en Payroll | Procesamiento de nómina productiva real |
| Consultas EN/ES | Agente de propósito general |
| Validation Engine determinístico | Cálculos de Payroll realizados por el LLM |
| Custom Tool para resultados estructurados | Modificación de resultados del Engine por el Agent |
| RAG sobre SOPs, reglas y Blueprint sintéticos | Documentos corporativos confidenciales |
| Explicaciones TOOL, RAG y TOOL_RAG | Asesoría legal/fiscal definitiva |
| Auditor/guardrails | Aprobación autónoma de nómina |
| Human-in-the-Loop | Pagos o transacciones financieras |
| FastAPI + Streamlit | Integraciones productivas con HRIS/ERP/T&A |
| Observabilidad y trazabilidad | SLA empresarial de producción |
| Docker + Cloud Run | Arquitectura productiva multi-servicio completa |

## 1.3 Indicadores Clave de Éxito

| KPI | Meta | Resultado final |
|---|---:|---|
| Latencia end-to-end p95 | < 3 s | **NO CONCLUYENTE** con Gemini real; la capa determinística mostró p95 <= 14 ms por ruta, pero no representa E2E real |
| Tasa de éxito de respuestas | >= 92% | **NO CONCLUYENTE** con Gemini real; 56/56 casos determinísticos y 11/14 casos de evaluación real ejecutados, afectados por 429/503 |
| Precisión de recuperación RAG | >= 85% | **VERIFICADO:** hit@1 100% con embeddings Gemini en 21 casos; umbral 0.638 |
| Exactitud de invocación Custom Tool | >= 95% | **PARCIALMENTE MEDIDO:** 100% en categorías TOOL/TOOL_RAG determinísticas y ruteo 100% en casos reales ejecutados |
| Consistencia Agent <-> Engine | 100% críticos | **VERIFICADO:** 100% |
| Detección del Auditor | >= 90% | **VERIFICADO:** 16/16 respuestas incorrectas detectadas; 0/3 falsos positivos de control |
| Manejo fuera de alcance | 100% | **VERIFICADO:** 100% en 12 casos EN/ES |
| Cobertura de pruebas | >= 80% | **VERIFICADO:** 96% de cobertura de sentencias de `app/` en suite offline |
| Costo / 1,000 consultas | <= USD 5 | **NO MEDIDO** estadísticamente; no se extrapola sin evidencia suficiente |
| Disponibilidad controlada | >= 99% | **NO MEDIDO** como SLA; deployment y smoke test HTTP 200 verificados |

---

# 2. Análisis y Especificación de Requerimientos

## 2.1 Contexto del Caso de Uso Empresarial

### AS-IS

El usuario debe localizar procedimientos y reglas en distintas fuentes, consultar resultados de validación y relacionar manualmente una excepción con el conocimiento operativo aplicable. Las herramientas determinísticas pueden validar de manera consistente, pero no proporcionan por sí mismas una interfaz conversacional que conecte resultados y contexto documental.

### TO-BE

El Agent actúa como capa de interacción y orquestación. El usuario pregunta en lenguaje natural; el sistema identifica intención y entidades; decide mediante código si necesita Tool, RAG, ambos, aclaración o rechazo; consulta las fuentes correspondientes; genera una explicación grounded; audita la respuesta y mantiene la decisión final en manos humanas.

## 2.2 Requerimientos Funcionales

1. Aceptar consultas de Payroll en español e inglés.
2. Detectar empleado, periodo e intención cuando estén presentes.
3. Consultar resultados estructurados del Validation Engine sin recalcularlos.
4. Recuperar documentación sintética relevante mediante RAG.
5. Combinar Engine + RAG cuando la pregunta requiera hechos y explicación.
6. Solicitar aclaración cuando falte contexto crítico.
7. Rechazar acciones prohibidas o fuera de alcance.
8. Auditar cada respuesta antes de presentarla.
9. Mantener contexto temporal de sesión sin memoria persistente.
10. Exponer API, dashboard, chat y health check.
11. Registrar trazabilidad mediante `trace_id` y eventos JSONL.
12. Degradar de forma segura cuando el proveedor LLM no esté disponible.

## 2.3 Requerimientos No Funcionales

- Determinismo y auditabilidad para cálculos de Payroll.
- Separación de responsabilidades entre Engine, Agent, RAG y Auditor.
- Uso exclusivo de datos sintéticos.
- Secretos fuera del código y del repositorio.
- Pruebas automatizadas y evidencia reproducible.
- Despliegue cloud accesible.
- Trazabilidad por request/trace.
- Manejo seguro de fallas de proveedor.
- Diseño compatible con evolución hacia servicios separados y controles empresariales.

## 2.4 Restricciones y Supuestos

El PoC no reemplaza controles humanos ni representa una plataforma productiva. Gemini es una dependencia externa para tareas probabilísticas, por lo que cuotas, disponibilidad y facturación pueden afectar evaluaciones reales. La población procesada por el Engine no está limitada por la cuota del LLM: el Engine procesa los registros determinísticamente; la cuota afecta interacciones que requieren Gemini.

---

# 3. Diseño de Arquitectura AI/LLM

## 3.1 Arquitectura Lógica

```text
Usuario
  |
  v
Streamlit Web UI
  |
  v
FastAPI
  |
  v
Agent / Orchestrator
  |----------------------|
  |                      |
  v                      v
Validation Tool          RAG
  |                      |
  v                      v
Validation Engine        Knowledge Base
  |                      |
  |----------+-----------|
             v
        LLM / Gemini
             |
             v
      Audit & Guardrails
             |
             v
       Human-in-the-Loop

Observability / trace_id / JSONL atraviesa el flujo.
```

## 3.2 Componentes y Responsabilidades

| Componente | Responsabilidad |
|---|---|
| Validation Engine | Cálculos, tolerancias, PASS/FAIL, excepciones y reason codes |
| Validation Tool | Acceso estructurado y de solo lectura a resultados |
| RAG | Recuperación de SOPs, reglas, fórmulas y Blueprint sintéticos |
| Agent / Orchestrator | Intención, entidades, selección de capacidades y composición |
| Gemini | Clasificación semántica y generación grounded cuando aplica |
| Auditor | Grounding numérico, consistencia, citas, alcance y decisiones prohibidas |
| Session Context | Contexto temporal multi-turn |
| FastAPI | Contratos de servicio |
| Streamlit | Dashboard y chat |
| Observability | Eventos, latencia, trace_id y redacción de secretos |
| Human reviewer | Investigación, excepción y aprobación final |

## 3.3 Validation Engine

Las reglas viven en `config/validation_rules.yaml`. La aritmética usa `Decimal`. Para cada validación se calculan `expected_value`, `actual_value`, `difference` y se aplica la tolerancia configurada. La salida incluye `status`, `exception`, `reason_code` y detalle. Un dato faltante o inválido no se convierte en cero: produce un estado explícito.

El dataset sintético del periodo 2026-09 contiene 30 empleados y escenarios diseñados para PASS, límites de tolerancia, FAIL, datos faltantes, datos inválidos y registros de proveedor ausentes.

## 3.4 RAG

La base documental es sintética y contiene SOPs, reglas, fórmulas y Blueprint. Los documentos se dividen por secciones, se generan embeddings y se recuperan chunks con metadatos y citas. El umbral calibrado con Gemini fue 0.638. Si no existe evidencia suficiente, el sistema no inventa una respuesta documental.

## 3.5 Agent / Orchestration

Rutas implementadas:

- `TOOL`: hechos estructurados del Engine.
- `RAG`: respuesta documental grounded.
- `TOOL_RAG`: hechos del Engine + explicación documentada.
- `CLARIFY`: falta contexto crítico.
- `OUT_OF_SCOPE`: acción prohibida, tema ajeno o solicitud fuera del alcance.

La selección final de ruta está controlada por código. El LLM no tiene autoridad para aprobar, recalcular o modificar resultados.

## 3.6 Audit & Guardrails

Checks determinísticos: `numeric_grounding`, `status_consistency`, `employee_consistency`, `prohibited_decision`, `citation_validity`, `citation_required`, `scope` y `no_arithmetic`.

Veredictos: `ALLOW`, `REVISE` o `BLOCK`. Una respuesta que requiere revisión puede ser reescrita una sola vez y se vuelve a auditar. Una decisión prohibida o una segunda falla se bloquea con respuesta segura.

## 3.7 Human-in-the-Loop

Las respuestas relacionadas con resultados y excepciones indican que la investigación y la aprobación corresponden a un revisor humano. El Agent es una capa de soporte y explicación, no una autoridad de Payroll.

---

# 4. Diseño de APIs y Conectores

## 4.1 API

La aplicación utiliza FastAPI y contratos Pydantic. La documentación interactiva OpenAPI/Swagger se expone en `/docs` cuando el servicio API se ejecuta directamente.

| Endpoint | Función |
|---|---|
| `POST /chat` | Consulta conversacional; devuelve trace, ruta, intención, entidades, respuesta, Engine, evidencia, Auditor y latencia |
| `GET /validation` | Consulta resultados del Engine por periodo, empleado, validación o estado |
| `POST /documents/ingest` | Reconstruye el índice; puede protegerse con `INGEST_TOKEN` |
| `GET /health` | Estado de corridas, Agent, índice y LLM |

Los errores tienen formato uniforme con `error`, `message` y `trace_id`.

## 4.2 Conectores

El PoC no se conecta a sistemas corporativos reales. Los conectores son internos al propio PoC: archivos sintéticos, índice RAG, Validation Tool y proveedor Gemini. Esta decisión reduce riesgo y mantiene el alcance académico reproducible.

## 4.3 Contratos y Separación

Streamlit consume la API y no importa directamente Engine, Agent ni LLM. Esto evita duplicar lógica de negocio en la presentación y mantiene una única fuente de verdad.

---

# 5. Seguridad, Cumplimiento y Ética

## 5.1 Datos y Privacidad

- 100% de los datos y documentos son sintéticos.
- No existen datos reales de empleados.
- No existen conexiones a HRIS, ERP, T&A o payroll productivos.
- El sistema no ejecuta pagos ni movimientos financieros.

## 5.2 Secretos

`GEMINI_API_KEY` se mantiene fuera del repositorio. Localmente `.env` está ignorado por Git; en GCP la clave se suministra mediante Secret Manager (`gemini-api-key`). Los logs aplican redacción de secretos y no deben exponer la API key.

## 5.3 Controles de Autoridad

El LLM no puede cambiar PASS/FAIL, recalcular nómina ni aprobar excepciones. Las acciones prohibidas se interceptan antes de la generación. El Auditor verifica además que la respuesta no introduzca decisiones no autorizadas.

## 5.4 Ética y Transparencia

El diseño evita presentar inferencias probabilísticas como hechos determinísticos. Los resultados del Engine se distinguen de las explicaciones generadas. Las limitaciones de proveedor y los fallbacks se hacen visibles. El usuario conserva la responsabilidad de la decisión final.

---

# 6. Implementación y Configuración de Infraestructura

## 6.1 Estructura del Repositorio

| Ruta | Propósito |
|---|---|
| `app/validation/` | Engine y Tool |
| `app/rag/` | Ingesta, embeddings, índice y retrieval |
| `app/agent/` | Orquestación, intención, rutas y sesión |
| `app/audit/` | Auditor y guardrails |
| `app/llm/` | Cliente Gemini y fake LLM para pruebas |
| `app/api/` | FastAPI |
| `app/web/` | Streamlit |
| `app/observability/` | Eventos, logs, trazas y redacción |
| `config/` | Reglas de validación |
| `data/` | Datos sintéticos |
| `knowledge/` | Documentos sintéticos |
| `scripts/` | Operación, evaluación y diagnóstico |
| `tests/` | Unitarias, integración, API, web, observabilidad, deploy y evaluación |
| `deploy/` | Script de arranque Cloud Run |
| `docs/` | Evidencia y documentación |

## 6.2 Runtime

La imagen usa Python 3.11-slim. El contenedor arranca FastAPI/Uvicorn en `127.0.0.1:8000`, espera `/health` y después publica Streamlit en `0.0.0.0:$PORT`. El proceso supervisa ambos componentes y utiliza stdout para Cloud Logging.

## 6.3 Configuración

Variables principales:

- `LLM_PROVIDER=gemini`
- `EMBEDDINGS_PROVIDER=gemini`
- `GEMINI_MODEL=gemini-3.8-flash`
- `GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001`
- `LOG_LEVEL=INFO`
- `GEMINI_API_KEY` desde Secret Manager

El nombre de modelo se valida al iniciar para evitar degradación silenciosa por configuración inválida.

---

# 7. Estrategia de Pruebas y Resultados

## 7.1 Estrategia

La estrategia combina pruebas determinísticas offline, pruebas de integración, evaluación RAG, casos sembrados para Auditor, consultas fuera de alcance, evaluación real estratificada con Gemini y un smoke test real en Cloud Run.

## 7.2 Regresión Offline Final

En el entorno local Windows se ejecutó:

```text
python -m pytest -m "not eval" -q
```

Resultado final:

```text
1 failed, 514 passed, 14 deselected in 13.34s
```

La única falla corresponde a `tests/deploy/test_deploy_package.py::test_start_script_syntax` porque Windows no dispone del ejecutable `bash` (`FileNotFoundError [WinError 2]`). No fue una falla funcional de la aplicación. En un entorno Linux compatible, la validación del paquete había completado 515 pruebas PASS y 14 deselected.

La cobertura offline de `app/` fue 96% de sentencias.

## 7.3 RAG y Auditor

- RAG: hit@1 100% con embeddings Gemini en 21 casos; umbral 0.638.
- Auditor: 16/16 respuestas incorrectas sembradas detectadas.
- Controles correctos del Auditor: 0/3 falsos positivos.
- Out-of-scope: 100% en 12 casos EN/ES.
- Consistencia Agent <-> Engine: 100% en casos críticos evaluados.

## 7.4 Evaluación Real Estratificada con Gemini

La evaluación real ejecutó 11 de 14 casos antes de detenerse por errores de proveedor/cuota. Resultados observados:

- routing accuracy: 100%
- clarify: 100%
- out_of_scope: 100%
- engine consistency: 100%
- seeded auditor: 100%
- N10: `true`
- intent LLM rate: 33.3%
- generation success rate: 50%
- errores observados: 2 respuestas 429 y 7 respuestas 503
- early stop tras 3 errores 429 consecutivos

**Estado oficial: INCONCLUSIVE.** No se interpreta como PASS ni como FAIL de calidad del sistema porque la ejecución fue incompleta y estuvo condicionada por disponibilidad/cuota del proveedor.

Evidencia: `cp4_gemini_stratified.json` y `cp4_gemini_stratified_INCONCLUSIVE_2026-10-04.json`.

## 7.5 Smoke Test Real End-to-End en Cloud

Consulta controlada:

```text
¿Por qué falló EMP024?
```

Resultado:

- ruta: `TOOL_RAG`
- intent: `validation_explanation`
- empleado: `EMP024`
- periodo: `2026-09`
- Engine `found=true`
- `fail_count=1`
- gross_pay PASS
- total_deductions PASS
- net_pay FAIL; expected 3732.48, provider 4082.48, difference +350, tolerance 10, `OUT_OF_TOLERANCE`
- evidencia RAG recuperada y citada
- Auditor ejecutado
- HTTP 200
- trace: `TRACE-4f596f6a`

Cadena observada en Cloud Logging:

```text
request_received
-> llm_called (intent)
-> intent_identified
-> tool_called
-> engine_result
-> rag_retrieved
-> llm_called (generation)
-> auditor_result
-> route_decided (TOOL_RAG)
-> response_completed
-> api_request (200)
```

Esta prueba constituye evidencia real de integración del flujo completo, pero no sustituye una evaluación estadística de disponibilidad o desempeño.

## 7.6 Resiliencia

Antes de habilitar crédito de proveedor, una ejecución recibió HTTP 402 por prepayment depleted. El sistema no colapsó: aplicó fallback de intención, consultó el Engine, registró la degradación, evitó inventar evidencia RAG cuando embeddings no estaban disponibles y devolvió una respuesta segura. Este comportamiento se conserva como evidencia de resiliencia.

---

# 8. Despliegue, Escalabilidad y Costos

## 8.1 Despliegue Real

| Campo | Valor |
|---|---|
| Plataforma | Google Cloud Run |
| Servicio | `payroll-agent` |
| Región | `us-central1` |
| Revisión verificada | `payroll-agent-00001-5pd` |
| Tráfico | 100% a la revisión verificada |
| URL | `https://payroll-agent-190772421839.us-central1.run.app` |
| Puerto público | 8080 |
| Memoria | 1 GiB |
| Máximo de instancias | 1 |
| Secretos | Google Secret Manager |

Topología académica desplegada:

```text
Browser -> Streamlit ($PORT/8080)
        -> FastAPI/Uvicorn (127.0.0.1:8000)
        -> Agent
        -> Validation Engine / RAG / Gemini
        -> Auditor
```

La topología de un solo servicio se eligió para el PoC académico. En producción sería razonable separar frontend, API y workloads de procesamiento.

## 8.2 Escalabilidad

El tamaño de la población de Payroll no está ligado a la cuota de Gemini. El Engine puede procesar la población completa de forma determinística; el consumo LLM ocurre únicamente en interacciones que requieren clasificación semántica o generación. Para una evolución productiva se recomienda separar consultas estructuradas que no requieren LLM y reservar generación para casos donde agrega valor.

## 8.3 Costos

El proyecto utilizó consumo controlado y configuración de seguridad de costos: `max-instances=1`, presupuesto/alerta en Google Cloud y recarga automática desactivada en el crédito prepago de Gemini. No se obtuvo una muestra suficiente para afirmar un costo estadístico por 1,000 consultas, por lo que ese KPI permanece **NO MEDIDO**.

---

# 9. Observabilidad y Monitoreo

## 9.1 Eventos

El sistema registra eventos estructurados JSONL y usa `trace_id` para correlacionar el ciclo completo de una solicitud. Entre los eventos se encuentran recepción de request, llamada al LLM, intención, llamada a Tool, resultado del Engine, retrieval, Auditor, decisión de ruta, finalización y respuesta API.

## 9.2 Métricas y Diagnóstico

Se registran latencias, ruta, origen de ruta, modo de respuesta, degradación del LLM, resultado del Auditor y errores. Cloud Run envía stdout a Cloud Logging, lo que permitió reconstruir la ejecución `TRACE-4f596f6a`.

## 9.3 Protección de Logs

Los errores de proveedor se registran para diagnóstico, pero los secretos son enmascarados. El repositorio excluye `.env` y la API key se inyecta mediante Secret Manager.

---

# 10. Resultados, Conclusiones y Trabajo Futuro

## 10.1 Resultados Principales

El PoC demuestra que una arquitectura híbrida puede mantener los cálculos críticos fuera del LLM y utilizar AI para interpretación y explicación. El Engine, RAG, Agent, Auditor, API, interfaz y observabilidad fueron integrados y desplegados. La ejecución real `TOOL_RAG` en Cloud Run confirmó el flujo completo.

Los resultados determinísticos y de control son sólidos dentro del alcance probado. La evaluación real amplia con Gemini permanece **INCONCLUSIVE** por fallas externas 429/503 y no debe reinterpretarse como un resultado de calidad que no se midió completamente.

## 10.2 Lecciones Aprendidas

1. **No todo debe agentizarse.** Los cálculos y reglas de Payroll necesitan determinismo y auditabilidad.
2. **Grounding requiere arquitectura, no solo prompting.** Engine, RAG y Auditor tienen responsabilidades separadas.
3. **La resiliencia debe ser visible.** Un fallback silencioso puede hacer parecer exitoso un flujo que perdió capacidades.
4. **La evaluación del LLM debe distinguir calidad del sistema de disponibilidad del proveedor.** Un 429/503 no debe confundirse con una respuesta incorrecta del Engine.
5. **El dato es la base de la escalabilidad.** Una futura plataforma debe combinar conocimiento documental, validación determinística y consultas estructuradas históricas.

## 10.3 Limitaciones

- Dataset y documentación exclusivamente sintéticos.
- Sin integraciones corporativas productivas.
- Sin autenticación/SSO empresarial.
- Sin SLA estadístico de disponibilidad.
- Sin prueba formal de concurrencia.
- Costo por 1,000 consultas no medido.
- Evaluación Gemini estratificada incompleta e INCONCLUSIVE.
- Topología Cloud Run de un solo servicio adecuada para PoC, no arquitectura final empresarial.

## 10.4 Trabajo Futuro

### Corto plazo

- ampliar evaluación real cuando exista capacidad estable del proveedor;
- incorporar métricas end-to-end repetibles de latencia y costo;
- fortalecer CI/CD y pruebas de despliegue Linux;
- formalizar documentación OpenAPI exportable.

### Mediano plazo

- separar frontend/API/workers;
- incorporar identidad, RBAC y controles empresariales;
- conectar fuentes autorizadas de conocimiento y datos;
- agregar capa estructurada de Payroll Data & Analytics para consultas históricas autorizadas;
- ampliar validaciones por país mediante engines especializados.

### Largo plazo

Evolucionar hacia una **AI Payroll Operations Platform** en la que el Agent pueda combinar tres fuentes controladas: conocimiento RAG, resultados del Validation Engine y una capa de datos/analytics estructurada. Esto permitiría preguntas ejecutivas y de optimización como historia de un empleado, gasto de overtime, gross-up, tendencias, recurrencia de excepciones, concentración por concepto y análisis de posibles causas, manteniendo una separación explícita entre hechos calculados e hipótesis.

## 10.5 Conclusión

El proyecto valida una idea central: en un dominio sensible como Payroll, una solución AI útil no debe reemplazar el determinismo, sino **orquestarlo y explicarlo**. El resultado es un PoC funcional, auditable y desplegado que conserva la autoridad de los cálculos en código, utiliza RAG para grounding, limita al LLM a tareas apropiadas, audita sus respuestas y mantiene a la persona en la decisión final.

---

# 11. Rúbrica de Evaluación - Autoevaluación

Esta sección no sustituye la evaluación del instructor; resume dónde se encuentra la evidencia del proyecto.

| Dimensión | Evidencia disponible |
|---|---|
| Solución funcional E2E | Cloud Run + smoke test real `TOOL_RAG`, HTTP 200 |
| Arquitectura y diseño | Separación Engine / RAG / Agent / Auditor / HITL documentada |
| Implementación técnica | Código modular, API, Streamlit, Docker, deployment package |
| Seguridad y ética | Synthetic-only, Secret Manager, `.env` ignorado, guardrails, HITL |
| Pruebas y validación | Suite offline, cobertura, RAG, Auditor, OOS, evaluación Gemini INCONCLUSIVE documentada |
| Observabilidad | trace_id, JSONL, Cloud Logging, trace real exportado |
| Documentación | README, documentación de checkpoints, deployment guide y este documento |
| Limitaciones | Declaradas explícitamente; no se presentan métricas no medidas como cumplidas |

---

# 12. Referencias y Bibliografía

Referencias técnicas internas del repositorio:

1. `README.md` - descripción, arquitectura, ejecución, QA y deployment.
2. `docs/CP1_REVIEW.md` - revisión del Validation Engine.
3. `docs/CP2_REVIEW.md` - revisión de Knowledge/RAG.
4. `docs/CP3_REVIEW.md` - revisión de Agent/Auditor.
5. `docs/CP4_REVIEW.md` - revisión de integración.
6. `docs/CP4_EVIDENCIA_FINAL.md` - evidencia final, evaluación y ejecución cloud.
7. `docs/DEPLOY_GCP.md` - estrategia y resultado del despliegue GCP.
8. `config/validation_rules.yaml` - reglas determinísticas del Engine.
9. `cp4_gemini_stratified.json` - evidencia de evaluación real estratificada.
10. `cp4_gemini_stratified_INCONCLUSIVE_2026-10-04.json` - cierre formal de evaluación inconclusa.
11. Documentación OpenAPI generada por FastAPI en runtime.

---

# Anexos

## Anexo A - Evidencia E2E principal

- Pregunta: `¿Por qué falló EMP024?`
- Ruta: `TOOL_RAG`
- Trace: `TRACE-4f596f6a`
- HTTP: `200`
- Evidencia exportada: `TRACE-4f596f6a_TOOL_RAG_SUCCESS.json` / `successful_tool_rag_trace.json`.

## Anexo B - Comandos principales de ejecución local

```bash
python -m pytest -m "not eval" -q
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
python -m streamlit run app/web/streamlit_app.py
```

## Anexo C - Deployment

El paquete incluye `Dockerfile`, `deploy/start.sh`, `.dockerignore`, `.gcloudignore` y pruebas específicas de deployment. La guía reproducible se encuentra en `docs/DEPLOY_GCP.md`.

## Anexo D - Declaración de autoría y uso de AI

El proyecto fue desarrollado como trabajo académico con apoyo de herramientas de AI para ideación, revisión, documentación y asistencia técnica. Las decisiones de arquitectura, definición del caso de uso, validación de resultados y entrega final permanecen bajo responsabilidad de la participante. El proyecto no incorpora información real o confidencial de empleadores, empleados o sistemas productivos.
