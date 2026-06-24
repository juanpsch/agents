# init_agents.py
import os
from dotenv import load_dotenv
from agents import set_tracing_export_api_key

# Esto se ejecuta una sola vez al importar este módulo
load_dotenv()

tracing_key = os.getenv("OPENAI_TRACING_API_KEY")
if tracing_key:
    set_tracing_export_api_key(tracing_key)