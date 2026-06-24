from pydantic import BaseModel, Field
from agents import Agent
from guardrails import query_safety

class ClarificationResult(BaseModel):
    questions: list[str] = Field(description="Lista de 2-3 preguntas clarificadoras")

INSTRUCTIONS = """Eres un asistente experto en investigación. Tu tarea es hacer 2-3 preguntas
clarificadoras breves y específicas para entender mejor lo que el usuario necesita investigar.

Las preguntas deben cubrir aspectos como:
- La profundidad deseada (resumen ejecutivo vs análisis exhaustivo)
- El enfoque o ángulo específico que le interesa
- El propósito o audiencia del informe

Sé directo y conciso. Máximo 3 preguntas. No hagas preguntas redundantes ni obvias."""

clarifier_agent = Agent(
    name="Agente clarificador",
    instructions=INSTRUCTIONS,
    model="gpt-4o-mini",
    output_type=ClarificationResult,
    input_guardrails=[query_safety],
)
