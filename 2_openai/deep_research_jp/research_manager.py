from agents import Runner, trace, gen_trace_id, InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered
from langsmith import traceable
from langsmith import trace as ls_trace
from search_agent import make_search_agent
from search_tools import duckduckgo_search, openai_search, tavily_search
from planner_agent import planner_agent, WebSearchItem, WebSearchPlan
from writer_agent import writer_agent, ReportData
from email_agent import email_agent
from clarifier_agent import clarifier_agent, ClarificationResult
import asyncio

SEARCH_TOOLS = {
    "DuckDuckGo": duckduckgo_search,
    "OpenAI WebSearch": openai_search,
    "Tavily": tavily_search,
}


class ResearchManager:

    # ── Punto de entrada principal: maneja la conversación completa ────────

    async def handle(self, message: str, state: dict, search_tool_name: str, num_searches: int):
        thread_id = state.get("thread_id")
        lse = {"metadata": {"thread_id": thread_id}} if thread_id else {}
        """
        Recibe el mensaje del usuario y el estado actual.
        Yields eventos:
          {"type": "message",  "content": str}          → agregar al chat
          {"type": "state",    "state": dict}            → actualizar estado
          {"type": "blocked",  "message": str}           → error + reset
          {"type": "report",   "data": ReportData,
                               "state": dict}            → informe listo
        """
        phase = state["phase"]

        # ── IDLE: nueva consulta ──────────────────────────────────────────
        if phase == "idle":
            yield {"type": "message", "content": "Analizando tu consulta..."}
            try:
                questions = await self.clarify(message, langsmith_extra=lse)
            except ValueError as e:
                yield {"type": "blocked", "message": str(e)}
                return

            new_state = {
                **state,
                "phase": "clarifying",
                "query": message,
                "questions": questions,
                "current_q": 0,
                "answers": [],
            }
            total = len(questions)
            yield {"type": "message", "content": f"*(1/{total})* **{questions[0]}**"}
            yield {"type": "state", "state": new_state}

        # ── CLARIFYING: preguntas de a una ────────────────────────────────
        elif phase == "clarifying":
            answers  = state["answers"] + [message]
            next_idx = state["current_q"] + 1
            questions = state["questions"]
            total    = len(questions)

            if next_idx < total:
                new_state = {**state, "current_q": next_idx, "answers": answers}
                yield {"type": "message", "content": f"*({next_idx + 1}/{total})* **{questions[next_idx]}**"}
                yield {"type": "state", "state": new_state}

            else:
                combined  = "\n".join(f"P: {q}\nR: {a}" for q, a in zip(questions, answers))
                new_state = {**state, "phase": "researching", "answers": answers}
                yield {"type": "state", "state": new_state}
                yield {"type": "message", "content": "Perfecto, iniciando investigación..."}

                async for event in self.run(state["query"], combined, search_tool_name, num_searches, thread_id):
                    if event["type"] == "report":
                        done_state = {**new_state, "phase": "done", "report": event["data"]}
                        yield {"type": "report", "data": event["data"], "state": done_state}
                    elif event["type"] == "blocked":
                        yield event
                    else:
                        yield {"type": "message", "content": event["message"]}

        # ── DONE / DEEPENING: profundizar ─────────────────────────────────
        elif phase in ("done", "deepening"):
            deep_state = {**state, "phase": "deepening"}
            yield {"type": "state", "state": deep_state}
            yield {"type": "message", "content": f"Profundizando: *{message}*..."}

            async for event in self.deepen(state["query"], state["report"], message, search_tool_name, num_searches, thread_id):
                if event["type"] == "report":
                    done_state = {**state, "phase": "done", "report": event["data"]}
                    yield {"type": "report", "data": event["data"], "state": done_state}
                elif event["type"] == "blocked":
                    yield event
                else:
                    yield {"type": "message", "content": event["message"]}

    # ── Métodos internos ───────────────────────────────────────────────────

    @traceable(name="clarify")
    async def clarify(self, query: str) -> list[str]:
        try:
            result = await Runner.run(clarifier_agent, f"Consulta del usuario: {query}")
        except InputGuardrailTripwireTriggered as e:
            reason = e.guardrail_result.output.output_info.reason
            raise ValueError(f"Consulta bloqueada: {reason}")
        return result.final_output_as(ClarificationResult).questions

    async def run(self, query: str, clarifications: str = "", search_tool_name: str = "DuckDuckGo", num_searches: int = 3, thread_id: str = None):
        lse = {"metadata": {"thread_id": thread_id}} if thread_id else {}
        trace_id = gen_trace_id()
        with ls_trace("Investigación profunda", metadata={"thread_id": thread_id} if thread_id else {}), trace("Investigación profunda", trace_id=trace_id):
            yield {"type": "message", "message": f"Traza: https://platform.openai.com/traces/trace?trace_id={trace_id}"}
            yield {"type": "progress", "message": "Planificando búsquedas..."}
            try:
                search_plan = await self.plan_searches(query, clarifications, num_searches, langsmith_extra=lse)
            except InputGuardrailTripwireTriggered as e:
                reason = e.guardrail_result.output.output_info.reason
                yield {"type": "blocked", "message": f"Consulta bloqueada: {reason}"}
                return
            n = len(search_plan.searches)

            tool = SEARCH_TOOLS.get(search_tool_name, duckduckgo_search)
            yield {"type": "progress", "message": f"Plan listo — realizando {n} búsquedas en paralelo ({search_tool_name})..."}
            tasks = [asyncio.create_task(self.search(item, tool, langsmith_extra=lse)) for item in search_plan.searches]
            results = []
            completed = 0
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                completed += 1
                yield {"type": "progress", "message": f"Buscando... {completed}/{n} completadas"}

            yield {"type": "progress", "message": "Redactando informe..."}
            try:
                report = await self.write_report(query, clarifications, results, langsmith_extra=lse)
            except OutputGuardrailTripwireTriggered as e:
                reason = e.guardrail_result.output.output_info.reason
                yield {"type": "blocked", "message": f"Informe bloqueado por contenido problemático: {reason}"}
                return
            yield {"type": "report", "data": report}

    async def deepen(self, query: str, original_report: ReportData, focus: str, search_tool_name: str = "DuckDuckGo", num_searches: int = 3, thread_id: str = None):
        lse = {"metadata": {"thread_id": thread_id}} if thread_id else {}
        trace_id = gen_trace_id()
        with ls_trace("Profundización", metadata={"thread_id": thread_id} if thread_id else {}), trace("Profundización", trace_id=trace_id):
            yield {"type": "progress", "message": f"Traza: https://platform.openai.com/traces/trace?trace_id={trace_id}"}
            yield {"type": "progress", "message": "Planificando búsquedas adicionales..."}
            search_plan = await self.plan_searches(focus, "", num_searches, langsmith_extra=lse)
            n = len(search_plan.searches)

            tool = SEARCH_TOOLS.get(search_tool_name, duckduckgo_search)
            yield {"type": "progress", "message": f"Realizando {n} búsquedas adicionales ({search_tool_name})..."}
            tasks = [asyncio.create_task(self.search(item, tool, langsmith_extra=lse)) for item in search_plan.searches]
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
            result = await self.write_report_deepen(input_text, langsmith_extra=lse)
            updated_report = result
            yield {"type": "report", "data": updated_report}

    @traceable(name="plan-searches")
    async def plan_searches(self, query: str, clarifications: str, num_searches: int = 3) -> WebSearchPlan:
        context = f"Consulta: {query}\nNúmero de búsquedas a realizar: {num_searches}"
        if clarifications:
            context += f"\nContexto adicional: {clarifications}"
        result = await Runner.run(planner_agent, context)
        return result.final_output_as(WebSearchPlan)

    @traceable(name="search")
    async def search(self, item: WebSearchItem, tool) -> str | None:
        input = f"Término de búsqueda: {item.query}\nRazón: {item.reason}"
        try:
            result = await Runner.run(make_search_agent(tool), input)
            return str(result.final_output)
        except Exception:
            return None

    @traceable(name="write-report-deepen")
    async def write_report_deepen(self, input_text: str) -> ReportData:
        result = await Runner.run(writer_agent, input_text)
        return result.final_output_as(ReportData)

    @traceable(name="write-report")
    async def write_report(self, query: str, clarifications: str, search_results: list[str]) -> ReportData:
        context = f"Consulta original: {query}"
        if clarifications:
            context += f"\nContexto del usuario: {clarifications}"
        context += f"\nResultados de búsqueda: {search_results}"
        result = await Runner.run(writer_agent, context)
        return result.final_output_as(ReportData)

    async def send_email(self, report: ReportData) -> None:
        await Runner.run(email_agent, report.markdown_report)
