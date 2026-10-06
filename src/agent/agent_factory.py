"""
Фабрика инициализации агента Platon-RuBond-bot.

Поддерживает:
  - LangGraph pipeline (parse → tools → risk_officer → human_gate → respond)
  - Structured output (AgentFinalResponse)
  - Streaming шагов для Streamlit
  - Chat history (SQLite)
  - Fallback tool-calling agent / SimpleAgentExecutor
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional

from src.agent.prompts import BOND_AGENT_SYSTEM_PROMPT
from src.agent.schemas import AgentFinalResponse
from src.agent.tools import get_all_tools
from src.config import Config
from src.memory.sql_history import SessionChatHistory, SQLiteHistoryManager
from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.agent.factory")


class PlatonAgentFactory:
    """
    Создание агента Platon-RuBond-bot.

    Пример::

        factory = PlatonAgentFactory()
        # Graph pipeline (рекомендуется)
        result = factory.run("Проанализируй SU26238RMFS7", session_id="u1")
        print(result.summary)

        # Streaming для Streamlit
        for step, state in factory.stream("Какая ставка ЦБ?", session_id="u1"):
            st.write(step, state.get("intermediate"))
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self._history_manager = SQLiteHistoryManager(db_path=self.config.history_db)
        self._graph = None

    def _get_graph(self):
        if self._graph is None:
            from src.agent.graph import get_graph_runner
            self._graph = get_graph_runner()
        return self._graph

    # ------------------------------------------------------------------
    # Primary API: graph pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        user_input: str,
        session_id: str = "default",
        *,
        human_decision: Optional[str] = None,
    ) -> AgentFinalResponse:
        """
        Полный прогон pipeline. Возвращает AgentFinalResponse.
        human_decision: "approve" | "reject" для human-in-the-loop.
        """
        from src.agent.observability import get_tracer

        history = SessionChatHistory(self._history_manager, session_id)
        history.add_user_message(user_input)

        state: Dict[str, Any] = {
            "input": user_input,
            "session_id": session_id,
            "intermediate": [],
            "needs_human": False,
        }
        if human_decision:
            state["human_decision"] = human_decision

        tracer = get_tracer()
        with tracer.start_span("agent_run", session_id=session_id, input=user_input[:100]):
            runner = self._get_graph()
            if hasattr(runner, "invoke"):
                # LangGraph compiled graph or PipelineRunner
                out_state = runner.invoke(state)
            else:
                out_state = state

        final_data = (out_state or {}).get("final") or {}
        try:
            response = AgentFinalResponse(**final_data)
        except Exception:
            response = AgentFinalResponse(
                summary=str(out_state),
                raw_output=str(out_state),
            )

        history.add_ai_message(response.to_ui_text())
        return response

    def stream(
        self,
        user_input: str,
        session_id: str = "default",
        *,
        human_decision: Optional[str] = None,
    ) -> Generator[tuple, None, None]:
        """
        Streaming шагов pipeline (улучшение 4).
        Yields: (node_name: str, partial_state: dict)

        В Streamlit::
            for step, st_data in factory.stream(prompt):
                st.status(step)
                if st_data.get("final"):
                    st.write(AgentFinalResponse(**st_data["final"]).to_ui_text())
        """
        history = SessionChatHistory(self._history_manager, session_id)
        history.add_user_message(user_input)

        state: Dict[str, Any] = {
            "input": user_input,
            "session_id": session_id,
            "intermediate": [],
            "needs_human": False,
        }
        if human_decision:
            state["human_decision"] = human_decision

        runner = self._get_graph()

        # PipelineRunner has .stream
        if hasattr(runner, "stream") and not hasattr(runner, "get_graph"):
            final_state = None
            for step_name, partial in runner.stream(state):
                yield step_name, partial
                final_state = partial
            if final_state and final_state.get("final"):
                try:
                    resp = AgentFinalResponse(**final_state["final"])
                    history.add_ai_message(resp.to_ui_text())
                except Exception:
                    pass
            return

        # LangGraph: stream events if available
        try:
            final_state = None
            for event in runner.stream(state):
                # event is dict node_name → state
                if isinstance(event, dict):
                    for node_name, partial in event.items():
                        yield node_name, partial
                        final_state = partial
            if final_state and isinstance(final_state, dict) and final_state.get("final"):
                try:
                    resp = AgentFinalResponse(**final_state["final"])
                    history.add_ai_message(resp.to_ui_text())
                except Exception:
                    pass
            return
        except Exception as exc:
            logger.warning("graph.stream failed (%s), fallback invoke", exc)

        # Fallback: single invoke
        response = self.run(user_input, session_id, human_decision=human_decision)
        yield "respond", {"final": response.model_dump()}

    # ------------------------------------------------------------------
    # Legacy: create_agent (AgentExecutor-compatible)
    # ------------------------------------------------------------------

    def create_agent(
        self,
        session_id: str = "default",
        *,
        verbose: bool = False,
        use_graph: bool = True,
    ) -> Any:
        """
        Возвращает объект с .invoke({"input": "..."}) → {"output": "..."}.
        По умолчанию оборачивает graph pipeline.
        """
        if use_graph:
            return _GraphExecutor(self, session_id)

        tools = get_all_tools()
        llm = self.build_llm()
        history = SessionChatHistory(self._history_manager, session_id)

        if isinstance(llm, _MockLLM):
            return _SimpleAgentExecutor(tools=tools, history=history, llm=llm)

        try:
            return self._build_tool_calling_agent(llm, tools, history, verbose)
        except Exception as exp:
            logger.warning("tool-calling agent failed (%s)", exp)
            return _SimpleAgentExecutor(tools=tools, history=history, llm=llm)

    def build_llm(self) -> Any:
        api_key = self.config.aitunnel_api_key
        if not api_key:
            logger.warning("AITUNNEL_API_KEY не задан — MockLLM")
            return _MockLLM()
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.config.llm_model,
                api_key=api_key,
                base_url=self.config.aitunnel_base_url,
                temperature=self.config.agent_temperature,
            )
        except Exception as exc:
            logger.error("ChatOpenAI init failed: %s", exc)
            return _MockLLM()

    def _build_tool_calling_agent(self, llm, tools, history, verbose):
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", BOND_AGENT_SYSTEM_PROMPT),
                MessagesPlaceholder("chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ]
        )
        try:
            from langchain.agents import create_tool_calling_agent
            agent_runnable = create_tool_calling_agent(llm, tools, prompt)
        except ImportError:
            from langchain.agents import create_openai_tools_agent
            agent_runnable = create_openai_tools_agent(llm, tools, prompt)

        from langchain.agents import AgentExecutor
        executor = AgentExecutor(
            agent=agent_runnable,
            tools=tools,
            verbose=verbose,
            max_iterations=self.config.agent_max_iterations,
            handle_parsing_errors=True,
        )
        return _HistoryAwareExecutor(executor, history)

    def get_history_manager(self) -> SQLiteHistoryManager:
        return self._history_manager


