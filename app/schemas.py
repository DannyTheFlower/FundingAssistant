from datetime import date
from typing import List, Literal, Dict
from pydantic import BaseModel, Field


Weighting = Literal["equal", "market_cap", "cap_freefloat", "cap_divyield", "custom"]


class SecurityIn(BaseModel):
    secid: str
    custom_weight: float | None = None


class IndexCreate(BaseModel):
    name: str = Field(..., example="MyPower20")
    base_date: date = Field(..., example="2025-04-01")
    weighting: Weighting
    securities: List[SecurityIn]


class IndexOut(BaseModel):
    id: int
    name: str
    base_value: float
    weights: Dict[str, float]


class IndexValue(BaseModel):
    date: date
    value: float


class IndexInfo(BaseModel):
    id: int
    name: str
    base_date: date
    weighting: str
    base_value: float

    class Config:
        from_attributes = True


class IndexPoint(BaseModel):
    date: date
    value: float
    imoex: float | None

    class Config:
        from_attributes = True


class SecurityWeight(BaseModel):
    secid: str
    shares: int


class ForecastRequest(BaseModel):
    assets: List[SecurityWeight]
    model: Literal["fast", "quality"] = "fast"


class ForecastResponse(BaseModel):
    history: list[tuple[date, float]]
    forecast: list[tuple[date, float]]
    lo95: list[tuple[date, float]]
    hi95: list[tuple[date, float]]
    metrics: dict[str, float]


class ReportRequest(BaseModel):
    assets: List[SecurityWeight]
