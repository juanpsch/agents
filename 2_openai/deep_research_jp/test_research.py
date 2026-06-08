"""
Unit tests for deep_research / research_manager.

Run with:
    pytest 2_openai/deep_research_jp/test_research.py -v

All calls to external services (OpenAI, search tools) are mocked so the
suite runs offline and fast.
"""

import sys
import pathlib
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Bootstrap: add project root and stub heavy imports ────────────────────────

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Stub init_agents before anything imports it
sys.modules.setdefault("init_agents", types.ModuleType("init_agents"))

# Stub the `agents` SDK so we don't need a real API key at import time
_agents_stub = types.ModuleType("agents")
# Exception stubs must be real exception classes so `except Foo` works.
class _InputGuardrailTripwireTriggered(Exception):
    def __init__(self, guardrail_result=None):
        self.guardrail_result = guardrail_result

class _OutputGuardrailTripwireTriggered(Exception):
    def __init__(self, guardrail_result=None):
        self.guardrail_result = guardrail_result

_agents_stub.InputGuardrailTripwireTriggered = _InputGuardrailTripwireTriggered
_agents_stub.OutputGuardrailTripwireTriggered = _OutputGuardrailTripwireTriggered

for _name in [
    "Agent", "Runner", "trace", "gen_trace_id",
    "GuardrailFunctionOutput", "RunContextWrapper",
    "WebSearchTool", "function_tool",
    "input_guardrail", "output_guardrail",
    "ModelSettings",
]:
    setattr(_agents_stub, _name, MagicMock())

# Make the decorators pass-through so module-level agents are created cleanly
_agents_stub.input_guardrail = lambda fn: fn
_agents_stub.output_guardrail = lambda fn: fn
_agents_stub.function_tool = lambda fn: fn

sys.modules["agents"] = _agents_stub

# Stub langsmith
_ls = types.ModuleType("langsmith")
_ls.traceable = lambda **kw: (lambda fn: fn)
_ls.trace = MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False)))
sys.modules["langsmith"] = _ls

# Stub ddgs and tavily so search_tools can be imported
sys.modules.setdefault("ddgs", types.ModuleType("ddgs"))
sys.modules.setdefault("tavily", types.ModuleType("tavily"))

# ── Now safe to import project modules ────────────────────────────────────────

from writer_agent import ReportData  # noqa: E402
from planner_agent import WebSearchItem, WebSearchPlan  # noqa: E402
from clarifier_agent import ClarificationResult  # noqa: E402
from research_manager import ResearchManager  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_state(phase="idle", **kwargs):
    base = {
        "phase": phase,
        "query": "",
        "report": None,
        "questions": [],
        "current_q": 0,
        "answers": [],
        "thread_id": "test-thread-id",
    }
    base.update(kwargs)
    return base


def make_report(**kwargs):
    defaults = dict(
        short_summary="Resumen de prueba.",
        markdown_report="# Informe\nContenido.",
        follow_up_questions=["¿Pregunta 1?", "¿Pregunta 2?"],
    )
    defaults.update(kwargs)
    return ReportData(**defaults)


async def collect(gen):
    """Drain an async generator and return all yielded values."""
    events = []
    async for item in gen:
        events.append(item)
    return events


# ── fill_followup ──────────────────────────────────────────────────────────────

class TestFillFollowup:
    """Tests for the fill_followup helper in deep_research.py.

    We test the pure logic directly without importing Gradio.
    """

    def _fill(self, choice):
        """Inline copy of fill_followup logic."""
        if not choice:
            return None  # gr.update() equivalent
        return choice.split(". ", 1)[1] if ". " in choice else choice

    def test_numbered_choice_strips_prefix(self):
        assert self._fill("1. ¿Cuál es el impacto económico?") == "¿Cuál es el impacto económico?"

    def test_choice_without_number_returned_as_is(self):
        assert self._fill("¿Pregunta sin número?") == "¿Pregunta sin número?"

    def test_empty_choice_returns_none(self):
        assert self._fill("") is None

    def test_none_choice_returns_none(self):
        assert self._fill(None) is None

    def test_multipart_question_preserves_dots(self):
        assert self._fill("2. ¿Qué es A.I.?") == "¿Qué es A.I.?"


