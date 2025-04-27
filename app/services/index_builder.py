import pandas as pd
from datetime import date
from services.moex import load_latest_prices


async def build_weights(
    df_cap: pd.DataFrame,
    weighting: str,
    custom: dict[str, float] | None = None,
) -> dict[str, float]:
    if weighting == "equal":
        w = {s: 1 / len(df_cap) for s in df_cap.secid}
    elif weighting == "market_cap":
        w = (df_cap.cap / df_cap.cap.sum()).to_dict()
    elif weighting == "cap_freefloat":
        w_cap_ff = df_cap.cap * df_cap.free_float / 100
        w = (w_cap_ff / w_cap_ff.sum()).to_dict()
    elif weighting == "custom":
        if not custom:
            raise ValueError("custom_weight dict required")
        total = sum(custom.values())
        w = {k: v / total for k, v in custom.items()}
    else:
        raise ValueError("Unknown weighting")
    return w


async def compute_index_value(weights: dict[str, float]) -> float:
    prices = await load_latest_prices(list(weights))
    return sum(prices[s] * w for s, w in weights.items())


async def compute_series(weights: dict[str, float], date_from: date, date_to: date):
    """Return list[{date,value}] daily using fixed weights."""
    from .moex import candles_bulk
    bulk = await candles_bulk(list(weights), date_from, date_to)
    # build common date index
    all_dates = sorted({d for df in bulk.values() for d in df["date"].unique()})
    series = []
    for d in all_dates:
        val = 0.0
        for s, w in weights.items():
            df = bulk.get(s)
            if df is None:
                continue
            row = df[df.date == d]
            if not row.empty:
                val += row.iloc[0].close * w
        series.append({"date": str(d), "value": val})
    return series
