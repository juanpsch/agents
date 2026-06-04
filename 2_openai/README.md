# Automated SDR — Sistema de Ventas con Agentes de IA

## Qué construimos

Tomamos el ejercicio del notebook `2_lab2.ipynb` (un sistema básico de generación de cold emails con el OpenAI Agents SDK) y lo convertimos en un programa productivo con conversación continua. El sistema tiene dos componentes: `2_lab2.py`, que orquesta la generación y envío del email inicial, y `webhook_server.py`, un servidor FastAPI que recibe las respuestas de los prospects y las contesta automáticamente usando un agente de IA.

## Arquitectura

```
python 2_lab2.py
       │
       ▼
 Sales Manager Agent
 ┌─────────────────────────────────────┐
 │  sales_agent1 (profesional)         │  ← 3 borradores en paralelo
 │  sales_agent2 (humorístico)         │
 │  sales_agent3 (conciso)             │
 │         │                           │
 │   Evalúa y elige el mejor           │
 │         │                           │
 │   email_manager tool                │
 │   ┌─────────────────────┐           │
 │   │ subject_writer      │           │
 │   │ html_converter      │           │
 │   │ send_html_email     │           │
 │   └─────────────────────┘           │
 └─────────────────────────────────────┘
       │
       │  FROM: alice@dynqf.es
       │  Reply-To: alice@reply.dynqf.es
       ▼
  Prospect recibe el cold email
       │
       │  Prospect responde
       ▼
  alice@reply.dynqf.es
  (MX record → mx.sendgrid.net)
       │
       ▼
  SendGrid Inbound Parse
       │  POST multipart/form-data
       ▼
  ngrok tunnel
       │
       ▼
  webhook_server.py  (FastAPI, puerto 8000)
  ┌────────────────────────────────────────┐
  │  Extrae texto del prospect             │
  │  Recupera historial de conversación    │
  │  SDR Follow-up Agent (gpt-4o-mini)     │
  │  Genera respuesta contextual           │
  │  Envía reply via SendGrid              │
  │  Guarda historial → próxima respuesta  │
  └────────────────────────────────────────┘
       │
       ▼
  Prospect recibe respuesta del SDR
  (con Reply-To: alice@reply.dynqf.es → loop continúa)
```

## Cómo funciona

El punto de entrada es `2_lab2.py`. Cuando se ejecuta, el **Sales Manager** (agente orquestador) llama en paralelo a tres agentes de ventas con estilos distintos — profesional, humorístico y conciso — para que cada uno genere un borrador del cold email. Luego evalúa los tres y elige el mejor. Ese borrador se pasa al **Email Manager** como tool, que a su vez llama a dos agentes auxiliares: uno que escribe el asunto y otro que convierte el cuerpo a HTML. Finalmente llama a `send_html_email`, que envía el email via SendGrid con `FROM: alice@dynqf.es` y `Reply-To: alice@reply.dynqf.es`.

Cuando el prospect responde, su cliente de email dirige el reply a `alice@reply.dynqf.es` gracias al header `Reply-To`. El MX record de ese subdominio apunta a `mx.sendgrid.net`, así que SendGrid intercepta el email y hace un `POST` al webhook configurado en **Inbound Parse**, que en desarrollo llega via ngrok al `webhook_server.py`. El servidor extrae el texto nuevo del prospect (descartando las citas del hilo anterior), lo agrega al historial de conversación en memoria, y lo pasa al **SDR Follow-up Agent**, que genera una respuesta contextual con el objetivo de avanzar hacia una llamada de demo. Esa respuesta se envía de vuelta al prospect, también con `Reply-To: alice@reply.dynqf.es`, cerrando el loop y permitiendo que la conversación continúe indefinidamente.

## Setup requerido

| Componente | Configuración |
|-----------|---------------|
| DNS | MX record: `reply.dynqf.es` → `mx.sendgrid.net` (prioridad 10) |
| SendGrid | Domain Authentication para `dynqf.es` + Inbound Parse para `reply.dynqf.es` |
| ngrok | `ngrok http 8000` → URL pública en SendGrid Inbound Parse |
| `.env` | `SDR_FROM_EMAIL`, `SDR_REPLY_TO`, `SDR_NAME`, `SENDGRID_API_KEY`, `OPENAI_API_KEY` |

## Cómo ejecutar

```bash
# Terminal 1 — webhook server
python webhook_server.py

# Terminal 2 — ngrok (expone el puerto al internet)
ngrok http 8000

# Terminal 3 — enviar el cold email inicial
python 2_lab2.py
```

## Problemas que tuvimos que corregir

| Problema | Causa | Solución |
|----------|-------|----------|
| `ModuleNotFoundError: No module named 'sendgrid'` | Dependencias no instaladas | `pip install sendgrid openai-agents` |
| Warning: tool name `transfer_to_Email Manager` inválido | El SDK no acepta espacios en nombres de agentes | Renombrar a `Email_Manager` |
| El `Email_Manager` respondía con texto en lugar de llamar sus tools | Con handoff, el cuerpo del email quedaba enterrado en el historial y el LLM no lo procesaba | Cambiar de handoff a `as_tool()` para pasarle el email explícitamente como argumento |
| SendGrid devolvía `HTTP 403 Forbidden` al enviar | El dominio autenticado es `dynqf.es` pero se intentaba enviar FROM `alice@reply.dynqf.es` (subdominio no autorizado) | Separar FROM (`alice@dynqf.es`) de Reply-To (`alice@reply.dynqf.es`) |
| El webhook no se disparaba al responder el email | El email respondido fue enviado antes del fix del `.env`, por lo que no tenía el `Reply-To` correcto | Reenviar un cold email nuevo con la configuración corregida |

## Patrones de diseño usados

- **Parallelization** — los 3 agentes de ventas corren simultáneamente
- **Orchestrator / Subagents** — el Sales Manager coordina a los demás agentes como tools
- **Agents as Tools** — cada agente se expone como función invocable por el orquestador
- **Tool use** — `send_html_email` es una función Python que el LLM puede llamar directamente
- **Human in the loop** (implícito) — el prospect es el humano que guía la conversación
