# Despliegue en Google Cloud Run — PoC académica

**Proyecto:** AI Payroll Operations & Validation Agent (PoC académica, **solo datos sintéticos**)
**Decisiones:** D1 (un solo servicio de Cloud Run), D2 (hoy se prioriza el demo desplegado; no se corre otra evaluación con Gemini), D3 (Pam/Zury verifican la facturación en GCP antes del despliegue).
**Alcance:** empaquetado y despliegue. **No cambia** `app/`, la arquitectura aprobada ni el comportamiento.

---

## 1. Topología (D1): simplificación consciente para el PoC

```
Internet ──HTTPS──▶ Cloud Run: payroll-agent (1 contenedor, máx. 1 instancia)
                     │
                     ├─ Streamlit UI   0.0.0.0:$PORT        ← único puerto público
                     │      │ HTTP interno (API_BASE_URL=http://127.0.0.1:8000, D10)
                     │      ▼
                     └─ FastAPI/uvicorn 127.0.0.1:8000       ← interno, no expuesto
                              │
                              ├─ Validation Tool → corrida sintética 2026-09 (dentro de la imagen)
                              ├─ RAG → índice Gemini (opcional) / índice fake (respaldo)
                              └─ Gemini API (texto + embeddings) ← GEMINI_API_KEY desde Secret Manager
```

- **Se mantiene la arquitectura:** la UI solo habla con la API por HTTP. La API no tiene URL pública, así que `/chat`, `/validation` y `/documents/ingest` no son accesibles desde internet.
- **Simplificación respecto al plan de CP5:** el plan proponía dos servicios, con la API privada por IAM. Para el demo académico se usa **un solo servicio**. Así no hacen falta tokens de identidad ni cambios en `app/`.
- **Una sola instancia (`--max-instances 1`):** las sesiones de conversación viven en memoria (D8) y además protege la cuota de Gemini.
- **Afinidad de sesión (`--session-affinity`):** Streamlit mantiene una conexión WebSocket por usuario.
- **Región:** `us-central1`.
- **Acceso público** solo durante la ventana del demo académico (sección 7).

## 2. Qué contiene la imagen y qué no

| Incluido | Excluido (`.dockerignore` / `.gcloudignore`) |
|---|---|
| `app/`, `config/`, `knowledge/` (documentos sintéticos), `scripts/`, `.streamlit/`, `deploy/` | `.env`, `.env.*`, llaves y credenciales |
| `data/synthetic_payroll/` (entradas sintéticas) | `.git`, `.venv`, cachés |
| Corrida de validación 2026-09, **generada en el build** (Engine determinista) | `logs/`, `*.jsonl`, `*.zip`, reportes de evaluación (`cp*_gemini*.json`, `eval*.json`) |
| Índice **fake**, generado en el build (respaldo sin credenciales) | Corridas locales (`data/validation_results/*.json`) e índice fake local |
| Índice **Gemini**, solo si existe en `data/vector_index/gemini/` antes del despliegue | `tests/`, `docs/`, `README.md` |

**Sin secretos:**
- `GEMINI_API_KEY` **nunca** está en la imagen ni en el Dockerfile. Cloud Run la inyecta al arrancar desde Secret Manager.
- La imagen corre con un usuario sin privilegios (`appuser`).
- Los logs salen por **stdout** como JSON y llegan a Cloud Logging. El archivo opcional va a `/tmp/agent.jsonl`, que es efímero.

**Verificación en el build:** si existe un índice Gemini y no corresponde a `knowledge/` (está desactualizado), **el build falla**. Una imagen inconsistente no llega a Cloud Run.

## 3. El índice Gemini, sin exponer secretos

El índice contiene solo el texto de los documentos sintéticos, los vectores y metadatos (modelo, dimensiones, huella del conocimiento). **No contiene la API key.**

**Opción A (recomendada): índice Gemini generado en local**
```bash
# En tu máquina, desde la carpeta del proyecto, con tu .env local (que NO se sube):
python scripts/ingest_knowledge.py --provider gemini
# Comprueba que el índice no contiene la key:
grep -c "AIza" data/vector_index/gemini/index.json     # debe imprimir 0
```
- Hace 1 solicitud de **embeddings** (`gemini-embedding-001`), un modelo con su propia cuota, distinta de la de generación.
- Si el índice de Gemini ya existe y `knowledge/` no cambió, **no hace falta regenerarlo**.

**Opción B (sin índice Gemini):** se despliega con `EMBEDDINGS_PROVIDER=fake`. El RAG usa el índice fake incluido en la imagen y el LLM sigue siendo Gemini. La búsqueda documental es de menor calidad, pero funciona.

## 4. Requisitos previos (Pam/Zury)

