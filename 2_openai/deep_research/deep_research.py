import sys, pathlib
_root = pathlib.Path(__file__).resolve().parent
while not (_root / "init_agents.py").exists() and _root != _root.parent:
    _root = _root.parent
sys.path.insert(0, str(_root))

import init_agents  # configura dotenv + tracing key
import gradio as gr
from research_manager import ResearchManager


async def run(query: str):
    async for chunk in ResearchManager().run(query):
        yield chunk


with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("# Búsqueda Profunda")
    query_textbox = gr.Textbox(label="¿Sobre qué tema te gustaría investigar?")
    run_button = gr.Button("Ejecutar", variant="primary")
    report = gr.Markdown(label="Informe")
    
    run_button.click(fn=run, inputs=query_textbox, outputs=report)
    query_textbox.submit(fn=run, inputs=query_textbox, outputs=report)

ui.launch(inbrowser=True)

