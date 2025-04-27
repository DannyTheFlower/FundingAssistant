import asyncio, aiomoex, aiohttp, io, datetime, pandas as pd
from bs4 import BeautifulSoup
from datetime import date
from urllib.parse import urljoin
from sqlmodel import Session, select
from database import engine
from models import Capitalization, FreeFloat


BASE_URL = "https://www.moex.com"
FF_URL = "https://web.moex.com/moex-web-icdb-api/api/v1/export/site-free-floats/xlsx"
PROF_URL = (
    "https://web.moex.com/moex-web-icdb-api/api/v2/export/ru_profitability"
    "?Format.Type=xlsx&Data.Direction=asc&Data.Language=ru"
)
DIV_URL = "https://web.moex.com/moex-web-icdb-api/api/v1/export/site-dividend-yields/xlsx"


def _df_from_cap(rows):
    return pd.DataFrame([r.dict() for r in rows])[
        ["secid", "name", "shares_out", "price", "cap"]
    ]


def _df_from_ff(rows):
    return pd.DataFrame([r.dict() for r in rows])[["SECID", "FREEFLOAT"]]


async def load_latest_prices(secids: list[str]) -> dict[str, float]:
    async with aiohttp.ClientSession() as session:
        tasks = [
            aiomoex.get_market_candles(
                session,
                security=s,
                interval=24,
                start=date.today().strftime("%Y-%m-%d"),
                end=date.today().strftime("%Y-%m-%d"),
            )
            for s in secids
        ]
        raw = await asyncio.gather(*tasks)
    return {s: candles[-1]["close"] if candles else 0.0 for s, candles in zip(secids, raw)}


async def _scrape_cap(year: int, quarter: int) -> pd.DataFrame:
    """Download capitalization table for *year*, *quarter* (1‑4)."""
    async with aiohttp.ClientSession() as s, s.get(f"{BASE_URL}/s26") as r:
        soup = BeautifulSoup(await r.text(), "lxml")
        scroller = soup.select_one("table.table1")
        if not scroller:
            raise RuntimeError("table-scroller not found on s26 page")
        header_cells = [th.text.strip() for th in scroller.find("tr").find_all("th")]
        if str(year) not in header_cells:
            raise ValueError(f"Year {year} not available on s26 page")
        y_idx = header_cells.index(str(year))
        href = None
        for tr in scroller.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if y_idx >= len(cells):
                continue
            text = cells[y_idx].get_text(strip=True)
            if text.startswith(f"{quarter} квартал"):
                a = cells[y_idx].find("a")
                if a and a.get("href"):
                    href = urljoin(BASE_URL, a["href"])
                break
        if not href:
            raise ValueError(f"Link for {quarter}‑q {year} not found")
    async with aiohttp.ClientSession() as s, s.get(href) as r:
        soup = BeautifulSoup(await r.text(), "lxml")
        table = soup.select_one("div.table-scroller table.table1, table.table1")
        if table is None:
            raise RuntimeError("Capitalization table not found at quarter page")
        df = pd.read_html(str(table), decimal=",", thousands=" ")[0]
    if len(df.columns) >= 7:
        df.columns = [
            "secid",
            "name",
            "type",
            "state_reg",
            "shares_out",
            "price",
            "cap",
        ] + list(df.columns[7:])
    for col in ["shares_out", "cap"]:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False)
            .astype(float)
        )
    df["shares_out"] = df["shares_out"].astype(int)
    df["price"] = (
        df["price"].astype(str).str.replace(" ", "").str.replace(",", ".").astype(float)
    )
    df["secid"] = df["secid"].str.strip()
    return df[["secid", "name", "shares_out", "price", "cap"]]


async def cap_table_q(year: int, quarter: int):
    """Return DataFrame (secid … cap) for given quarter; uses DB cache."""
    with Session(engine) as ss:
        rows = ss.exec(
            select(Capitalization).where(Capitalization.year == year, Capitalization.quarter == quarter)
        ).all()
        if rows:
            return _df_from_cap(rows)
    df = await _scrape_cap(year, quarter)
    with Session(engine) as ss:
        for row in df.itertuples(index=False):
            ss.add(
                Capitalization(
                    year=year,
                    quarter=quarter,
                    secid=row.secid,
                    name=row.name,
                    shares_out=row.shares_out,
                    price=row.price,
                    cap=row.cap,
                )
            )
        ss.commit()
    return df


async def _load_xlsx(url: str) -> pd.DataFrame:
    async with aiohttp.ClientSession() as s, s.get(url) as r:
        buf = await r.read()
    return pd.read_excel(io.BytesIO(buf))


async def free_float() -> pd.DataFrame:
    target = date.today() - datetime.timedelta(days=1)
    with Session(engine) as ss:
        rows = ss.exec(select(FreeFloat).where(FreeFloat.date == target or FreeFloat.date == date.today())).all()
        if rows:
            return pd.DataFrame([r.dict() for r in rows])[["secid", "free_float"]]
    df = await _load_xlsx(FF_URL)
    if len(df.columns) >= 7:
        df.columns = [
            "secid",
            "name",
            "itin",
            "type",
            "state_reg",
            "listing_level",
            "free_float",
        ] + list(df.columns[7:])
    df = df.loc[df["free_float"] != "не рассчитан"].copy()
    df["free_float"] = df["free_float"].astype(float)
    with Session(engine) as ss:
        for row in df.itertuples(index=False):
            ss.merge(FreeFloat(date=date.today(), secid=row.secid, free_float=row.free_float))
        ss.commit()
    return df[["secid", "free_float"]]


async def list_securities(year: int, quarter: int) -> list[tuple[str, str]]:
    """Return pairs (secid, name) from cap‑table for given year/quarter."""
    rows = [(r.secid, r.name) for r in Session(engine).exec(
        select(Capitalization.secid, Capitalization.name).where(
            Capitalization.year == year, Capitalization.quarter == quarter
        )).all()]
    if rows:
        return rows
    df = await cap_table_q(year, quarter)
    return list(zip(df.secid, df.name))


async def candles_bulk(secids: list[str], date_from: date, date_to: date):
    """Return dict secid→DataFrame(date, close) daily candles."""
    async with aiohttp.ClientSession() as session:
        tasks = [
            aiomoex.get_market_candles(
                session,
                security=s,
                interval=24,
                start=date_from.strftime("%Y-%m-%d"),
                end=date_to.strftime("%Y-%m-%d"),
            )
            for s in secids
        ]
        raw = await asyncio.gather(*tasks)
    out = {}
    for s, candles in zip(secids, raw):
        if not candles:
            continue
        df = pd.DataFrame(candles)[["begin", "close"]]
        df["date"] = pd.to_datetime(df["begin"]).dt.date
        out[s] = df[["date", "close"]]
    return out