1. **Proyecto de GCP y facturación (D3):** Cloud Run, Cloud Build y Artifact Registry requieren una cuenta de facturación vinculada al proyecto, aunque el uso sea mínimo.
   **Antes de vincularla, verifiquen en AI Studio cómo afecta al nivel y la cuota de Gemini** si la API key pertenece a ese mismo proyecto. No asumimos ningún cambio de plan.
2. **Dónde correr los comandos:**
   - **Cloud Shell** (recomendado: ya tiene `gcloud`). Suban el proyecto como zip **sin `.env`**, incluyendo `data/vector_index/gemini/` si usan la opción A.
   - **O** el **gcloud CLI** en su laptop.
3. Permisos: Owner o Editor en el proyecto.

## 5. Pasos exactos de despliegue (bash / Cloud Shell)

```bash
# 0. Variables
export PROJECT_ID="<id-del-proyecto>"
export REGION="us-central1"
export SERVICE="payroll-agent"
gcloud config set project "$PROJECT_ID"

# 1. APIs necesarias
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com logging.googleapis.com

# 2. Secreto: la key se escribe sin eco y no queda en el historial
read -s -p "GEMINI_API_KEY: " GEMINI_KEY; echo
printf "%s" "$GEMINI_KEY" | gcloud secrets create gemini-api-key --replication-policy=automatic --data-file=-
unset GEMINI_KEY

# 3. Permiso de lectura del secreto para la cuenta de servicio de Cloud Run (la predeterminada)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 4. (Opción A) Confirmar que el índice Gemini está en la carpeta que se va a subir
ls data/vector_index/gemini/index.json

# 5. Build + despliegue desde el código (Cloud Build usa el Dockerfile)
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --min-instances 0 \
  --max-instances 1 \
  --session-affinity \
  --memory 1Gi \
  --cpu 1 \
  --timeout 3600 \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars LLM_PROVIDER=gemini,EMBEDDINGS_PROVIDER=gemini,GEMINI_MODEL=gemini-3.8-flash,GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001,LOG_LEVEL=INFO
```

Notas del paso 5:
- La primera vez, `gcloud` pide crear el repositorio de Artifact Registry `cloud-run-source-deploy`: respondan **Y**.
- `--timeout 3600` es la duración máxima de una conexión. Así la conexión de Streamlit no se corta cada 5 minutos durante la grabación.
- Opción B: usen `EMBEDDINGS_PROVIDER=fake` en `--set-env-vars`.
- Durante la grabación, `--min-instances 1` evita el arranque en frío, pero mantiene la instancia encendida (costo). Después vuelvan a 0.
- PowerShell: reemplacen `\` al final de línea por `` ` `` y `export VAR=...` por `$env:VAR="..."`. En el paso 2 usen Cloud Shell, para no dejar la key en el historial.

## 6. Verificación después del despliegue

| Chequeo | Cómo | Resultado esperado |
|---|---|---|
| URL | `gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)'` | `https://payroll-agent-….run.app` |
| UI y salud | Abrir la URL. Barra lateral → "Estado del sistema" (consulta `GET /health` de la API interna) | **Operando**; corridas, Agente, índice y LLM en `ok` |
| Engine | Dashboard | 90 validaciones · 76 PASS · 14 FAIL |
| Agent | Una pregunta de ejemplo de cada ruta | Ruta, respuesta, fuentes y aviso de decisión humana |
| API no pública | Solo existe la URL de Streamlit; no hay URL de la API | La API no es accesible desde internet |
| Logs | Cloud Logging, filtro de abajo con el `trace_id` que aparece en "Detalles técnicos" | `request_received` → `llm_called ok=true` → `response_completed` |

```
resource.type="cloud_run_revision"
resource.labels.service_name="payroll-agent"
jsonPayload.trace_id="TRACE-xxxxxxxx"
```

**Cuota de Gemini durante el demo (D2):** el free tier tiene 20 solicitudes por día para `gemini-3.8-flash`. Costo por pregunta:

| Ruta | Solicitudes |
|---|---|
| Fuera de alcance por regla ("Aprueba la nómina") | 0 |
| Engine | 1 |
| Aclaración | 1 |
| Documentación | 2 |
| Engine + documentación | 2 |

Un recorrido de las 5 rutas usa ≈ 6–8 solicitudes. Planeen las preguntas del video y no hagan pruebas de más. Si la cuota se agota, la app sigue funcionando con el respaldo determinista y muestra el aviso ⚠️ "LLM no disponible".

## 7. Acceso público solo para el demo, y limpieza

- `--allow-unauthenticated` deja la UI pública. Es solo para el demo académico, con datos sintéticos y una instancia como máximo.
- Después de la evaluación, cierren el acceso o borren el servicio:
  ```bash
  gcloud run services remove-iam-policy-binding "$SERVICE" --region "$REGION" --member=allUsers --role=roles/run.invoker
  # o
  gcloud run services delete "$SERVICE" --region "$REGION"
  ```
- Recomendado: una alerta de presupuesto en Billing.

