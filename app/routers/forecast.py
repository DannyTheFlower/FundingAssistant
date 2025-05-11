import pandas as pd, numpy as np, asyncio
from fastapi import APIRouter, HTTPException
from services.price_cache import get_series
from services.benchmark import get_imoex_series
from schemas import SecurityWeight, ForecastRequest, ForecastResponse
from utils.dataset import make_dataset
from utils.catboost import fit_catboost, forecast_catboost, fit_predict_catboost_clf
from utils.tft import fit_tft, forecast_tft


router = APIRouter(prefix="/forecast", tags=["Forecast"])


@router.post("/", response_model=ForecastResponse)
async def forecast(req: ForecastRequest):
    assets = req.assets
    if not assets:
        raise HTTPException(400, "empty assets")

    dfs = await asyncio.gather(*[get_series(a.secid) for a in assets])
    price_tbl = pd.concat(
        [df.set_index("date")["close"].rename(a.secid) for a, df in zip(assets, dfs)],
        axis=1
    ).sort_index().ffill().dropna(how="any")
    shares = pd.Series({a.secid: a.shares for a in assets})
    pf = (price_tbl * shares).sum(axis=1)
    ret = pf.pct_change().dropna()

    imoex_df = await get_imoex_series(pf.index.min(), pf.index.max())
    imoex_ser = imoex_df.set_index("date")["close"]
    df, garch_fit = make_dataset(pf, imoex_ser)

    vol_ann = ret.std() * np.sqrt(252)
    var_95 = np.quantile(ret, 0.05)
    increase_proba = fit_predict_catboost_clf(df)

    horizon = 60
    if req.model == "quality":
        tft_model, ds, enc_df = fit_tft(pf, imoex_ser, horizon, horizon)
        fc, lo_ci, hi_ci = forecast_tft(tft_model, ds, enc_df)
    else:
        cb, feats = fit_catboost(df)
        fc, lo_ci, hi_ci = forecast_catboost(df, garch_fit, cb, feats, horizon)

    f_dates = pd.bdate_range(pf.index[-1] + pd.Timedelta(days=1), periods=horizon).date

    return ForecastResponse(
        history=list(zip(pf.index, pf.values)),
        forecast=list(zip(f_dates, fc)),
        lo95=list(zip(f_dates, lo_ci)),
        hi95=list(zip(f_dates, hi_ci)),
        metrics={
            "annual_volatility": vol_ann,
            "VaR_95": var_95,
            "P_up_60d": increase_proba,
        }
    )