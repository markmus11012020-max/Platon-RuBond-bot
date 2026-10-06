"""
Вкладки графического интерфейса Streamlit.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import streamlit as st

from src.ui.sidebar import SidebarConfig
from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.ui.tabs")


class TabsRenderer:
    """
    Рендерер четырёх вкладок оператора.
    Бизнес-логика вызывается через фабрики/менеджеры, UI только отображает.
    """

    def __init__(self, config: SidebarConfig) -> None:
        self.config = config

    def render(self) -> None:
        tab_chat, tab_market, tab_portfolio, tab_news = st.tabs(
            [
                "💬 Интеллектуальный Чат",
                "📊 Анализ рынка и Поиск",
                "📁 Мой Портфель",
                "📰 ИИ-Мониторинг новостей",
            ]
        )
        with tab_chat:
            self._render_chat()
        with tab_market:
            self._render_market()
        with tab_portfolio:
            self._render_portfolio()
        with tab_news:
            self._render_news()

    # ==================================================================
    # Tab 1: Chat
    # ==================================================================

    def _render_chat(self) -> None:
        st.subheader("Диалог с Platon-RuBond-bot")
        st.caption(
            "Задавайте вопросы об облигациях, ставке ЦБ, новостях. "
            "Агент использует tools + Risk Officer."
        )

        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = self._load_history()

        # История
        for msg in st.session_state.chat_messages:
            role = msg.get("role", "assistant")
            with st.chat_message("user" if role in ("human", "user") else "assistant"):
                st.markdown(msg.get("content", ""))

        prompt = st.chat_input("Спросите про ISIN, YTM, ставку ЦБ, новости…")
        if not prompt:
            return

        st.session_state.chat_messages.append({"role": "human", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            status = st.status("Агент думает…", expanded=True)
            steps_log: List[str] = []

            try:
                from src.agent.agent_factory import PlatonAgentFactory
                from src.agent.schemas import AgentFinalResponse
                from src.config import Config

                cfg = Config()
                cfg.llm_model = self.config.model
                cfg.agent_temperature = self.config.temperature
                factory = PlatonAgentFactory(config=cfg)

                human_decision = None
                low = prompt.strip().lower()
                if low in ("approve", "reject", "одобрить", "отклонить"):
                    human_decision = "approve" if low in ("approve", "одобрить") else "reject"

                final_resp: Optional[AgentFinalResponse] = None
                for step_name, partial in factory.stream(
                    prompt,
                    session_id=self.config.session_id,
                    human_decision=human_decision,
                ):
                    steps_log.append(step_name)
                    status.write(f"→ `{step_name}`")
                    if partial.get("final"):
                        try:
                            final_resp = AgentFinalResponse(**partial["final"])
                        except Exception:
                            pass

                status.update(label="Готово", state="complete")
                if final_resp is None:
                    final_resp = factory.run(
                        prompt,
                        session_id=self.config.session_id,
                        human_decision=human_decision,
                    )

                text = final_resp.to_ui_text()
                placeholder.markdown(text)

                if final_resp.needs_human_input:
                    st.warning(final_resp.human_prompt or "Требуется подтверждение (approve/reject)")

                if final_resp.bond_report:
                    with st.expander("Структурированный отчёт"):
                        st.json(final_resp.bond_report.model_dump())

                if final_resp.risk_review:
                    with st.expander("Risk Officer"):
                        st.json(final_resp.risk_review.model_dump())

                st.session_state.chat_messages.append(
                    {"role": "ai", "content": text}
                )
            except Exception as exc:
                logger.exception("chat failed")
                status.update(label="Ошибка", state="error")
                err = f"Ошибка агента: {exc}"
                placeholder.error(err)
                st.session_state.chat_messages.append({"role": "ai", "content": err})

    def _load_history(self) -> List[Dict[str, str]]:
        try:
            from src.memory.sql_history import SQLiteHistoryManager
            from src.config import Config

            hm = SQLiteHistoryManager(db_path=Config().history_db)
            rows = hm.get_history(self.config.session_id, limit=40)
            hm.close()
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        except Exception:
            return []

    # ==================================================================
    # Tab 2: Market analysis
    # ==================================================================

    def _render_market(self) -> None:
        st.subheader("Анализ облигации")
        col_in, col_btn = st.columns([3, 1])
        with col_in:
            secid = st.text_input(
                "ISIN / SECID",
                placeholder="Например: SU26238RMFS7 или RU000A105XX3",
                key="market_secid",
            )
        with col_btn:
            st.write("")  # spacer
            st.write("")
            run = st.button("Анализировать", type="primary", use_container_width=True)

        if not run or not secid:
            st.info("Введите SECID/ISIN и нажмите «Анализировать».")
            return

        with st.spinner("Запрос к MOEX + расчёт YTM…"):
            try:
                from src.data_providers.moex_api import MoexParser
                from src.analytics.bond_math import BondAnalyzer

                parser = MoexParser()
                analyzer = BondAnalyzer()
                raw = parser.fetch_data(secid.strip())
                parsed = parser.parse_data(raw)
                if not parsed:
                    st.error(f"Нет данных по `{secid}`. Проверьте код или доступ к ISS MOEX.")
                    with st.expander("Сырой ответ"):
                        st.json(raw)
                    return

                bond = dict(parsed[0])
                # Фильтр рейтинга (если есть)
                filtered = analyzer.filter_by_risk(
                    [bond], max_risk_level=self.config.min_rating
                )
                passed_filter = len(filtered) > 0

                ytm = analyzer.calculate_ytm(bond)
                simple = analyzer.calculate_simple_ytm(bond)
                cy = analyzer.calculate_current_yield(bond)
                floater = None
                ct = (bond.get("coupon_type") or "").lower()
                if "флоат" in ct or "float" in ct or "перемен" in ct:
                    floater = analyzer.estimate_floater_yield(bond, self.config.key_rate)
                credit_spread = analyzer.calculate_credit_spread(bond, self.config.key_rate)
                z_spread = analyzer.calculate_z_spread(bond, self.config.key_rate)

                st.markdown(f"### {bond.get('shortname') or bond.get('isin') or secid}")
                if not passed_filter:
                    st.warning(
                        f"Рейтинг не проходит порог **{self.config.min_rating}** "
                        f"(или рейтинг неизвестен)."
                    )

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Цена", self._fmt_price(bond.get("current_price")))
                m2.metric("Номинал", self._fmt_num(bond.get("face_value")))
                m3.metric(
                    "YTM",
                    f"{ytm*100:.2f}%" if ytm is not None else "n/a",
                )
                m4.metric(
                    "Тек. доходность",
                    f"{cy*100:.2f}%" if cy is not None else "n/a",
                )

                m5, m6, m7, m8 = st.columns(4)
                m5.metric("Купон, ₽", self._fmt_num(bond.get("nearest_coupon_value")))
                m6.metric("Период, дн.", str(bond.get("coupon_period") or "—"))
                m7.metric("Тип купона", bond.get("coupon_type") or "—")
                m8.metric(
                    "Флоатер est.",
                    f"{floater*100:.2f}%" if floater is not None else "—",
                )

                c1, c2, c3 = st.columns(3)
                c1.metric("Погашение", bond.get("maturity_date") or "—")
                c2.metric("Оферта", bond.get("offer_date") or "—")
                c3.metric("ISIN", bond.get("isin") or "—")

                s1, s2 = st.columns(2)
                s1.metric(
                    "Credit spread",
                    f"{credit_spread*100:.2f} п.п." if credit_spread is not None else "—",
                )
                s2.metric(
                    "Z-spread",
                    f"{z_spread*100:.2f} п.п." if z_spread is not None else "—",
                )

                with st.expander("Все поля"):
                    st.dataframe(
                        {
                            "Поле": list(bond.keys()),
                            "Значение": [str(v) for v in bond.values()],
                        },
                        use_container_width=True,
                        hide_index=True,
                    )
            except Exception as exc:
                logger.exception("market analysis failed")
                st.error(f"Ошибка анализа: {exc}")

    # ==================================================================
    # Tab 3: Portfolio
    # ==================================================================

    def _render_portfolio(self) -> None:
        st.subheader("Портфель облигаций")

        pm = self._get_portfolio_manager()

        with st.form("add_position_form", clear_on_submit=True):
            st.markdown("**Добавить позицию**")
            c1, c2, c3 = st.columns(3)
            with c1:
                isin = st.text_input("ISIN", placeholder="RU000A105XX3")
            with c2:
                qty = st.number_input("Количество", min_value=0.0, value=1.0, step=1.0)
            with c3:
                price = st.number_input(
                    "Цена покупки (% номинала)",
                    min_value=0.01,
                    value=100.0,
                    step=0.1,
                )
            c4, c5 = st.columns(2)
            with c4:
                issuer = st.text_input("Эмитент", value="")
            with c5:
                sector = st.text_input("Сектор", value="")
            submitted = st.form_submit_button("Добавить", type="primary")

        if submitted:
            ok = pm.add_to_portfolio(
                isin=isin.strip(),
                quantity=qty,
                purchase_price=price,
                issuer=issuer or "unknown",
                sector=sector or "unknown",
            )
            if ok:
                st.success(f"Позиция {isin} добавлена / увеличена")
            else:
                st.error("Не удалось добавить позицию (проверьте ISIN, qty, price)")

        positions = pm.get_positions()
        if not positions:
            st.info("Портфель пуст. Добавьте первую бумагу.")
            return

        st.markdown("**Позиции**")
        st.dataframe(positions, use_container_width=True, hide_index=True)

        # Метрики: подтягиваем рыночные данные где возможно
        market_data = self._enrich_positions(positions)
        metrics = pm.calculate_portfolio_metrics(
            market_data, tax_rate=self.config.tax_rate
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Рыночная стоимость", f"{metrics['total_market_value']:,.0f} ₽")
        m2.metric("Себестоимость", f"{metrics['total_cost']:,.0f} ₽")
        m3.metric("PnL", f"{metrics['pnl']:,.0f} ₽")
        ytm = metrics.get("weighted_ytm")
        m4.metric(
            "Ср. YTM",
            f"{ytm*100:.2f}%" if ytm is not None else "n/a",
        )

        n1, n2 = st.columns(2)
        ytm_net = metrics.get("weighted_ytm_net")
        n1.metric(
            "YTM net (после НДФЛ)",
            f"{ytm_net*100:.2f}%" if ytm_net is not None else "n/a",
        )
        n2.metric("Позиций", metrics["positions_count"])

        if not metrics.get("diversification_ok", True):
            st.error("Нарушена диверсификация:")
            for w in metrics.get("concentration_warnings") or []:
                st.markdown(f"- {w}")
        else:
            st.success("Диверсификация в пределах лимита")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Доли по ISIN**")
            weights = metrics.get("weights") or {}
            if weights:
                st.bar_chart({"Доля": weights})
            st.markdown("**Эмитенты**")
            st.json(metrics.get("issuer_weights") or {})
        with col_b:
            st.markdown("**Купонный календарь (gross)**")
            cal = metrics.get("coupon_calendar") or {}
            if cal:
                st.bar_chart({"Купон, ₽": cal})
            else:
                st.caption("Нет данных для календаря (нужны купоны с MOEX)")
            st.markdown("**Купонный календарь (net)**")
            cal_n = metrics.get("coupon_calendar_net") or {}
            if cal_n:
                st.bar_chart({"Купон net, ₽": cal_n})

        if st.button("Очистить портфель"):
            pm.clear()
            st.rerun()

    def _get_portfolio_manager(self):
        from src.analytics.portfolio import PortfolioManager
        from src.config import Config

        if "portfolio_manager" not in st.session_state:
            cfg = Config()
            st.session_state.portfolio_manager = PortfolioManager(
                max_position_weight=self.config.max_position_weight,
                db_path=cfg.portfolio_db,
                tax_rate=self.config.tax_rate,
                auto_load=True,
            )
        pm = st.session_state.portfolio_manager
        pm.max_position_weight = self.config.max_position_weight
        pm.tax_rate = self.config.tax_rate
        return pm

    def _enrich_positions(self, positions: List[Dict]) -> List[Dict]:
        """Пытается подтянуть current_price/ytm с MOEX для метрик."""
        from src.data_providers.moex_api import MoexParser
        from src.analytics.bond_math import BondAnalyzer

        parser = MoexParser()
        analyzer = BondAnalyzer()
        result = []
        for pos in positions:
            isin = pos.get("isin") or ""
            entry = {
                "isin": isin,
                "current_price": pos.get("purchase_price"),
                "face_value": 1000.0,
                "nearest_coupon_value": None,
                "coupon_period": 182,
            }
            try:
                raw = parser.fetch_data(isin)
                parsed = parser.parse_data(raw)
                if parsed:
                    b = parsed[0]
                    entry.update(
                        {
                            "current_price": b.get("current_price") or entry["current_price"],
                            "face_value": b.get("face_value") or 1000.0,
                            "nearest_coupon_value": b.get("nearest_coupon_value"),
                            "coupon_period": b.get("coupon_period") or 182,
                            "next_coupon_date": b.get("offer_date"),
                        }
                    )
                    entry["ytm"] = analyzer.calculate_ytm(b)
            except Exception:
                pass
            result.append(entry)
        return result

    # ==================================================================
    # Tab 4: News monitoring
    # ==================================================================

    def _render_news(self) -> None:
        st.subheader("ИИ-мониторинг новостей долгового рынка")
        query = st.text_input(
            "Запрос",
            value="облигации выпуск оферта",
            key="news_query",
        )
        col1, col2 = st.columns([1, 3])
        with col1:
            run = st.button("Обновить ленту", type="primary")

        if not run and "news_cache" not in st.session_state:
            st.info("Нажмите «Обновить ленту» для загрузки новостей.")
            return

        if run:
            with st.spinner("RSS + DuckDuckGo + RAG…"):
                try:
                    from src.data_providers.news_scraper import NewsParser
                    from src.memory.pinecone_store import PineconeMemoryManager
                    from src.config import Config

                    parser = NewsParser()
                    raw = parser.fetch_data(query)
                    news = parser.parse_data(raw)

                    # Индексируем в Pinecone / offline store для RAG
                    cfg = Config()
                    pm = PineconeMemoryManager(
                        api_key=cfg.pinecone_api_key,
                        environment=cfg.pinecone_env,
                        index_name=cfg.pinecone_index,
                        aitunnel_api_key=cfg.aitunnel_api_key,
                        aitunnel_base_url=cfg.aitunnel_base_url,
                    )
                    chunks = [
                        f"{n.get('title', '')}. {n.get('text', '')}" for n in news[:20]
                    ]
                    meta = [
                        {
                            "source": n.get("source", ""),
                            "date": n.get("date", ""),
                            "link": n.get("link", ""),
                            "title": n.get("title", "")[:200],
                        }
                        for n in news[:20]
                    ]
                    if chunks:
                        pm.upsert_document_vectors(chunks, metadata=meta)

                    rag_hits = pm.similarity_search(query, top_k=5)

                    # Простая «суммаризация»: top-N заголовков
                    summary_lines = [f"• {n.get('title', '')}" for n in news[:8]]
                    summary = "Ключевые заголовки:\n" + "\n".join(summary_lines)

                    st.session_state.news_cache = {
                        "news": news,
                        "rag_hits": rag_hits,
                        "summary": summary,
                        "query": query,
                    }
                except Exception as exc:
                    logger.exception("news tab failed")
                    st.error(f"Ошибка загрузки новостей: {exc}")
                    return

        data = st.session_state.get("news_cache") or {}
        news = data.get("news") or []
        rag_hits = data.get("rag_hits") or []
        summary = data.get("summary") or ""

        st.markdown("#### Краткое саммари")
        st.markdown(summary or "_нет данных_")

        st.markdown("#### RAG (Pinecone / offline)")
        if rag_hits:
            for i, h in enumerate(rag_hits, 1):
                score = h.get("score")
                score_s = f"{score:.3f}" if isinstance(score, (int, float)) else "—"
                with st.expander(f"#{i} score={score_s}"):
                    st.write(h.get("text", "")[:800])
                    st.caption(str(h.get("metadata") or {}))
        else:
            st.caption("RAG-хитов нет (индекс пуст или offline).")

        st.markdown(f"#### Лента ({len(news)})")
        for n in news[:25]:
            title = n.get("title") or "Без заголовка"
            with st.expander(f"{title[:120]}"):
                st.write(n.get("text") or "")
                st.caption(
                    f"{n.get('date', '')} · {n.get('source', '')} · {n.get('link', '')}"
                )

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _fmt_num(v: Any) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):,.2f}"
        except (TypeError, ValueError):
            return str(v)

    @staticmethod
    def _fmt_price(v: Any) -> str:
        if v is None:
            return "—"
        try:
            f = float(v)
            if f <= 200:
                return f"{f:.2f}%"
            return f"{f:,.2f} ₽"
        except (TypeError, ValueError):
            return str(v)
