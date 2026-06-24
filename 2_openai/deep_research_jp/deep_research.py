import sys, pathlib
_root = pathlib.Path(__file__).resolve().parent
while not (_root / "init_agents.py").exists() and _root != _root.parent:
    _root = _root.parent
sys.path.insert(0, str(_root))

import init_agents  # configura dotenv + tracing key
import gradio as gr
import uuid
from research_manager import ResearchManager


def initial_state():
    return {"phase": "idle", "query": "", "report": None, "questions": [], "current_q": 0, "answers": [], "thread_id": str(uuid.uuid4())}


# outputs: chatbot, app_state, report_output, email_btn, followup_radio, msg_input

async def respond(message, history, state, search_tool, num_searches):
    if not message.strip():
        yield history, state, gr.update(), gr.update(), gr.update(), ""
        return

    history = history + [{"role": "user", "content": message}]
    yield history, state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

    async for event in ResearchManager().handle(message, state, search_tool, int(num_searches)):
        t = event["type"]

        if t == "message":
            history = history + [{"role": "assistant", "content": event["content"]}]
            yield history, state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

        elif t == "state":
            state = event["state"]
            yield history, state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

        elif t == "blocked":
            history = history + [{"role": "assistant", "content": f"⚠️ {event['message']}"}]
            yield history, initial_state(), gr.update(), gr.update(visible=False), gr.update(visible=False), ""
            return

        elif t == "report":
            state = event["state"]
            report = event["data"]
            summary = f"Investigación completada.\n\n**Resumen:** {report.short_summary}"
            if report.follow_up_questions:
                summary += "\n\n*Hacé click en una pregunta abajo para profundizar el informe.*"
            history = history + [{"role": "assistant", "content": summary}]
            fq = report.follow_up_questions or []
            numbered = [f"{i+1}. {q}" for i, q in enumerate(fq)]
            yield (
                history, state,
                gr.update(value=report.markdown_report),
                gr.update(visible=True, value="Enviar informe por email"),
                gr.update(choices=numbered, value=None, visible=bool(fq)),
                "",
            )


def fill_followup(choice):
    if not choice:
        return gr.update()
    text = choice.split(". ", 1)[1] if ". " in choice else choice
    return gr.update(value=text)


async def send_email(history, state):
    if state.get("report") is None:
        yield history, gr.update(value="Sin informe para enviar.")
        return
    yield history, gr.update(value="Enviando...", interactive=False)
    try:
        await ResearchManager().send_email(state["report"])
        history = history + [{"role": "assistant", "content": "Email enviado correctamente."}]
        yield history, gr.update(value="Email enviado", interactive=False)
    except Exception as e:
        history = history + [{"role": "assistant", "content": f"Error al enviar email: {e}"}]
        yield history, gr.update(value="Enviar informe por email", interactive=True)


def reset():
    return (
        [],
        initial_state(),
        gr.update(value="*El informe aparecerá aquí una vez finalizada la investigación.*"),
        gr.update(visible=False),
        gr.update(choices=[], visible=False, value=None),
    )


# ── UI ─────────────────────────────────────────────────────────────────────

with gr.Blocks(
    theme=gr.themes.Default(primary_hue="sky", neutral_hue="slate"),
    title="Investigación Profunda",
    css="""
        .options-bar {
            padding: 6px 16px !important;
            border-bottom: 1px solid #334155;
            align-items: center;
        }
        .options-bar label { font-size: 0.75rem !important; margin-bottom: 1px !important; }
        .report-col { border-left: 1px solid #334155; padding-left: 1.5rem; }
        footer { display: none !important; }
    """,
) as ui:

    gr.Markdown("## Investigación Profunda")

    with gr.Row(elem_classes="options-bar"):
        search_tool_selector = gr.Radio(
            choices=["DuckDuckGo", "OpenAI WebSearch", "Tavily"],
            value="DuckDuckGo",
            label="Motor de búsqueda",
            scale=3,
        )
        num_searches_slider = gr.Slider(
            minimum=1, maximum=10, value=3, step=1,
            label="Búsquedas",
            scale=1,
            min_width=160,
        )

    app_state = gr.State(initial_state())

    with gr.Row(equal_height=True):

        with gr.Column(scale=1):
            chatbot = gr.Chatbot(
                type="messages",
                height=340,
                label="Conversación",
                show_copy_button=True,
            )
            followup_radio = gr.Radio(
                choices=[],
                label="Preguntas de seguimiento — click para profundizar",
                visible=False,
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="¿Sobre qué querés investigar?",
                    label="",
                    scale=5,
                    autofocus=True,
                )
                send_btn = gr.Button("Enviar", variant="primary", scale=1, min_width=80)
            reset_btn = gr.Button("Nueva búsqueda", variant="secondary")

        with gr.Column(scale=1, elem_classes="report-col"):
            gr.Markdown("### Informe")
            report_output = gr.Markdown(
                value="*El informe aparecerá aquí una vez finalizada la investigación.*",
                height=460,
            )
            email_btn = gr.Button("Enviar informe por email", variant="secondary", visible=False)

    respond_outputs = [chatbot, app_state, report_output, email_btn, followup_radio, msg_input]

    send_btn.click(respond, [msg_input, chatbot, app_state, search_tool_selector, num_searches_slider], respond_outputs)
    msg_input.submit(respond, [msg_input, chatbot, app_state, search_tool_selector, num_searches_slider], respond_outputs)
    followup_radio.change(fill_followup, [followup_radio], [msg_input])
    email_btn.click(send_email, [chatbot, app_state], [chatbot, email_btn])
    reset_btn.click(reset, [], [chatbot, app_state, report_output, email_btn, followup_radio])


ui.launch(inbrowser=True)
