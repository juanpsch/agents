# asyncio: permite correr código asíncrono (await/async) en Python estándar
# os: para leer variables de entorno (SENDGRID_API_KEY)
# Dict: anotación de tipo para el valor de retorno de las tools
import asyncio
import os
from typing import Dict

# sendgrid: cliente HTTP para enviar emails via la API de SendGrid
# agents: SDK de OpenAI para construir agentes — Agent define un agente,
#         Runner lo ejecuta, trace agrupa llamadas en un trace, function_tool
#         convierte una función Python en una tool que el LLM puede invocar
# load_dotenv: carga el archivo .env para que os.environ pueda leer las claves
import sendgrid
from agents import Agent, Runner, trace, function_tool
from dotenv import load_dotenv
from sendgrid.helpers.mail import Content, Email, Mail, ReplyTo, To

# Carga las variables del archivo .env (override=True fuerza la recarga
# aunque la variable ya exista en el entorno del sistema)
load_dotenv(override=True)

# FROM: dominio raíz autenticado en SendGrid (ej: alice@dynqf.es)
# REPLY_TO: subdominio con MX record → replies van al webhook (ej: alice@reply.dynqf.es)
# Son distintos: FROM necesita estar autenticado para enviar,
# REPLY_TO necesita tener MX apuntado a mx.sendgrid.net para recibir.
SDR_FROM_EMAIL = os.environ.get("SDR_FROM_EMAIL") or os.environ.get("SENDER_VERIFIED_EMAIL")
SDR_REPLY_TO   = os.environ.get("SDR_REPLY_TO") or os.environ.get("SENDER_VERIFIED_EMAIL")
SDR_NAME       = os.environ.get("SDR_NAME", "Alice")


# =============================================================================
# INSTRUCCIONES DE LOS AGENTES
# Cada string es el "system prompt" que define la personalidad y tarea
# de cada agente. El LLM los recibe como contexto antes de cualquier mensaje.
# =============================================================================

# Estilo formal — emails serios y profesionales
instructions1 = (
    "You are a sales agent working for ComplAI, "
    "a company that provides a SaaS tool for ensuring SOC2 compliance and preparing for audits, powered by AI. "
    "You write professional, serious cold emails."
)

# Estilo humorístico — emails entretenidos para aumentar la tasa de respuesta
instructions2 = (
    "You are a humorous, engaging sales agent working for ComplAI, "
    "a company that provides a SaaS tool for ensuring SOC2 compliance and preparing for audits, powered by AI. "
    "You write witty, engaging cold emails that are likely to get a response."
)

# Estilo conciso — emails cortos y directos al punto
instructions3 = (
    "You are a busy sales agent working for ComplAI, "
    "a company that provides a SaaS tool for ensuring SOC2 compliance and preparing for audits, powered by AI. "
    "You write concise, to the point cold emails."
)

# Agente especializado en escribir asuntos (subject) de email
subject_instructions = (
    "You can write a subject for a cold sales email. "
    "You are given a message and you need to write a subject for an email that is likely to get a response."
)

# Agente especializado en convertir texto plano/markdown a HTML bien formateado
html_instructions = (
    "You can convert a text email body to an HTML email body. "
    "You are given a text email body which might have some markdown "
    "and you need to convert it to an HTML email body with simple, clear, compelling layout and design."
)

# El Sales Manager es el agente orquestador. Sus instrucciones son deliberadamente
# detalladas porque debe coordinar a otros agentes en un orden específico:
# 1) generar 3 borradores → 2) elegir el mejor → 3) hacer handoff al emailer.
# Sin estas reglas explícitas el LLM podría saltarse pasos o enviar más de un email.
sales_manager_instructions = """
You are a Sales Manager at ComplAI. Your goal is to find the single best cold sales email using the sales_agent tools.

Follow these steps carefully:
1. Generate Drafts: Use all three sales_agent tools to generate three different email drafts. Do not proceed until all three drafts are ready.

2. Evaluate and Select: Review the drafts and choose the single best email using your judgment of which one is most effective.
You can use the tools multiple times if you're not satisfied with the results from the first try.

3. Send the winning email: Call the email_manager tool passing the FULL body of the winning email as input. The email_manager will handle subject, HTML formatting, and sending.

Crucial Rules:
- You must use the sales agent tools to generate the drafts — do not write them yourself.
- You must call email_manager exactly once with the complete email body — never more than once.
"""

# El Email Manager recibe el cuerpo del email ganador y lo procesa en tres pasos:
# subject_writer → html_converter → send_html_email
emailer_instructions = (
    "You are an email formatter and sender. "
    "You will receive the body of a cold sales email. You MUST always call all three tools in this exact order:\n"
    "1. Call subject_writer with the email body to generate a subject line.\n"
    "2. Call html_converter with the email body to convert it to HTML.\n"
    "3. Call send_html_email with the subject from step 1 and the HTML from step 2 to send the email.\n"
    "Do not skip any step. Do not respond with text until all three tools have been called and the email has been sent."
)


# =============================================================================
# TOOLS (herramientas)
# @function_tool convierte la función en un FunctionTool: genera automáticamente
# el JSON schema que el LLM necesita para saber cómo llamarla y qué parámetros
# pasarle. Sin el decorador, el agente no puede invocar la función.
# =============================================================================

