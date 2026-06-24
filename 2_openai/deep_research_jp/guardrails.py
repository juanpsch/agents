from pydantic import BaseModel
from agents import (
    Agent, Runner,
    GuardrailFunctionOutput,
    input_guardrail, output_guardrail,
    RunContextWrapper,
)


# ── Modelos de salida ──────────────────────────────────────────────────────

class SafetyCheck(BaseModel):
    is_safe: bool
    reason: str


# ── Agentes evaluadores ────────────────────────────────────────────────────

_input_checker = Agent(
    name="Input safety checker",
    instructions="""Evaluás si una consulta de investigación es segura para procesar.
Marcá como NO segura si la consulta busca:
- Instrucciones para actividades ilegales (síntesis de drogas, armas, explosivos, hacking malicioso)
- Contenido que facilite daño a personas
- Material de abuso infantil (CSAM)
- Doxxing o violación de privacidad de individuos
- Campañas de desinformación o propaganda

Una consulta es segura si busca información, análisis, historia, ciencia, tecnología, negocios,
o cualquier tema legítimo de investigación, incluso si el tema es sensible (crimen, conflictos, política).
El criterio es si la consulta FACILITA daño, no si menciona temas difíciles.
Respondé solo con el JSON requerido.""",
    model="gpt-4o-mini",
    output_type=SafetyCheck,
)

_output_checker = Agent(
    name="Output safety checker",
    instructions="""Evaluás si un informe de investigación es seguro para entregar al usuario.
Marcá como NO seguro si el informe contiene:
- Instrucciones paso a paso para actividades ilegales o peligrosas
- Discurso de odio o contenido que incite violencia
- Información personal identificable (PII) de individuos privados
- Contenido sexual explícito no solicitado

Un informe es seguro aunque analice temas sensibles, presente datos históricos sobre violencia o crimen,
o discuta controversias. El criterio es si el contenido FACILITA daño concreto.
Respondé solo con el JSON requerido.""",
    model="gpt-4o-mini",
    output_type=SafetyCheck,
)


# ── Guardrails ─────────────────────────────────────────────────────────────

@input_guardrail
async def query_safety(
    ctx: RunContextWrapper, agent: Agent, input: str | list
) -> GuardrailFunctionOutput:
    text = input if isinstance(input, str) else str(input)
    result = await Runner.run(_input_checker, text, context=ctx.context)
    check = result.final_output_as(SafetyCheck)
    return GuardrailFunctionOutput(output_info=check, tripwire_triggered=not check.is_safe)


@output_guardrail
async def report_safety(
    ctx: RunContextWrapper, agent: Agent, output
) -> GuardrailFunctionOutput:
    text = output.markdown_report if hasattr(output, "markdown_report") else str(output)
    result = await Runner.run(_output_checker, text[:4000], context=ctx.context)  # primeros 4k chars
    check = result.final_output_as(SafetyCheck)
    return GuardrailFunctionOutput(output_info=check, tripwire_triggered=not check.is_safe)
