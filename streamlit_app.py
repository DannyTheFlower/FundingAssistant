import streamlit as st, requests, pandas as pd, datetime as dt, altair as alt


BASE = "http://localhost:8000/api"

weightings = {
    "equal": "Равные веса",
    "market_cap": "По капитализации",
    "cap_freefloat": "Капитализация × Free‑float",
    "cap_divyield": "Капитализация × Дивдоходность"
}
weightings_inv = {v: k for k, v in weightings.items()}
metrics_map = {
    "ytd": "Доходность с начала года (YTD)",
    "annual_return": "Годовая доходность",
    "annual_vol": "Годовая волатильность",
    "sharpe": "Коэффициент Шарпа",
    "mdd": "Максимальная просадка (MDD)",
    "VaR_95": "VaR 95% (риск потерь)",
    "corr": "Корреляция с IMOEX",
    "beta": "Бета относительно IMOEX",
    "te": "Трек-ошибка (Tracking Error)",
    "ir": "Коэффициент информации (Information Ratio)"
}
for k, v in {"report_ready": False, "report_bytes":  None}.items():
    st.session_state.setdefault(k, v)

st.set_page_config(page_title="MOEX Index Lab", layout="wide")
tabs = st.tabs(["🛠️Конструктор индексов", "🔮Прогнозирование доходности"])

with tabs[0]:
    st.title("📈Конструктор индексов MOEX")

    st.subheader("Найти индекс")
    query = st.text_input("Поиск по ID или названию", placeholder="MOEX_Utilities")
    if st.button("🔍 Найти"):
        r = requests.get(f"{BASE}/index/indices", params={"q": query})
        if r.ok:
            res_df = pd.DataFrame(r.json())
            if res_df.empty:
                st.info("Ничего не найдено")
            else:
                st.dataframe(res_df[["id", "name", "base_date", "weighting"]])
        else:
            st.error(r.text)

    st.markdown("---")

    st.subheader("Создать новый индекс")

    colY, colQ = st.columns(2)
    Y = colY.number_input("Год", value=dt.date.today().year, step=1)
    Q = colQ.selectbox("Квартал", [1, 2, 3, 4], index=0)

    if "securities_df" not in st.session_state:
        st.session_state["securities_df"] = pd.DataFrame(columns=["ID", "Name"])

    if st.button("Получить данные"):
        with st.spinner("Загружается список бумаг…"):
            r = requests.get(f"{BASE}/securities", params={"year": Y, "quarter": Q})
            r.raise_for_status()
            st.session_state["securities_df"] = pd.DataFrame(r.json(), columns=["ID", "Name"])

    if not st.session_state["securities_df"].empty:
        df_sec = st.session_state["securities_df"]
        choices = st.multiselect(
            "Выберите бумаги:",
            options=[f"{row.ID} – {row.Name}" for row in df_sec.itertuples()],
        )
        selected_ids = [c.split(" – ")[0] for c in choices]

        index_name = st.text_input("Название индекса", placeholder="My_Dividend_Stars")
        w_type_human = st.selectbox("Тип взвешивания", list(weightings_inv), 1)
        w_type = weightings_inv[w_type_human]
        base_date = st.date_input("Базовая дата индекса", value=dt.date(Y, Q * 3 - 2, 1))

        if st.button("Создать индекс 🎉", disabled=not selected_ids):
            payload = {
                "name": index_name,
                "base_date": str(base_date),
                "weighting": w_type,
                "securities": [{"secid": s} for s in selected_ids],
            }
            res = requests.post(f"{BASE}/index", json=payload)
            if res.ok:
                info = res.json()
                st.session_state["index_id"] = info["id"]
                st.success(f"Индекс создан, ID={info['id']}, базовое значение={info['base_value']:.2f}")
            else:
                st.error(res.text)

    if "index_id" in st.session_state:
        colF, colT = st.columns(2)
        d_from = colF.date_input("С", value=dt.date.today() - dt.timedelta(days=30))
        d_till = colT.date_input("По", value=dt.date.today())
        if st.button("Показать динамику"):
            with st.spinner("Расчёт…"):
                s = requests.get(
                    f"{BASE}/index/{st.session_state['index_id']}/series",
                    params={"from": str(d_from), "till": str(d_till)},
                )
                if s.ok and s.json():
                    df = pd.DataFrame(s.json())
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")

                    left, right = st.columns(2)

                    left.subheader(st.session_state.get("index_name", "Ваш индекс"))
                    left.line_chart(
                        df[["value"]].rename(columns={"value": st.session_state.get("index_name", "index")}),
                        use_container_width=True
                    )

                    right.subheader("IMOEX")
                    right.line_chart(
                        df[["imoex"]].rename(columns={"imoex": "IMOEX"}),
                        use_container_width=True
                    )
                else:
                    st.warning(s.text)

    if "index_id" in st.session_state:
        if st.button("Паспорт индекса"):
            r = requests.get(f"{BASE}/index/{st.session_state['index_id']}/stats")
            if r.ok:
                stats = r.json()

                with st.expander("Основные характеристики", expanded=True):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("YTD", f"{stats['performance']['ytd']:.2%}")
                    col2.metric("Annual Vol", f"{stats['performance']['annual_vol']:.2%}")
                    col3.metric("Sharpe", f"{stats['performance']['sharpe']:.2f}")

                col21, col22 = st.columns(2)

                with col21:
                    with st.expander("Риск-метрики"):
                        st.table(pd.Series(stats['performance']).to_frame("value").rename(metrics_map))

                with col22:
                    with st.expander("Относительно IMOEX"):
                        st.table(pd.Series(stats['vs_imoex']).to_frame("value").rename(metrics_map))
            else:
                st.error(r.text)