@function_tool
def send_email(body: str) -> Dict[str, str]:
    """Send out an email with the given body to all sales prospects"""
    sg = sendgrid.SendGridAPIClient(api_key=os.environ.get("SENDGRID_API_KEY"))
    from_email = Email(SDR_FROM_EMAIL, SDR_NAME)
    to_email = To(os.environ.get("TO_EMAIL"))
    content = Content("text/plain", body)
    mail = Mail(from_email, to_email, "Sales email", content)
    # Reply-To igual que FROM → el reply del prospect va al webhook via MX
    mail.reply_to = ReplyTo(SDR_REPLY_TO, SDR_NAME)
    response = sg.client.mail.send.post(request_body=mail.get())
    print(f"[send_email] status={response.status_code} from={SDR_FROM_EMAIL}")
    return {"status": response.status_code}


@function_tool
def send_html_email(subject: str, html_body: str) -> Dict[str, str]:
    """Send out an email with the given subject and HTML body to all sales prospects"""
    sg = sendgrid.SendGridAPIClient(api_key=os.environ.get("SENDGRID_API_KEY"))
    from_email = Email(SDR_FROM_EMAIL, SDR_NAME)
    to_email = To(os.environ.get("TO_EMAIL"))
    # text/html en lugar de text/plain para que el cliente de email renderice el HTML
    content = Content("text/html", html_body)
    mail = Mail(from_email, to_email, subject, content)
    # Reply-To igual que FROM → el reply del prospect va al webhook via MX
    mail.reply_to = ReplyTo(SDR_REPLY_TO, SDR_NAME)
    response = sg.client.mail.send.post(request_body=mail.get())
    print(f"[send_html_email] status={response.status_code} from={SDR_FROM_EMAIL}")
    return {"status": response.status_code}


# =============================================================================
# AGENTES
# Cada Agent es un LLM con identidad, instrucciones y capacidades propias.
# Los agentes de ventas solo saben escribir emails — no tienen tools ni handoffs.
# =============================================================================

sales_agent1 = Agent(
    name="Professional Sales Agent",
    instructions=instructions1,
    model="gpt-4o-mini",
)

sales_agent2 = Agent(
    name="Engaging Sales Agent",
    instructions=instructions2,
    model="gpt-4o-mini",
)

sales_agent3 = Agent(
    name="Busy Sales Agent",
    instructions=instructions3,
    model="gpt-4o-mini",
)

# Agentes auxiliares para el pipeline de formato y envío
subject_writer = Agent(
    name="Email subject writer",
    instructions=subject_instructions,
    model="gpt-4o-mini",
)

html_converter = Agent(
    name="HTML email body converter",
    instructions=html_instructions,
    model="gpt-4o-mini",
)


# =============================================================================
# AGENTS AS TOOLS
# .as_tool() envuelve un agente como si fuera una función: cuando el orquestador
# llama a "sales_agent1", en realidad lanza un Runner.run() interno sobre ese
# agente y devuelve su output como resultado de la tool. El control vuelve
# al agente que lo llamó (a diferencia del handoff, donde el control se transfiere).
# =============================================================================

subject_tool = subject_writer.as_tool(
    tool_name="subject_writer",
    tool_description="Write a subject for a cold sales email",
)

html_tool = html_converter.as_tool(
    tool_name="html_converter",
    tool_description="Convert a text email body to an HTML email body",
)

# El emailer_agent usa sus 3 tools en secuencia.
# Se expone como tool (no handoff) para que el Sales Manager le pase
# el cuerpo del email explícitamente como argumento.
emailer_agent = Agent(
    name="Email_Manager",
    instructions=emailer_instructions,
    tools=[subject_tool, html_tool, send_html_email],
    model="gpt-4o-mini",
)

# Los 3 agentes de ventas se exponen como tools para el Sales Manager
tool1 = sales_agent1.as_tool(tool_name="sales_agent1", tool_description="Write a cold sales email")
tool2 = sales_agent2.as_tool(tool_name="sales_agent2", tool_description="Write a cold sales email")
tool3 = sales_agent3.as_tool(tool_name="sales_agent3", tool_description="Write a cold sales email")

# email_manager como tool: el Sales Manager le pasa el cuerpo del email ganador
# como input explícito, en lugar de depender del historial de conversación
email_manager_tool = emailer_agent.as_tool(
    tool_name="email_manager",
    tool_description="Format the email as HTML and send it. Pass the full email body as input.",
)

# El Sales Manager tiene las 4 tools: 3 para generar borradores + 1 para enviar
sales_manager = Agent(
    name="Sales Manager",
    instructions=sales_manager_instructions,
    tools=[tool1, tool2, tool3, email_manager_tool],
    model="gpt-4o-mini",
)


# =============================================================================
# MAIN
# Runner.run() ejecuta el agente de forma asíncrona. trace() agrupa todas las
# llamadas LLM del flujo bajo un nombre visible en platform.openai.com/traces.
# =============================================================================

async def main():
    message = "Send out a cold sales email addressed to Dear CEO from Alice"
    with trace("Automated SDR"):
        result = await Runner.run(sales_manager, message)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
