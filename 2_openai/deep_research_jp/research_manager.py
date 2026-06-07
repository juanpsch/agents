from agents import Runner, trace, gen_trace_id
from search_agent import search_agent
from planner_agent import planner_agent, WebSearchItem, WebSearchPlan
from writer_agent import writer_agent, ReportData
from email_agent import email_agent
from clarifier_agent import clarifier_agent, ClarificationResult
import asyncio


class ResearchManager:

    async def clarify(self, query: str) -> list[str]:
        result = await Runner.run(clarifier_agent, f"Consulta del usuario: {query}")
        return result.final_output_as(ClarificationResult).questions

    async def run(self, query: str, clarifications: str = ""):
        trace_id = gen_trace_id()
        with trace("Investigación profunda", trace_id=trace_id):
            yield {"type": "status", "message": f"Traza: https://platform.openai.com/traces/trace?trace_id={trace_id}"}
            yield {"type": "progress", "message": "Planificando búsquedas..."}
            search_plan = await self.plan_searches(query, clarifications)
            n = len(search_plan.searches)

            yield {"type": "progress", "message": f"Plan listo — realizando {n} búsquedas en paralelo..."}
            tasks = [asyncio.create_task(self.search(item)) for item in search_plan.searches]
            results = []
            completed = 0
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                completed += 1
                yield {"type": "progress", "message": f"Buscando... {completed}/{n} completadas"}

            yield {"type": "progress", "message": "Redactando informe..."}
            report = await self.write_report(query, clarifications, results)
            yield {"type": "report", "data": report}

    async def deepen(self, query: str, original_report: ReportData, focus: str):
        trace_id = gen_trace_id()
        with trace("Profundización", trace_id=trace_id):
            yield {"type": "status", "message": f"Traza: https://platform.openai.com/traces/trace?trace_id={trace_id}"}
            yield {"type": "progress", "message": "Planificando búsquedas adicionales..."}
            search_plan = await self.plan_searches(focus, "")
            n = len(search_plan.searches)

            yield {"type": "progress", "message": f"Realizando {n} búsquedas adicionales..."}
            tasks = [asyncio.create_task(self.search(item)) for item in search_plan.searches]
            results = []
            completed = 0
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                completed += 1
                yield {"type": "progress", "message": f"Buscando... {completed}/{n} completadas"}

            yield {"type": "progress", "message": "Refinando informe..."}
            input_text = (
                f"Consulta original: {query}\n\n"
                f"Informe existente:\n{original_report.markdown_report}\n\n"
                f"El usuario quiere profundizar en: {focus}\n\n"
                f"Nueva investigación adicional:\n{results}\n\n"
                f"Expandí y mejorá el informe incorporando la nueva información. "
                f"Mantené todo el contenido previo y enriquecelo con secciones nuevas o ampliadas."
            )
            result = await Runner.run(writer_agent, input_text)
            updated_report = result.final_output_as(ReportData)
            yield {"type": "report", "data": updated_report}

    async def plan_searches(self, query: str, clarifications: str) -> WebSearchPlan:
        context = f"Consulta: {query}"
        if clarifications:
            context += f"\nContexto adicional: {clarifications}"
        result = await Runner.run(planner_agent, context)
        return result.final_output_as(WebSearchPlan)

    async def search(self, item: WebSearchItem) -> str | None:
        input = f"Término de búsqueda: {item.query}\nRazón: {item.reason}"
        try:
            result = await Runner.run(search_agent, input)
            return str(result.final_output)
        except Exception:
            return None

    async def write_report(self, query: str, clarifications: str, search_results: list[str]) -> ReportData:
        context = f"Consulta original: {query}"
        if clarifications:
            context += f"\nContexto del usuario: {clarifications}"
        context += f"\nResultados de búsqueda: {search_results}"
        result = await Runner.run(writer_agent, context)
        return result.final_output_as(ReportData)

    async def send_email(self, report: ReportData) -> None:
        await Runner.run(email_agent, report.markdown_report)
