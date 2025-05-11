from datetime import date
from typing import List, Optional

from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint


class Index(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    base_date: date
    weighting: str
    base_value: Optional[float] = None
    components: List["IndexComponent"] = Relationship(back_populates="index")


class IndexComponent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    index_id: int = Field(foreign_key="index.id")
    secid: str
    weight: float
    index: Index = Relationship(back_populates="components")


class Capitalization(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("year", "quarter", "secid"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    year: int
    quarter: int
    secid: str
    name: str
    state_reg: str
    shares_out: Optional[int]
    price: Optional[float]
    cap: Optional[float]


class FreeFloat(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("date", "secid"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    secid: str
    free_float: float


class DividendYield(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    year: int
    state_reg: str = Field(index=True)
    div_yield: float
    loaded_at: date = Field(default_factory=date.today)


class ImoexPrice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    close: float


class Price(SQLModel, table=True):
    secid: str = Field(default=None, primary_key=True)
    trade_date: date = Field(default=None, primary_key=True, alias="date")
    close: Optional[float]
