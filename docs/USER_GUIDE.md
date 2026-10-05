# Manual de Usuario
## AI Payroll Operations & Validation Agent

**Tipo:** PoC académico  
**Datos:** 100% sintéticos  
**Decisión final:** Human-in-the-Loop

## 1. Objetivo
La aplicación ayuda a consultar validaciones de nómina, investigar excepciones y recuperar contexto documental mediante Validation Engine, RAG, Gemini, Agent/Orchestrator y Auditor.

**LLM comprende → Código decide → Engine valida → RAG fundamenta → Auditor controla → Humano aprueba.**

No sustituye a un sistema de nómina ni a la aprobación humana.

## 2. Acceso
Abrir la URL del ambiente desplegado o iniciar Streamlit localmente. El despliegue académico verificado se ejecuta en Google Cloud Run.

## 3. Pantalla principal
La interfaz puede mostrar:
- Estado general del sistema.
- Estado de validaciones.
- Estado del agente.
- Estado del índice de conocimiento.
- Estado del LLM.
- Resumen de validaciones sintéticas.
- Área de consulta en lenguaje natural.

## 4. Realizar una consulta
1. Abrir la aplicación.
2. Escribir una pregunta clara.
3. Incluir Employee ID o periodo cuando aplique.
4. Enviar la consulta.
5. Revisar ruta, resultado y evidencia.
6. Utilizar la respuesta como apoyo para investigación, nunca como aprobación automática.

## 5. Rutas del agente

### TOOL
Para hechos estructurados de validación.

Ejemplo:
```text
Muéstrame la validación de EMP024 para 2026-09.
```

El Validation Engine es la fuente autoritativa de Expected, Actual/Provider, Difference, Tolerance, PASS/FAIL, Exception y Reason Code.

### RAG
Para recuperar conocimiento documental.

Ejemplo:
```text
¿Qué regla documentada aplica a esta validación?
```

La respuesta se apoya en SOPs, reglas y documentación controlada.

### TOOL_RAG
Combina hechos determinísticos y contexto documental.

Ejemplo:
```text
¿Por qué falló EMP024?
```

Flujo: Engine → RAG → explicación LLM → Auditor → respuesta con evidencia.

### CLARIFY
Cuando falta información necesaria, el sistema solicita el dato en vez de asumirlo.

### OUT_OF_SCOPE
Para solicitudes fuera del alcance definido del PoC.

## 6. Interpretar resultados
**PASS:** el valor evaluado cumple la regla/tolerancia configurada.

**FAIL:** existe una diferencia o condición que requiere investigación. FAIL no significa automáticamente rechazar la nómina.

**Expected:** valor esperado según lógica determinística.

**Actual / Provider:** valor recibido para comparación.

**Difference:** diferencia evaluada.

**Tolerance:** margen permitido.

**Reason Code:** motivo determinístico asociado a la excepción.

## 7. Caso representativo EMP024
La consulta:
```text
¿Por qué falló EMP024?
```
puede activar `TOOL_RAG`. En el caso sintético utilizado en la demostración, el sistema identifica una excepción de net pay, combina hechos del Engine con documentación recuperada por RAG y mantiene la investigación/decisión final con el revisor humano.

## 8. Evidencia y trazabilidad
La observabilidad puede registrar:
```text
request_received
→ llm_called
→ intent_identified
→ tool_called
→ engine_result
→ rag_retrieved
→ auditor_result
→ route_decided
→ response_completed
```

Cada solicitud puede asociarse a un Trace ID para diferenciar hechos determinísticos, evidencia documental, generación LLM, controles del Auditor y errores del proveedor.

## 9. Ante una excepción
1. Revisar concepto.
2. Revisar Expected, Actual, Difference y Tolerance.
3. Revisar Reason Code.
4. Consultar explicación/documentación.
5. Confirmar evidencia.
6. Investigar causa.
7. Escalar/corregir mediante el proceso autorizado.
8. Mantener aprobación final humana.

## 10. Si Gemini no está disponible
Gemini puede presentar errores de cuota, saldo o disponibilidad. No interpretar una falla del proveedor como PASS/FAIL. Revisar el fallback, reintentar cuando corresponda y utilizar únicamente hechos determinísticos disponibles.

La arquitectura evita convertir una falla del proveedor en un cálculo de nómina inventado.

## 11. Buenas prácticas
Consultas recomendadas:
```text
¿Por qué falló EMP024?
Muéstrame la validación de EMP024 para 2026-09.
¿Qué regla documentada aplica a esta validación?
```

Solicitudes fuera del propósito del PoC:
```text
Aprueba el payroll por mí.
Modifica el salario del empleado.
```

## 12. Human-in-the-Loop
El humano conserva responsabilidad sobre investigación, interpretación, confirmación de fuentes, decisiones de corrección, acciones productivas y aprobación final.

## 13. Seguridad
No:
- Introducir datos reales/confidenciales.
- Compartir API keys.
- Exponer `.env`.
- Copiar credenciales a prompts.
- Interpretar una respuesta generativa como autorización de pago.

## 14. Limitaciones conocidas
- Datos sintéticos.
- No es un sistema productivo de nómina.
- Sin identidad empresarial/SSO.
- Human-in-the-Loop obligatorio.
- Dependencia del proveedor para capacidades LLM.
- Sin SLA productivo declarado.
- Sin costo estadístico por 1,000 consultas declarado.
- Topología Cloud Run académica.

La evaluación estratificada con Gemini real permanece documentada como **INCONCLUSIVE** por errores/limitaciones del proveedor durante la ejecución; se mantiene separada de las pruebas determinísticas.

## 15. Evolución futura
- Motores por país.
- Analítica histórica estructurada.
- Tendencias, estacionalidad y patrones.
- Excepciones recurrentes.
- Consultas ejecutivas.
- Identidad/autorización empresarial.
- Servicios escalables.
- Plataforma global de Payroll.

## 16. Documentación relacionada
- `README.md`
- `docs/PROJECT_DOCUMENTATION.md`
- `docs/INSTALLATION_GUIDE.md`
- `docs/DEPLOY_GCP.md`
- `docs/CP4_EVIDENCIA_FINAL.md`

**AI Payroll Operations & Validation Agent — By Pam GR**