# ── initial_state (tested inline to avoid Gradio UI launch) ───────────────────

class TestInitialState:
    """
    We reproduce initial_state() logic here to avoid importing deep_research.py,
    which calls ui.launch() at module level and would open a browser window.
    """

    def _initial_state(self):
        import uuid
        return {
            "phase": "idle",
            "query": "",
            "report": None,
            "questions": [],
            "current_q": 0,
            "answers": [],
            "thread_id": str(uuid.uuid4()),
        }

    def test_keys_present(self):
        state = self._initial_state()
        assert set(state.keys()) == {"phase", "query", "report", "questions", "current_q", "answers", "thread_id"}

    def test_initial_phase_is_idle(self):
        assert self._initial_state()["phase"] == "idle"

    def test_thread_id_is_unique(self):
        assert self._initial_state()["thread_id"] != self._initial_state()["thread_id"]


# ── ResearchManager.handle — phase: idle ──────────────────────────────────────

class TestHandleIdle:
    @pytest.mark.asyncio
    async def test_emits_message_then_question_and_state(self):
        mgr = ResearchManager()
        mgr.clarify = AsyncMock(return_value=["¿Profundidad?", "¿Audiencia?"])

        events = await collect(mgr.handle("IA en educación", make_state("idle"), "DuckDuckGo", 3))

        types_ = [e["type"] for e in events]
        assert types_ == ["message", "message", "state"]

    @pytest.mark.asyncio
    async def test_state_transitions_to_clarifying(self):
        mgr = ResearchManager()
        mgr.clarify = AsyncMock(return_value=["¿Profundidad?"])

        events = await collect(mgr.handle("IA en educación", make_state("idle"), "DuckDuckGo", 3))

        state_event = next(e for e in events if e["type"] == "state")
        assert state_event["state"]["phase"] == "clarifying"
        assert state_event["state"]["query"] == "IA en educación"
        assert state_event["state"]["questions"] == ["¿Profundidad?"]

    @pytest.mark.asyncio
    async def test_first_question_shows_counter(self):
        mgr = ResearchManager()
        mgr.clarify = AsyncMock(return_value=["¿Profundidad?", "¿Audiencia?"])

        events = await collect(mgr.handle("IA en educación", make_state("idle"), "DuckDuckGo", 3))

        question_event = events[1]  # second event is the first question
        assert "(1/2)" in question_event["content"]
        assert "¿Profundidad?" in question_event["content"]

    @pytest.mark.asyncio
    async def test_blocked_when_clarify_raises_value_error(self):
        mgr = ResearchManager()
        mgr.clarify = AsyncMock(side_effect=ValueError("Consulta bloqueada: tema peligroso"))

        events = await collect(mgr.handle("Algo peligroso", make_state("idle"), "DuckDuckGo", 3))

        assert len(events) == 2  # "Analizando..." message + blocked
        blocked = events[-1]
        assert blocked["type"] == "blocked"
        assert "bloqueada" in blocked["message"]


# ── ResearchManager.handle — phase: clarifying ────────────────────────────────

