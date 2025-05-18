from pathlib import Path
from typing import Optional

import pandas as pd
import quantstats as qs

qs.extend_pandas()


def generate_report(
    prices: pd.Series,
    benchmark: Optional[pd.Series] = None,
    out_path: Path | str = Path("/data/portfolio_report.pdf"),
) -> Path:
    out_path = Path(out_path)
    rets = prices.pct_change().dropna()
    rets.index = pd.to_datetime(rets.index)

    if benchmark is not None:
        bench_rets = benchmark.pct_change().dropna().reindex(rets.index).dropna()
        bench_rets.index = pd.to_datetime(bench_rets.index)
    else:
        bench_rets = None

    qs.reports.html(
        rets,
        benchmark=bench_rets,
        output=str(out_path),
        title="Portfolio Tear-Sheet",
        download_filename=None
    )
    return out_path
