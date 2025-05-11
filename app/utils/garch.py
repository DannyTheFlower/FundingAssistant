import pandas as pd, numpy as np
from arch import arch_model


def fit_garch(train: pd.Series):
    model = arch_model(train * 100, p=1, q=1, mean="AR", lags=1, dist="t")
    model = model.fit(disp="off")
    return model


def get_garch_prices_train(train: pd.Series, last_price: float, garch_fitted: arch_model):
    fitted_pct = train * 100 - garch_fitted.resid
    fitted_r = fitted_pct / 100
    prices = last_price * (1 + fitted_r).cumprod()
    return prices


def forecast_prices(last_price: float, garch_fitted: arch_model, horizon: int):
    fc = garch_fitted.forecast(horizon=horizon)
    mu = fc.mean.iloc[-1].values / 100
    prices = last_price * (1 + mu).cumprod()
    vol = np.sqrt(fc.variance.iloc[-1].values) / 100
    return prices, vol
