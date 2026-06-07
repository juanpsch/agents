from agents import Agent, ModelSettings

INSTRUCTIONS = (
    "Eres un asistente de investigación. Dado un término de búsqueda, buscas en la web ese término y "
    "produce un resumen conciso de los resultados. El resumen debe tener 2-3 párrafos y menos de 300 "
    "palabras. Captura los puntos principales. Escribe de manera concisa, no es necesario tener frases completas o buena "
    "gramática. Esto será consumido por alguien que sintetiza un informe, por lo que es vital que captures la "
    "esencia y ignores cualquier fluff. No incluyas ningún comentario adicional más que el resumen en sí."
)


def make_search_agent(tool):
    return Agent(
        name="Agente de búsqueda",
        instructions=INSTRUCTIONS,
        tools=[tool],
        model="gpt-4o-mini",
        model_settings=ModelSettings(tool_choice="required"),
    )
