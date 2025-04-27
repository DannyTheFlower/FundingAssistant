import streamlit as st, requests, pandas as pd, datetime as dt


BASE = "http://localhost:8000/api"

st.title("📈Конструктор индексов MOEX")

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

    w_type = st.selectbox("Тип взвешивания", ["equal", "market_cap", "cap_freefloat"], 1)
    base_date = st.date_input("Базовая дата индекса", value=dt.date(Y, Q * 3 - 2, 1))

    if st.button("Создать индекс 🎉", disabled=not selected_ids):
        payload = {
            "name": "DemoIndex",
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
            if s.ok:
                df = pd.DataFrame(s.json())
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
                st.line_chart(df["value"], use_container_width=True)
            else:
                st.error(s.text)