with tabs[1]:
    st.header("🔮Прогнозирование доходности портфеля")

    if "securities_df" not in st.session_state or st.session_state["securities_df"].empty:
        st.info("Сначала на вкладке «Конструктор» нажмите «Получить бумаги»")

    df_sec = st.session_state["securities_df"]
    if not df_sec.empty:
        st.subheader("Выбор активов и количеств акций")
        picks = st.multiselect(
            "Бумаги:",
            options=[f"{row.ID} – {row.Name}" for row in df_sec.itertuples()],
        )
        weights = {}
        for p in picks:
            secid = p.split(" – ")[0]
            weights[secid] = st.number_input(
                f"{secid} — кол-во акций", min_value=1, value=10, step=1
            )
        model_choice = st.radio(
            "Алгоритм",
            ["Быстрее (GARCH + CatBoost)", "Качественнее (TFT)"],
            horizontal=True
        )
        model_code = "fast" if model_choice.startswith("Быстрее") else "quality"

        if st.button("Смоделировать", disabled=not weights):
            payload = {"assets": [{"secid": s, "shares": n} for s, n in weights.items()],
                       "model": model_code}
            with st.spinner("Обучаем модель..."):
                r = requests.post(f"{BASE}/forecast", json=payload)
            if r.ok:
                data = r.json()
                df_h = pd.DataFrame(data["history"], columns=["date", "value"]).set_index("date")
                df_f = pd.DataFrame(data["forecast"], columns=["date", "value"]).set_index("date")
                df_lo = pd.DataFrame(data["lo95"], columns=["date", "value"]).set_index("date")
                df_hi = pd.DataFrame(data["hi95"], columns=["date", "value"]).set_index("date")

                left, right = st.columns(2)
                left.subheader("История портфеля")
                left.line_chart(df_h)

                right.subheader("Прогноз на 60 торговых дней")
                base = alt.Chart(df_f.reset_index()).encode(x="date:T")
                band = alt.Chart(
                    pd.concat([df_lo, df_hi], axis=1, keys=["lo", "hi"]).reset_index()
                ).mark_area(opacity=0.2).encode(x="date:T", y="lo:Q", y2="hi:Q")
                line = base.mark_line(color="#1f77b4").encode(y="value:Q")
                right.altair_chart(band + line, use_container_width=True)

                col1, col2, col3 = st.columns(3)
                col1.metric("Среднегодовая волатильность", f"{data['metrics']['annual_volatility']:.2%}")
                col2.metric("VaR 95%", f"{data['metrics']['VaR_95']:.2%}")
                col3.metric("Вероятность роста портфеля через 60 дней", f"{data['metrics']['P_up_60d']:.1%}")
            else:
                st.error(r.text)

            with st.spinner("Создаём отчёт..."):
                r = requests.post(f"{BASE}/report", json=payload)
                r.raise_for_status()
                st.session_state.report_bytes = r.content
                st.session_state.report_ready = True

        if st.session_state.report_ready:
            st.download_button(
                "Скачать отчёт",
                data=st.session_state.report_bytes,
                file_name="portfolio_report.html",
                mime="text/html",
            )
