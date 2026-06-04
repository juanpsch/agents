# =============================================================================
# WEBHOOK SERVER — SDR Conversación Continua
#
# Este servidor recibe los emails de respuesta de los prospects via
# SendGrid Inbound Parse, genera una respuesta con el SDR agent, y la envía.
#
# SETUP REQUERIDO (una sola vez):
#
# 1. DOMINIO
#    Necesitás un dominio que controles (ej: tudominio.com).
#    Creá un subdominio dedicado para recibir respuestas, ej: reply.tudominio.com
#
# 2. MX RECORD
#    En tu proveedor de DNS, agregá este MX record para el subdominio:
#      Host:     reply.tudominio.com
#      Value:    mx.sendgrid.net
#      Priority: 10
#    Esto hace que los emails enviados a *@reply.tudominio.com
#    los reciba SendGrid en lugar de tu proveedor de email habitual.
#
# 3. SENDGRID — INBOUND PARSE
#    En tu cuenta de SendGrid:
#    Settings → Inbound Parse → Add Host & URL
#      Hostname: reply.tudominio.com
#      URL:      https://TU-NGROK-URL/webhook/reply   (ver paso 5)
#    Opcionalmente activa "Send Raw" para recibir el MIME completo.
#
# 4. VARIABLES DE ENTORNO (.env)
#    Agrega estas líneas a tu .env:
#      SENDGRID_API_KEY=xxxx
#      REPLY_DOMAIN=reply.tudominio.com          # subdominio con MX apuntado
#      SDR_FROM_EMAIL=alice@reply.tudominio.com  # dirección desde la que envía el SDR
#      SDR_NAME=Alice                            # nombre del SDR
#
# 5. NGROK (para desarrollo local)
#    Instalá ngrok: https://ngrok.com/download
#    En una terminal separada, corré:
#      ngrok http 8000
#    Ngrok te dará una URL pública tipo: https://abc123.ngrok.io
#    Esa URL va en el campo URL del paso 3 (con /webhook/reply al final).
#    IMPORTANTE: cada vez que reiniciás ngrok cambia la URL → actualizá SendGrid.
#
# 6. CORRER EL SERVIDOR
#    pip install fastapi uvicorn python-multipart
#    python webhook_server.py
#
# FLUJO COMPLETO:
#    2_lab2.py envía cold email con Reply-To: alice@reply.tudominio.com
#    → Prospect responde
#    → Su cliente de email envía a alice@reply.tudominio.com
#    → MX record redirige a mx.sendgrid.net
#    → SendGrid parsea y hace POST a /webhook/reply
#    → Este servidor extrae el texto, corre el SDR agent
#    → SDR agent genera respuesta y la enviamos de vuelta al prospect
# =============================================================================

import asyncio
import logging
import os
import re
from email import message_from_string
from typing import Optional

import sendgrid
import uvicorn
from agents import Agent, Runner, trace
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse
from sendgrid.helpers.mail import Content, Email, Mail, ReplyTo, To

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="SDR Webhook Server")

# Conversación en memoria: { email_del_prospect: [{"role": "user"|"assistant", "content": str}] }
# Para producción reemplazá esto con Redis o una base de datos.
conversation_history: dict[str, list[dict]] = {}

# Variables de entorno con defaults para desarrollo
SDR_FROM_EMAIL = os.environ.get("SDR_FROM_EMAIL") or os.environ.get("SENDER_VERIFIED_EMAIL")
SDR_NAME = os.environ.get("SDR_NAME", "Alice")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")

# =============================================================================
# AGENTE SDR DE SEGUIMIENTO
# Este agente maneja la conversación de vuelta con el prospect.
# Recibe el historial completo de la conversación para mantener contexto.
# =============================================================================

FOLLOWUP_INSTRUCTIONS = f"""
You are {SDR_NAME}, an SDR (Sales Development Representative) at ComplAI.
ComplAI is a SaaS tool for SOC2 compliance and audit preparation, powered by AI.

You are continuing an email conversation with a prospect who replied to your cold outreach.
Your goal is to:
- Understand their interest or objections
- Answer questions clearly and concisely
- Move toward scheduling a 15-minute discovery call
- Be conversational and helpful, never pushy or salesy

Rules:
- Keep replies to 2–4 short paragraphs maximum
- Do not repeat the original pitch — they already read it
- If they ask something you don't know, offer to connect them with a specialist
- Sign off as {SDR_NAME} from ComplAI
- Write in plain text, no markdown
"""

sdr_followup_agent = Agent(
    name="SDR Follow-up Agent",
    instructions=FOLLOWUP_INSTRUCTIONS,
    model="gpt-4o-mini",
)


# =============================================================================
# UTILIDADES
# =============================================================================

def extract_sender_address(from_header: str) -> str:
    """Extrae solo la dirección de email del header From (puede venir como 'Nombre <email>')."""
    match = re.search(r"<(.+?)>", from_header)
    if match:
        return match.group(1).strip()
    return from_header.strip()


