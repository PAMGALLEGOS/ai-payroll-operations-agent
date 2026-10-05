# Manual de Instalación
## AI Payroll Operations & Validation Agent

**Tipo:** PoC académico AI/LLM  
**Datos:** 100% sintéticos  
**Stack:** Python · FastAPI · Streamlit · Validation Engine · RAG · Gemini · Auditor  
**Despliegue validado:** Google Cloud Run

## 1. Objetivo
Este manual describe cómo instalar, ejecutar y validar el proyecto. La arquitectura mantiene una separación explícita: **LLM comprende → Código decide → Engine valida → RAG fundamenta → Auditor controla → Humano aprueba.** El LLM no es la fuente autoritativa de cálculos ni de PASS/FAIL.

## 2. Prerrequisitos
- Git.
- Python compatible (PoC validado localmente con Python 3.13; contenedor con Python 3.11).
- `pip`.
- Terminal PowerShell/CMD/Bash o equivalente.
- API key válida de Gemini para capacidades reales del proveedor.
- Internet para dependencias y Gemini.

Para GCP: proyecto con facturación habilitada, `gcloud`, Cloud Run, Cloud Build, Artifact Registry, Secret Manager y Cloud Logging.

## 3. Obtener el código
```bash
git clone https://github.com/PAMGALLEGOS/ai-payroll-operations-agent.git
cd ai-payroll-operations-agent
```

## 4. Crear entorno virtual
Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
```

## 5. Instalar dependencias
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Variables de entorno
Copiar `.env.example` a `.env` y completar únicamente las variables requeridas.

Ejemplo conceptual:
```text
LLM_PROVIDER=gemini
EMBEDDINGS_PROVIDER=gemini
GEMINI_MODEL=gemini-3.8-flash
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
GEMINI_API_KEY=<SU_CLAVE>
LOG_LEVEL=INFO
```

**Nunca subir `.env`, API keys o credenciales a Git.** En Cloud Run la clave debe suministrarse mediante Secret Manager.

## 7. Estructura principal
```text
app/
config/
data/
knowledge/
scripts/
tests/
docs/
deploy/
```

El PoC contiene Validation Engine determinístico, RAG, agente/orquestador, Auditor/guardrails, API FastAPI, UI Streamlit y observabilidad. No requiere datos reales de empleados.

## 8. Ejecutar pruebas
```bash
python -m pytest -m "not eval" -q
```

La suite del proyecto contiene 515 pruebas. La ejecución final local en Windows registró 514 PASS, 14 deseleccionadas y una prueba del paquete de despliegue que no pudo ejecutar validación Bash porque Bash no estaba instalado. Esta limitación es ambiental y está separada de la lógica de la aplicación.

## 9. Iniciar FastAPI
```bash
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Health check:
```text
http://127.0.0.1:8000/health
```

## 10. Iniciar Streamlit
En otra terminal con el entorno virtual activo:
```bash
python -m streamlit run app/web/streamlit_app.py
```

## 11. Validación básica
Confirmar:
1. `/health` responde.
2. Streamlit abre correctamente.
3. El dashboard muestra estado del sistema.
4. Los datos sintéticos están disponibles.
5. Una consulta estructurada recupera resultados del Validation Engine.
6. Con Gemini configurado, las rutas LLM/RAG pueden invocar al proveedor.
7. La observabilidad registra trazabilidad de solicitudes.

## 12. Docker
El repositorio incluye `Dockerfile`, `deploy/start.sh`, `.dockerignore` y `.gcloudignore`.

Topología del contenedor:
```text
Browser → Streamlit ($PORT) → FastAPI/Uvicorn (127.0.0.1:8000)
        → Agent → Validation Engine / RAG / Gemini → Auditor
```

## 13. Google Cloud Run
Despliegue académico verificado:
- Servicio: `payroll-agent`
- Región: `us-central1`
- Memoria: 1 GiB
- Máximo de instancias: 1
- Secret Manager para `GEMINI_API_KEY`
- Cloud Logging para logs

Ejemplo:
```bash
gcloud run deploy payroll-agent --source . --region us-central1 --allow-unauthenticated --port 8080 --max-instances 1 --session-affinity --memory 1Gi --timeout 3600 --set-secrets GEMINI_API_KEY=gemini-api-key:latest --set-env-vars LLM_PROVIDER=gemini,EMBEDDINGS_PROVIDER=gemini,GEMINI_MODEL=gemini-3.8-flash,GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001,LOG_LEVEL=INFO
```

Ver `docs/DEPLOY_GCP.md` para detalles adicionales.

## 14. Troubleshooting
**UI sin API:** confirmar que FastAPI esté activo y la URL de API sea correcta.

**Gemini 402/429/503:** revisar saldo, cuota, disponibilidad del modelo y credenciales. La aplicación incorpora manejo seguro de fallas para no inventar resultados determinísticos.

**Bash en Windows:** `deploy/start.sh` está diseñado para Linux; la ausencia de Bash puede afectar una prueba local específica, no la lógica del PoC.

**RAG sin resultados:** comprobar activos de conocimiento/índice y configuración del proveedor de embeddings.

## 15. Seguridad y alcance
- Usar únicamente datos sintéticos.
- No almacenar secretos en Git.
- No usar el LLM como calculadora autoritativa de nómina.
- No interpretar una respuesta como aprobación de Payroll.
- Mantener Human-in-the-Loop.

## 16. Documentación relacionada
- `README.md`
- `docs/PROJECT_DOCUMENTATION.md`
- `docs/DEPLOY_GCP.md`
- `docs/CP4_EVIDENCIA_FINAL.md`
- `docs/USER_GUIDE.md`

**AI Payroll Operations & Validation Agent — By Pam GR**