class TestHandleClarifying:
    def _clarifying_state(self, questions, current_q=0, answers=None):
        return make_state(
            "clarifying",
            query="IA en salud",
            questions=questions,
            current_q=current_q,
            answers=answers or [],
        )

    @pytest.mark.asyncio
    async def test_advances_to_next_question(self):
        mgr = ResearchManager()
        state = self._clarifying_state(["¿Q1?", "¿Q2?", "¿Q3?"], current_q=0)

        events = await collect(mgr.handle("Mi respuesta", state, "DuckDuckGo", 3))

        types_ = [e["type"] for e in events]
        assert "message" in types_
        assert "state" in types_
        state_evt = next(e for e in events if e["type"] == "state")
        assert state_evt["state"]["current_q"] == 1
        assert state_evt["state"]["answers"] == ["Mi respuesta"]

    @pytest.mark.asyncio
    async def test_last_answer_triggers_research(self):
        mgr = ResearchManager()

        async def fake_run(*args, **kwargs):
            report = make_report()
            yield {"type": "report", "data": report}

        mgr.run = fake_run
        state = self._clarifying_state(["¿Q1?", "¿Q2?"], current_q=1, answers=["R1"])

        events = await collect(mgr.handle("R2", state, "DuckDuckGo", 3))

        types_ = [e["type"] for e in events]
        assert "report" in types_

    @pytest.mark.asyncio
    async def test_last_answer_state_becomes_done(self):
        mgr = ResearchManager()

        async def fake_run(*args, **kwargs):
            yield {"type": "report", "data": make_report()}

        mgr.run = fake_run
        state = self._clarifying_state(["¿Q1?"], current_q=0, answers=[])

        events = await collect(mgr.handle("R1", state, "DuckDuckGo", 3))

        report_evt = next(e for e in events if e["type"] == "report")
        assert report_evt["state"]["phase"] == "done"

    @pytest.mark.asyncio
    async def test_blocked_event_forwarded(self):
        mgr = ResearchManager()

        async def fake_run(*args, **kwargs):
            yield {"type": "blocked", "message": "Contenido bloqueado"}

        mgr.run = fake_run
        state = self._clarifying_state(["¿Q1?"], current_q=0)

        events = await collect(mgr.handle("respuesta", state, "DuckDuckGo", 3))

        blocked = next(e for e in events if e["type"] == "blocked")
        assert blocked["message"] == "Contenido bloqueado"

    @pytest.mark.asyncio
    async def test_question_counter_shown_correctly(self):
        mgr = ResearchManager()
        state = self._clarifying_state(["¿Q1?", "¿Q2?", "¿Q3?"], current_q=1, answers=["R1"])

        events = await collect(mgr.handle("R2", state, "DuckDuckGo", 3))

        msg_events = [e for e in events if e["type"] == "message"]
        assert any("(3/3)" in e["content"] for e in msg_events)


# ── ResearchManager.handle — phase: done / deepening ──────────────────────────

class TestHandleDone:
    @pytest.mark.asyncio
    async def test_deepening_emits_report(self):
        mgr = ResearchManager()

        async def fake_deepen(*args, **kwargs):
            yield {"type": "report", "data": make_report()}

        mgr.deepen = fake_deepen
        state = make_state("done", query="IA en salud", report=make_report())

        events = await collect(mgr.handle("Profundizar en costos", state, "DuckDuckGo", 3))

        assert any(e["type"] == "report" for e in events)

    @pytest.mark.asyncio
    async def test_deepening_phase_set_then_reverted_to_done(self):
        mgr = ResearchManager()

        async def fake_deepen(*args, **kwargs):
            yield {"type": "report", "data": make_report()}

        mgr.deepen = fake_deepen
        state = make_state("done", query="IA en salud", report=make_report())

        events = await collect(mgr.handle("Profundizar", state, "DuckDuckGo", 3))

        state_events = [e for e in events if e["type"] == "state"]
        phases = [e["state"]["phase"] for e in state_events]
        assert "deepening" in phases

        report_evt = next(e for e in events if e["type"] == "report")
        assert report_evt["state"]["phase"] == "done"


# ── ResearchManager.run — internal pipeline ───────────────────────────────────