## 8. Modos de respaldo (sin redesplegar código)

| Modo | Variables | Cuándo |
|---|---|---|
| A: Gemini + índice Gemini | `LLM_PROVIDER=gemini`, `EMBEDDINGS_PROVIDER=gemini` | Normal (requiere el índice Gemini en la imagen) |
| B: Gemini + índice fake | `LLM_PROVIDER=gemini`, `EMBEDDINGS_PROVIDER=fake` | Sin índice Gemini |
| C: todo fake, sin Gemini | `LLM_PROVIDER=fake`, `EMBEDDINGS_PROVIDER=fake` | Sin key o sin cuota. La UI muestra el proveedor activo |

```bash
gcloud run services update "$SERVICE" --region "$REGION" --update-env-vars LLM_PROVIDER=fake,EMBEDDINGS_PROVIDER=fake
```

## 9. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El build falla en "Gemini index … stale" | El índice no corresponde a `knowledge/` | Regenerarlo (opción A) o quitar `data/vector_index/gemini/` (opción B) |
| El build falla por permisos de la cuenta de servicio | En proyectos nuevos, Cloud Build usa la cuenta predeterminada de Compute | Otorgar `roles/run.builder` a `${PROJECT_NUMBER}-compute@developer.gserviceaccount.com` y repetir |
| La revisión no arranca | Error al iniciar | Cloud Run → Logs: buscar líneas `[start]` |
| Estado "Degradado", índice `missing` | Se usó `EMBEDDINGS_PROVIDER=gemini` sin índice Gemini en la imagen | Modo B o redesplegar con el índice |
| "Agente: unavailable" con un mensaje de `GEMINI_MODEL` | Variable mal escrita (F6b) | Corregir `--set-env-vars` |
| Aviso ⚠️ "LLM no disponible" | Cuota de Gemini (429) o disponibilidad (503) | Esperar el reinicio de la cuota o usar el modo C |
| `allUsers` no permitido | Política de la organización | Usar un proyecto personal o `gcloud run services proxy` |

## 10. Limitaciones declaradas del despliegue académico

- **Un servicio y una instancia, con sesiones en memoria:** un reinicio borra las conversaciones. Es suficiente para el demo, no para producción.
- **La API no tiene autenticación propia:** está protegida por no estar expuesta (solo `127.0.0.1`).
- **La evidencia de evaluación con Gemini real sigue `INCONCLUSIVE` por la cuota diaria (D2).** Está documentada en `CP4_EVIDENCIA_FINAL.md`. La evaluación de 56 casos con Gemini queda para CP5 o para cuando haya más cuota.
- **Solo datos sintéticos.** Sin datos de empleados, empresas ni sistemas reales.


---

## 11. Resultado real del despliegue — 4 de octubre de 2026

El procedimiento documentado en esta guía fue ejecutado exitosamente en Google Cloud Platform.

### Configuración desplegada

| Elemento | Resultado |
|---|---|
| Servicio | `payroll-agent` |
| Plataforma | Google Cloud Run |
| Región | `us-central1` |
| Revisión | `payroll-agent-00001-5pd` |
| Tráfico | 100 % |
| Máximo de instancias | 1 |
| Gestión de secreto | Google Secret Manager |
| LLM | Gemini |
| Embeddings | Gemini |
| Estado del dashboard | Operativo |

URL del PoC:

`https://payroll-agent-190772421839.us-central1.run.app`

### Smoke test end-to-end

Se realizó una prueba controlada desde la aplicación desplegada con la pregunta:

`¿Por qué falló EMP024?`

Resultado:

- Ruta final: `TOOL_RAG`
- Trace ID: `TRACE-4f596f6a`
- Intent: `validation_explanation`
- Employee ID: `EMP024`
- Resultado encontrado por el Engine: `true`
- Validaciones FAIL: `1`
- HTTP status: `200`

Cloud Logging confirmó la cadena de ejecución:

`request_received → llm_called → intent_identified → tool_called → engine_result → rag_retrieved → llm_called → auditor_result → route_decided → response_completed`

Por lo tanto, el smoke test verificó de forma integrada el flujo:

`Usuario → Agent/LLM → Validation Engine → RAG → LLM → Auditor → respuesta`

Esta prueba confirma el funcionamiento end-to-end del PoC desplegado. No sustituye la evaluación estadística completa del modelo.

### Nota sobre la evaluación de Gemini

La evaluación estratificada ejecutada previamente permanece clasificada como `INCONCLUSIVE` debido a errores de proveedor/cuota durante esa corrida. El resultado no fue reinterpretado después de habilitar el entorno pagado.

El smoke test exitoso posterior demuestra funcionamiento integrado en cloud, pero no se utiliza para afirmar una tasa estadística de calidad de Gemini.

La evidencia detallada se conserva en `docs/CP4_EVIDENCIA_FINAL.md`.