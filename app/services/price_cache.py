import aiohttp, pandas as pd
import aiomoex
from datetime import date, timedelta
from sqlmodel import Session, select
from database import engine
from models import Price


async def _fetch_iss(secid: str, start="2000-01-01", end: str = str(date.today())) -> pd.DataFrame:
    async with aiohttp.ClientSession() as sess:
        raw = await aiomoex.get_board_history(
            sess, security=secid, start=start, end=end, board="TQBR",
            columns=("TRADEDATE", "CLOSE")
        )
    df = pd.DataFrame(raw).rename(columns={"TRADEDATE": "date", "CLOSE": "close"})
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


async def get_series(secid: str) -> pd.DataFrame:
    """Вернёт полный ряд CLOSE; докачает отсутствующие даты."""
    with Session(engine) as ses:
        rows = ses.exec(select(Price).where(Price.secid == secid)).all()
    if rows:
        have_min = min(r.trade_date for r in rows)
        have_max = max(r.trade_date for r in rows)
    else:
        have_min = date.today()
        have_max = date(1900,1,1)

    need_start = "2000-01-01"
    need_end = str(date.today())

    if have_min > date.fromisoformat(need_start):
        df_left = await _fetch_iss(secid, need_start, str(have_min - timedelta(days=1)))
    else:
        df_left = pd.DataFrame()

    if have_max < date.today():
        df_right = await _fetch_iss(secid, str(have_max + timedelta(days=1)), need_end)
    else:
        df_right = pd.DataFrame()

    for df in (df_left, df_right):
        if not df.empty:
            with Session(engine) as ses:
                ses.add_all([
                    Price(secid=secid, date=r.date, close=float(r.close))
                    for r in df.itertuples()
                    if r.close is not None
                ])
                ses.commit()
        if df_left.equals(df_right):
            break

    with Session(engine) as ses:
        full = ses.exec(select(Price).where(Price.secid == secid)).all()
    return (
        pd.DataFrame([{"date": r.trade_date, "close": r.close} for r in full])
        .sort_values("date")
        .reset_index(drop=True)
    )
