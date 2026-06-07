import sys, pathlib
_root = pathlib.Path(__file__).resolve().parent
while not (_root / "init_agents.py").exists() and _root != _root.parent:
    _root = _root.parent
sys.path.insert(0, str(_root))

import init_agents  # configura dotenv + tracing key
import gradio as gr
from research_manager import ResearchManager


def initial_state():
    return {
        "phase": "idle",   # idle | clarifying | researching | done | deepening
        "query": "",
        "report": None,
        "questions": [],
        "current_q": 0,
        "answers": [],
    }


# outputs: chatbot, app_state, report_output, email_btn, followup_radio, msg_input

async def respond(message, history, state, search_tool, num_searches):
    if not message.strip():
        yield history, state, gr.update(), gr.update(), gr.update(), ""
        return

    history = history + [{"role": "user", "content": message}]

    # ── IDLE: nueva consulta ──────────────────────────────────────────
    if state["phase"] == "idle":
        history = history + [{"role": "assistant", "content": "Analizando tu consulta..."}]
        yield history, state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

        try:
            questions = await ResearchManager().clarify(message)
        except ValueError as e:
            history[-1] = {"role": "assistant", "content": f"⚠️ {e}"}
            yield history, initial_state(), gr.update(), gr.update(visible=False), gr.update(visible=False), ""
            return
        new_state = {**initial_state(), "phase": "clarifying", "query": message, "questions": questions}

        total = len(questions)
        history[-1] = {"role": "assistant", "content": f"*(1/{total})* **{questions[0]}**"}
        yield history, new_state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

    # ── CLARIFYING: preguntas de a una ───────────────────────────────
    elif state["phase"] == "clarifying":
        answers = state["answers"] + [message]
        next_idx = state["current_q"] + 1
        questions = state["questions"]
        total = len(questions)

        if next_idx < total:
            new_state = {**state, "current_q": next_idx, "answers": answers}
            history = history + [{"role": "assistant", "content": f"*({next_idx + 1}/{total})* **{questions[next_idx]}**"}]
            yield history, new_state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

        else:
            # Todas contestadas → arrancar investigación
            combined = "\n".join(f"P: {q}\nR: {a}" for q, a in zip(questions, answers))
            new_state = {**state, "phase": "researching", "answers": answers}
            history = history + [{"role": "assistant", "content": "Perfecto, iniciando investigación..."}]
            yield history, new_state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

            async for event in ResearchManager().run(state["query"], combined, search_tool, num_searches):
                if event["type"] == "report":
                    report = event["data"]
                    done_state = {**new_state, "phase": "done", "report": report}

                    summary = f"Investigación completada.\n\n**Resumen:** {report.short_summary}"
                    if report.follow_up_questions:
                        summary += "\n\n*Hacé click en una pregunta abajo para profundizar el informe.*"
                    history = history + [{"role": "assistant", "content": summary}]

                    fq = report.follow_up_questions or []
                    numbered = [f"{i+1}. {q}" for i, q in enumerate(fq)]
                    yield (
                        history, done_state,
                        gr.update(value=report.markdown_report),
                        gr.update(visible=True, value="Enviar informe por email"),
                        gr.update(choices=numbered, value=None, visible=bool(fq)),
                        "",
                    )
                elif event["type"] == "blocked":
                    history = history + [{"role": "assistant", "content": f"⚠️ {event['message']}"}]
                    yield history, initial_state(), gr.update(), gr.update(visible=False), gr.update(visible=False), ""
                    return
                else:
                    history = history + [{"role": "assistant", "content": event["message"]}]
                    yield history, new_state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

    # ── DONE / DEEPENING: profundizar ────────────────────────────────
    elif state["phase"] in ("done", "deepening"):
        deep_state = {**state, "phase": "deepening"}
        history = history + [{"role": "assistant", "content": f"Profundizando: *{message}*..."}]
        yield history, deep_state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""

        async for event in ResearchManager().deepen(state["query"], state["report"], message, search_tool, num_searches):
            if event["type"] == "report":
                report = event["data"]
                done_state = {**state, "phase": "done", "report": report}

                summary = f"Informe actualizado.\n\n**Resumen:** {report.short_summary}"
                if report.follow_up_questions:
                    summary += "\n\n*Hacé click en una pregunta para seguir profundizando.*"
                history = history + [{"role": "assistant", "content": summary}]

                fq = report.follow_up_questions or []
                numbered = [f"{i+1}. {q}" for i, q in enumerate(fq)]
                yield (
                    history, done_state,
                    gr.update(value=report.markdown_report),
                    gr.update(visible=True, value="Enviar informe por email"),
                    gr.update(choices=numbered, value=None, visible=bool(fq)),
                    "",
                )
            else:
                history = history + [{"role": "assistant", "content": event["message"]}]
                yield history, deep_state, gr.update(), gr.update(visible=False), gr.update(visible=False), ""


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
        /* Página sin scroll — todo encaja en el viewport */
        html, body { overflow: hidden; height: 100%; }
        .gradio-container { height: 100vh !important; overflow: hidden !important; }
        .main-wrap { height: 100vh; display: flex; flex-direction: column; }

        /* Barra de opciones compacta */
        .options-bar {
            flex-shrink: 0;
            padding: 6px 16px !important;
            border-bottom: 1px solid #334155;
            align-items: center;
        }
        .options-bar label { font-size: 0.75rem !important; margin-bottom: 1px !important; }
        .options-bar .gr-radio-row { gap: 8px !important; }

        /* Columna del informe */
        .report-col { border-left: 1px solid #334155; padding-left: 1.5rem; }

        footer { display: none !important; }
    """,
) as ui:

    with gr.Column(elem_classes="main-wrap"):

        gr.Markdown("## Investigación Profunda")

        # ── Barra de opciones ─────────────────────────────────────────────
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

        # ── Contenido principal ───────────────────────────────────────────
        with gr.Row(equal_height=True):

            # Columna izquierda: conversación
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(
                    type="messages",
                    height=360,
                    label="Conversación",
                    show_copy_button=True,
                    bubble_full_width=False,
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

            # Columna derecha: informe
            with gr.Column(scale=1, elem_classes="report-col"):
                gr.Markdown("### Informe")
                report_output = gr.Markdown(
                    value="*El informe aparecerá aquí una vez finalizada la investigación.*",
                    height=430,
                )
                email_btn = gr.Button("Enviar informe por email", variant="secondary", visible=False)

        # ── Eventos ──────────────────────────────────────────────────────
        respond_outputs = [chatbot, app_state, report_output, email_btn, followup_radio, msg_input]

        send_btn.click(respond, [msg_input, chatbot, app_state, search_tool_selector, num_searches_slider], respond_outputs)
        msg_input.submit(respond, [msg_input, chatbot, app_state, search_tool_selector, num_searches_slider], respond_outputs)
        followup_radio.change(fill_followup, [followup_radio], [msg_input])
        email_btn.click(send_email, [chatbot, app_state], [chatbot, email_btn])
        reset_btn.click(reset, [], [chatbot, app_state, report_output, email_btn, followup_radio])


ui.launch(inbrowser=True)
