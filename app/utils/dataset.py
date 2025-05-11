import pandas as pd, numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
from utils.garch import fit_garch, get_garch_prices_train


def make_dataset(prices: pd.Series, imoex: pd.Series | None = None):
    df = prices.to_frame("close")
    if imoex is not None:
        df = df.join(imoex.rename("imoex"), how="left")

    df["ret"] = df["close"].pct_change()
    df = df.dropna()

    for lag in range(1, 5):
        df[f"lag_{lag}"] = df["ret"].shift(lag)
        df[f"price_lag_{lag}"] = df["close"].shift(lag)

    df["roll_mean_3"] = df["ret"].rolling(3).mean()
    df["roll_mean_7"] = df["ret"].rolling(7).mean()
    df["roll_std_5"] = df["ret"].rolling(5).std()
    df["roll_std_10"] = df["ret"].rolling(10).std()

    ind_rsi = RSIIndicator(df["close"]).rsi()
    ind_macd = MACD(df["close"]).macd_diff()
    boll = BollingerBands(df["close"])
    df["rsi14"] = ind_rsi
    df["macd"] = ind_macd
    df["bbhigh"] = boll.bollinger_hband()
    df["bblow"] = boll.bollinger_lband()

    df["dow"] = pd.to_datetime(df.index).dayofweek
    df["month"] = pd.to_datetime(df.index).month
    df["year"] = pd.to_datetime(df.index).year

    garch_fit = fit_garch(df["ret"])
    stat_prices = get_garch_prices_train(
        train=df["ret"],
        last_price=df["close"].iloc[0],
        garch_fitted=garch_fit
    )

    df["stat_pred"] = stat_prices
    df["stat_pred_next"] = stat_prices.shift(-1)
    df["close_next"] = df["close"].shift(-1)
    df["resid_next"] = df["close_next"] - df["stat_pred_next"]

    df.dropna(inplace=True)
    return df, garch_fit


def _next_trading_day(d: pd.Timestamp) -> pd.Timestamp:
    d_next = d + pd.Timedelta(days=1)
    while d_next.weekday() >= 5:
        d_next += pd.Timedelta(days=1)
    return d_next


def make_next_row(df: pd.DataFrame) -> pd.DataFrame:
    last = df.iloc[-1]
    new_date = _next_trading_day(last.name)

    row = {
        "close": np.nan,
        "close_next": np.nan,
        "imoex": np.nan,
        "stat_pred": np.nan,
        "stat_pred_next": np.nan,
        "ret": np.nan,
        "resid_next": np.nan,
        "lag_1": last["ret"],
        "price_lag_1": last["close"]
    }

    for lag in range(2, 5):
        row[f"lag_{lag}"] = last[f"lag_{lag-1}"]
        row[f"price_lag_{lag}"] = last[f"price_lag_{lag-1}"]

    recent_rets = df["ret"].tail(10)
    row["roll_mean_3"] = recent_rets.tail(3).mean()
    row["roll_mean_7"] = recent_rets.tail(7).mean()
    row["roll_std_5"] = recent_rets.tail(5).std()
    row["roll_std_10"] = recent_rets.tail(10).std()

    ind_rsi = RSIIndicator(df["close"]).rsi().iloc[-1]
    ind_macd = MACD(df["close"]).macd_diff().iloc[-1]
    boll = BollingerBands(df["close"])
    row["rsi14"] = ind_rsi
    row["macd"] = ind_macd
    row["bbhigh"] = boll.bollinger_hband().iloc[-1]
    row["bblow"] = boll.bollinger_lband().iloc[-1]

    row["dow"] = new_date.weekday()
    row["month"] = new_date.month
    row["year"] = new_date.year

    next_df = pd.DataFrame([row], index=[new_date])
    next_df = next_df[df.columns]
    return next_df