class TestRunPipeline:
    @pytest.mark.asyncio
    async def test_run_emits_report_at_end(self):
        mgr = ResearchManager()
        mgr.plan_searches = AsyncMock(return_value=WebSearchPlan(searches=[
            WebSearchItem(query="IA educación", reason="relevante"),
        ]))
        mgr.search = AsyncMock(return_value="Resultado de búsqueda simulado")
        mgr.write_report = AsyncMock(return_value=make_report())

        events = await collect(mgr.run("IA en educación", "", "DuckDuckGo", 1, "tid"))

        assert any(e["type"] == "report" for e in events)

    @pytest.mark.asyncio
    async def test_run_blocked_on_input_guardrail(self):
        guardrail_result = MagicMock()
        guardrail_result.output.output_info.reason = "Tema peligroso"
        exc = _InputGuardrailTripwireTriggered(guardrail_result)

        mgr = ResearchManager()
        mgr.plan_searches = AsyncMock(side_effect=exc)

        events = await collect(mgr.run("algo peligroso", "", "DuckDuckGo", 1, "tid"))

        blocked = next(e for e in events if e["type"] == "blocked")
        assert "bloqueada" in blocked["message"]

    @pytest.mark.asyncio
    async def test_run_blocked_on_output_guardrail(self):
        guardrail_result = MagicMock()
        guardrail_result.output.output_info.reason = "Contenido problemático"
        exc = _OutputGuardrailTripwireTriggered(guardrail_result)

        mgr = ResearchManager()
        mgr.plan_searches = AsyncMock(return_value=WebSearchPlan(searches=[
            WebSearchItem(query="q", reason="r"),
        ]))
        mgr.search = AsyncMock(return_value="resultado")
        mgr.write_report = AsyncMock(side_effect=exc)

        events = await collect(mgr.run("query", "", "DuckDuckGo", 1, "tid"))

        blocked = next(e for e in events if e["type"] == "blocked")
        assert "bloqueado" in blocked["message"]

    @pytest.mark.asyncio
    async def test_failed_search_does_not_crash_pipeline(self):
        mgr = ResearchManager()
        mgr.plan_searches = AsyncMock(return_value=WebSearchPlan(searches=[
            WebSearchItem(query="q1", reason="r1"),
            WebSearchItem(query="q2", reason="r2"),
        ]))
        # First search fails, second succeeds
        mgr.search = AsyncMock(side_effect=[None, "resultado"])
        mgr.write_report = AsyncMock(return_value=make_report())

        events = await collect(mgr.run("query", "", "DuckDuckGo", 2, "tid"))

        assert any(e["type"] == "report" for e in events)

    @pytest.mark.asyncio
    async def test_search_tool_selection(self):
        from search_tools import duckduckgo_search, tavily_search

        mgr = ResearchManager()
        captured_tool = {}

        async def fake_search(item, tool, **kw):
            captured_tool["tool"] = tool
            return "res"

        mgr.plan_searches = AsyncMock(return_value=WebSearchPlan(searches=[
            WebSearchItem(query="q", reason="r"),
        ]))
        mgr.search = fake_search
        mgr.write_report = AsyncMock(return_value=make_report())

        await collect(mgr.run("q", "", "Tavily", 1, "tid"))
        assert captured_tool["tool"] is tavily_search

        await collect(mgr.run("q", "", "DuckDuckGo", 1, "tid"))
        assert captured_tool["tool"] is duckduckgo_search


# ── ResearchManager.deepen ─────────────────────────────────────────────────────

class TestDeepen:
    @pytest.mark.asyncio
    async def test_deepen_emits_report(self):
        mgr = ResearchManager()
        original = make_report()
        mgr.plan_searches = AsyncMock(return_value=WebSearchPlan(searches=[
            WebSearchItem(query="costos IA", reason="relevante"),
        ]))
        mgr.search = AsyncMock(return_value="nueva info")
        mgr.write_report_deepen = AsyncMock(return_value=make_report(short_summary="Ampliado"))

        events = await collect(mgr.deepen("IA en salud", original, "costos", "DuckDuckGo", 1, "tid"))

        report_evt = next(e for e in events if e["type"] == "report")
        assert report_evt["data"].short_summary == "Ampliado"

    @pytest.mark.asyncio
    async def test_deepen_builds_context_with_original_report(self):
        mgr = ResearchManager()
        original = make_report(markdown_report="# Original\nContenido previo.")
        captured_input = {}

        async def fake_write(input_text, **kw):
            captured_input["text"] = input_text
            return make_report()

        mgr.plan_searches = AsyncMock(return_value=WebSearchPlan(searches=[
            WebSearchItem(query="q", reason="r"),
        ]))
        mgr.search = AsyncMock(return_value="res")
        mgr.write_report_deepen = fake_write

        await collect(mgr.deepen("query", original, "nuevo foco", "DuckDuckGo", 1, "tid"))

        assert "# Original" in captured_input["text"]
        assert "nuevo foco" in captured_input["text"]
