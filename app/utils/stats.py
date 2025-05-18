import numpy as np, pandas as pd
from typing import Dict

def calc_stats(
    index_ser: pd.Series,
    imoex_ser: pd.Series
) -> Dict:
    df = pd.DataFrame({"idx": index_ser, "imoex": imoex_ser}).ffill().dropna()
    idx, bm = df["idx"], df["imoex"]

    ret_i = idx.pct_change().dropna()
    ret_b = bm.pct_change().dropna()
    ret_i, ret_b = ret_i.align(ret_b, join="inner")

    ann_vol = ret_i.std()*np.sqrt(252)
    ann_ret = ret_i.mean()*252
    sharpe = ann_ret/ann_vol if ann_vol else np.nan
    var95 = np.quantile(ret_i, 0.05)

    roll_max = idx.cummax()
    mdd = ((idx / roll_max) - 1).min()

    ytd = idx.loc[str(idx.index[-1].year)].iloc[-1] / \
          idx.loc[str(idx.index[-1].year)].iloc[0] - 1

    corr = ret_i.corr(ret_b)
    beta = ret_i.cov(ret_b)/ret_b.var()
    te = np.sqrt(((ret_i - ret_b) ** 2).mean())
    ir = (ret_i.mean() - ret_b.mean()) / te if te else np.nan

    return {
        "performance": {
            "ytd": ytd,
            "annual_return": ann_ret,
            "annual_vol": ann_vol,
            "sharpe": sharpe,
            "mdd": mdd,
            "VaR_95": var95
        },
        "vs_imoex": {"corr": corr, "beta": beta, "te": te, "ir": ir}
    }
