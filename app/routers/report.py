import asyncio
import tempfile
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.price_cache import get_series
from services.benchmark import get_imoex_series
from schemas import ReportRequest
from utils.report import generate_report

router = APIRouter(prefix="/report", tags=["Report"])


@router.post("/", response_class=FileResponse)
async def portfolio_report(req: ReportRequest):
    if not req.assets:
        raise HTTPException(400, "assets empty")

    dfs = await asyncio.gather(*[get_series(a.secid) for a in req.assets])
    price_tbl = (
        pd.concat(
            [df.set_index("date")["close"].rename(a.secid) for a, df in zip(req.assets, dfs)],
            axis=1,
        )
        .sort_index()
        .ffill()
        .dropna(how="any")
    )
    shares = pd.Series({a.secid: a.shares for a in req.assets})
    pf_price = (price_tbl * shares).sum(axis=1)

    bm_df = await get_imoex_series(pf_price.index.min(), pf_price.index.max())
    bm_price = bm_df.rename({"close": "IMOEX"}, axis=1).set_index("date")["IMOEX"]

    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    pdf_path = generate_report(pf_price, bm_price, tmp.name)

    return FileResponse(
        pdf_path,
        media_type="text/html; charset=utf-8",
        filename="portfolio_report.html",
    )