class _GraphExecutor:
    """Адаптер graph → invoke({"input"}) интерфейс."""

    def __init__(self, factory: PlatonAgentFactory, session_id: str) -> None:
        self.factory = factory
        self.session_id = session_id

    def invoke(self, inputs: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        user_input = inputs.get("input", "")
        human_decision = inputs.get("human_decision") or kwargs.get("human_decision")
        response = self.factory.run(
            user_input, self.session_id, human_decision=human_decision
        )
        return {
            "output": response.to_ui_text(),
            "structured": response.model_dump(),
        }

    def stream(self, inputs: Dict[str, Any], **kwargs: Any):
        user_input = inputs.get("input", "")
        human_decision = inputs.get("human_decision")
        for step, state in self.factory.stream(
            user_input, self.session_id, human_decision=human_decision
        ):
            yield step, state


class _HistoryAwareExecutor:
    def __init__(self, executor: Any, history: SessionChatHistory) -> None:
        self.executor = executor
        self.history = history

    def invoke(self, inputs: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        user_input = inputs.get("input", "")
        self.history.add_user_message(user_input)
        chat_history = self.history.messages
        if chat_history and getattr(chat_history[-1], "content", None) == user_input:
            chat_history = chat_history[:-1]
        result = self.executor.invoke({**inputs, "chat_history": chat_history}, **kwargs)
        if result.get("output"):
            self.history.add_ai_message(str(result["output"]))
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.executor, name)


class _MockLLM:
    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        return type("Msg", (), {"content": "[MockLLM] Укажите AITUNNEL_API_KEY"})()

    def bind_tools(self, tools: list) -> "_MockLLM":
        return self


class _SimpleAgentExecutor:
    def __init__(self, tools: list, history: SessionChatHistory, llm: Any) -> None:
        self.tools = {getattr(t, "name", t.__name__): t for t in tools}
        self.history = history
        self.llm = llm

    def invoke(self, inputs: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        # Делегируем в graph для единообразия
        from src.agent.agent_factory import PlatonAgentFactory
        # fallback local routing was previous behavior; prefer graph
        factory = PlatonAgentFactory()
        resp = factory.run(inputs.get("input", ""), session_id="simple")
        return {"output": resp.to_ui_text(), "structured": resp.model_dump()}


class AgentFactory(PlatonAgentFactory):
    """Алиас."""
    pass
