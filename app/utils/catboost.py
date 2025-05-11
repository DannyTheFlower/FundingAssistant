import pandas as pd, numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor, Pool
from utils.dataset import make_next_row
from utils.garch import forecast_prices


default_params_reg = {
    'subsample': 0.6,
    'random_strength': 2.0,
    'learning_rate': 0.1,
    'l2_leaf_reg': 9,
    'iterations': 1000,
    'depth': 10,
    'border_count': 32,
    'bagging_temperature': 1.0,
    'loss_function': 'RMSE',
    'eval_metric': 'RMSE',
    'verbose': 0
}

default_params_clf = {
    'iterations': 2000,
    'depth': 8,
    'learning_rate': 0.01,
    'loss_function': 'CrossEntropy',
    'eval_metric': 'F1',
    'random_strength': 1,
    'l2_leaf_reg': 4,
    'bootstrap_type': 'Bayesian',
    'bagging_temperature': 0.3,
    'verbose': 0
}


def fit_catboost(df: pd.DataFrame, params: dict | None = None):
    if params is None:
        params = default_params_reg

    features = [c for c in df.columns if c not in ("imoex", "close_next", "stat_pred_next", "resid_next")]
    target = "resid_next"

    ds = Pool(df[features], df[target])
    model = CatBoostRegressor(**params)
    model.fit(ds)
    return model, features


def forecast_catboost(
    df: pd.DataFrame,
    garch_fit,
    cb_model: CatBoostRegressor,
    cb_features: list[str],
    horizon: int = 60
):
    last_price = df.iloc[-1]["close"]
    preds, lo, hi = [], [], []

    garch_prices, vol = forecast_prices(last_price, garch_fit, horizon)

    for k in range(horizon):
        last_price = df.iloc[-1]["close"]
        feats = df.iloc[-1][cb_features]

        stat_pred = garch_prices[k]
        resid_hat = cb_model.predict(feats)
        price_next = stat_pred + resid_hat

        preds.append(price_next)
        lo.append(price_next - 1.96 * vol[k] * last_price)
        hi.append(price_next + 1.96 * vol[k] * last_price)

        df = pd.concat([df, make_next_row(df)])
        df.at[df.index[-1], "close"] = price_next
        df.at[df.index[-1], "ret"] = (price_next - last_price) / last_price
        df.at[df.index[-1], "stat_pred"] = stat_pred

    return np.array(preds), np.array(lo), np.array(hi)


def fit_predict_catboost_clf(df: pd.DataFrame, params: dict | None = None):
    if params is None:
        params = default_params_clf

    last_row = df.iloc[-1].copy()
    df = df.copy()

    df["close_next_60"] = df["close"].shift(60)
    df = df.dropna()
    df["increased"] = (df["close_next_60"] > df["close"]).astype(int)

    features = [c for c in df.columns if c not in ("close_next", "stat_pred_next", "resid_next", "close_next_60", "increased")]
    target = "increased"

    X, y = df[features], df[target]
    ds = Pool(X, y)
    model = CatBoostClassifier(**params)
    model.fit(ds)

    pred = model.predict(last_row[features])
    proba = model.predict_proba(last_row[features])[1]
    tp = ((y == 1) & (pred == 1)).sum()
    fn = ((y == 1) & (pred == 0)).sum()
    real_proba = tp / (tp + fn) * proba + fn / (tp + fn) * (1 - proba)

    return real_proba