def extract_reply_body(raw_mime: str) -> str:
    """
    Parsea el MIME del email y extrae solo el texto nuevo del prospect,
    descartando las líneas de texto citado (que empiezan con '>') y
    los encabezados de respuesta ('On ... wrote:').
    """
    msg = message_from_string(raw_mime)

    body = ""
    if msg.is_multipart():
        # Busca la primera parte text/plain
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")

    # Elimina líneas citadas y encabezados de respuesta estándar
    clean_lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        # "On Mon, 2 Jun 2026 Alice wrote:" — encabezado de cita estándar
        if re.match(r"^On .+ wrote:$", stripped):
            break  # Todo lo que sigue es cita
        clean_lines.append(line)

    return "\n".join(clean_lines).strip()


def extract_fields_from_raw(raw_mime: str) -> tuple[str, str, str]:
    """Extrae from, subject y body del MIME crudo."""
    msg = message_from_string(raw_mime)
    sender = extract_sender_address(msg.get("from", ""))
    subject = msg.get("subject", "Re: Sales email")
    body = extract_reply_body(raw_mime)
    return sender, subject, body


SDR_REPLY_TO = os.environ.get("SDR_REPLY_TO") or os.environ.get("SENDER_VERIFIED_EMAIL")


def send_reply_email(to_address: str, subject: str, body: str) -> None:
    """Envía la respuesta del SDR al prospect via SendGrid."""
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    from_email = Email(SDR_FROM_EMAIL, SDR_NAME)
    to_email = To(to_address)

    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    content = Content("text/plain", body)
    mail = Mail(from_email, to_email, reply_subject, content)
    # Reply-To apunta al subdominio con MX para que cada respuesta del prospect
    # siga llegando al webhook y la conversación continúe indefinidamente
    mail.reply_to = ReplyTo(SDR_REPLY_TO, SDR_NAME)
    response = sg.client.mail.send.post(request_body=mail.get())
    log.info("Email enviado a %s — status %s", to_address, response.status_code)


# =============================================================================
# ENDPOINT WEBHOOK
# SendGrid hace POST aquí cada vez que llega un email a reply.tudominio.com
# =============================================================================

@app.post("/webhook/reply")
async def handle_reply(
    request: Request,
    # Modo "Send Raw" activado en SendGrid → llega el MIME completo en el campo "email"
    email: Optional[str] = Form(None),
    # Modo por defecto → SendGrid parsea y manda campos individuales
    from_field: Optional[str] = Form(None, alias="from"),
    subject: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
):
    # --- Extraer datos del email recibido ---
    if email:
        # Modo raw MIME
        sender, subject_parsed, reply_text = extract_fields_from_raw(email)
    else:
        # Modo campos individuales
        sender = extract_sender_address(from_field or "")
        subject_parsed = subject or "Re: Sales email"
        reply_text = (text or "").strip()

    log.info("Webhook recibido de: %s | Asunto: %s", sender, subject_parsed)

    if not reply_text or not sender:
        log.warning("Email vacío o sin remitente — ignorando")
        # Devolvemos 200 de todas formas para que SendGrid no reintente
        return JSONResponse({"status": "ignored"}, status_code=200)

    # --- Recuperar o inicializar historial de conversación ---
    history = conversation_history.get(sender, [])
    history.append({"role": "user", "content": reply_text})

    # Construimos el prompt con el historial completo para que el agente tenga contexto
    history_text = "\n\n---\n\n".join(
        f"{'Prospect' if m['role'] == 'user' else SDR_NAME}: {m['content']}"
        for m in history
    )
    prompt = (
        f"Here is the full email conversation so far:\n\n{history_text}\n\n"
        f"Write your reply to the prospect's latest message."
    )

    # --- Correr el SDR agent ---
    log.info("Corriendo SDR agent para %s...", sender)
    with trace(f"SDR Reply to {sender}"):
        result = await Runner.run(sdr_followup_agent, prompt)

    agent_reply = result.final_output

    # Guardamos la respuesta del agente en el historial
    history.append({"role": "assistant", "content": agent_reply})
    conversation_history[sender] = history

    log.info("Respuesta generada:\n%s", agent_reply)

    # --- Enviar el reply ---
    send_reply_email(sender, subject_parsed, agent_reply)

    return JSONResponse({"status": "success"}, status_code=200)


@app.get("/health")
async def health():
    """Endpoint para verificar que el servidor está corriendo."""
    return {"status": "ok", "conversations_active": len(conversation_history)}


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    log.info("Iniciando SDR Webhook Server en http://0.0.0.0:8000")
    log.info("Webhook URL: http://0.0.0.0:8000/webhook/reply")
    log.info("Health check: http://0.0.0.0:8000/health")
    uvicorn.run(app, host="0.0.0.0", port=8000)
