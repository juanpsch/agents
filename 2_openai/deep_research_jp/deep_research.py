import sys, pathlib
_root = pathlib.Path(__file__).resolve().parent
while not (_root / "init_agents.py").exists() and _root != _root.parent:
    _root = _root.parent
sys.path.insert(0, str(_root))

import init_agents  # configura dotenv + tracing key
import gradio as gr
from research_manager import ResearchManager

# ── Estado de la conversación ──────────────────────────────────────────────
# phase: "idle" | "clarifying" | "researching"

def initial_state():
    return {"phase": "idle", "query": ""}


async def respond(message, history, state, send_email_flag):
    if not message.strip():
        yield history, state, gr.update(), ""
        return

    history = history + [{"role": "user", "content": message}]

    if state["phase"] == "idle":
        # Paso 1: pedir clarificaciones
        history = history + [{"role": "assistant", "content": "Analizando tu consulta..."}]
        yield history, state, gr.update(), ""

        questions = await ResearchManager().clarify(message)
        new_state = {"phase": "clarifying", "query": message}

        q_lines = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        response = (
            f"Para darte el mejor informe posible necesito un poco más de contexto:\n\n"
            f"{q_lines}\n\n"
            f"*Respondé todo en el siguiente mensaje (podés ser breve).*"
        )
        history[-1] = {"role": "assistant", "content": response}
        yield history, new_state, gr.update(), ""

    elif state["phase"] == "clarifying":
        # Paso 2: investigar con el contexto aclarado
        new_state = {"phase": "researching", "query": state["query"]}
        history = history + [{"role": "assistant", "content": "Iniciando investigación..."}]
        yield history, new_state, gr.update(), ""

        async for event in ResearchManager().run(state["query"], message, send_email_flag):
            if event["type"] == "report":
                report = event["data"]

                summary_block = f"**Resumen:** {report.short_summary}"
                if report.follow_up_questions:
                    fq = "\n".join(f"- {q}" for q in report.follow_up_questions)
                    summary_block += f"\n\n**Preguntas de seguimiento:**\n{fq}"

                history[-1] = {"role": "assistant", "content": f"Investigación completada.\n\n{summary_block}"}
                final_state = initial_state()
                yield history, final_state, gr.update(value=report.markdown_report), ""
            else:
                history[-1] = {"role": "assistant", "content": event["message"]}
                yield history, new_state, gr.update(), ""


def reset():
    return [], initial_state(), gr.update(value="")


# ── UI ─────────────────────────────────────────────────────────────────────

with gr.Blocks(
    theme=gr.themes.Default(primary_hue="sky", neutral_hue="slate"),
    title="Investigación Profunda",
    css="""
        .report-col { border-left: 1px solid #334155; padding-left: 1.5rem; }
        footer { display: none !important; }
    """,
) as ui:

    gr.Markdown("# Investigación Profunda\nHacé tu pregunta y el sistema te pedirá contexto antes de investigar.")

    app_state = gr.State(initial_state())

    with gr.Row(equal_height=True):

        # ── Columna izquierda: conversación ──────────────────────────────
        with gr.Column(scale=1):
            chatbot = gr.Chatbot(
                type="messages",
                height=520,
                label="Conversación",
                show_copy_button=True,
                bubble_full_width=False,
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="¿Sobre qué querés investigar?",
                    label="",
                    scale=5,
                    autofocus=True,
                )
                send_btn = gr.Button("Enviar", variant="primary", scale=1, min_width=80)

            with gr.Row():
                send_email_cb = gr.Checkbox(label="Enviar informe por email", value=True, scale=3)
                reset_btn = gr.Button("Nueva búsqueda", variant="secondary", scale=1)

        # ── Columna derecha: informe ─────────────────────────────────────
        with gr.Column(scale=1, elem_classes="report-col"):
            gr.Markdown("### Informe")
            report_output = gr.Markdown(
                value="*El informe aparecerá aquí una vez finalizada la investigación.*",
                height=560,
            )

    # ── Eventos ─────────────────────────────────────────────────────────
    shared_inputs  = [msg_input, chatbot, app_state, send_email_cb]
    shared_outputs = [chatbot, app_state, report_output, msg_input]

    send_btn.click(respond, shared_inputs, shared_outputs)
    msg_input.submit(respond, shared_inputs, shared_outputs)
    reset_btn.click(reset, [], [chatbot, app_state, report_output])


ui.launch(inbrowser=True)
