import aiohttp, pandas as pd
import aiomoex
from datetime import date, timedelta
from sqlmodel import Session, select
from database import engine
from models import ImoexPrice


async def _fetch_imoex_from_iss(d_from: date, d_till: date) -> pd.DataFrame:
    async with aiohttp.ClientSession() as s:
        raw = await aiomoex.get_board_history(
            s,
            security="IMOEX",
            start=str(d_from),
            end=str(d_till),
            market="index",
            board="SNDX",
            columns=("TRADEDATE", "CLOSE"),
        )
    df = pd.DataFrame(raw).rename(columns={"TRADEDATE": "date", "CLOSE": "close"})
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df
    return pd.DataFrame()


def _save_to_db(df: pd.DataFrame):
    with Session(engine) as ses:
        for r in df.itertuples():
            if not ses.get(ImoexPrice, r.date):
                ses.add(ImoexPrice(date=r.date, close=float(r.close)))
        ses.commit()


async def get_imoex_series(d_from: date, d_till: date) -> pd.DataFrame:
    with Session(engine) as ses:
        rows = ses.exec(
            select(ImoexPrice).where(ImoexPrice.date.between(d_from, d_till))
        ).all()
    if rows:
        d_min = min(r.date for r in rows)
        d_max = max(r.date for r in rows)
    else:
        d_min = d_till + timedelta(days=1)
        d_max = d_from - timedelta(days=1)

    fetch_ranges = []
    if d_from < d_min:
        fetch_ranges.append((d_from, d_min - timedelta(days=1)))
    if d_till > d_max:
        fetch_ranges.append((d_max + timedelta(days=1), d_till))
    if len(fetch_ranges) > 1 and fetch_ranges[0] == fetch_ranges[1]:
        fetch_ranges = [fetch_ranges[0]]

    for start, end in fetch_ranges:
        if start <= end:
            df_new = await _fetch_imoex_from_iss(start, end)
            if not df_new.empty:
                _save_to_db(df_new)
                rows.extend(
                    ImoexPrice(date=r.date, close=r.close) for r in df_new.itertuples()
                )

    return (
        pd.DataFrame([{"date": r.date, "close": r.close} for r in rows])
        .drop_duplicates(subset="date")
        .sort_values("date")
        .reset_index(drop=True)
    ) if rows else pd.DataFrame()
