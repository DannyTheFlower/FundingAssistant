from fastapi import APIRouter, Query
from datetime import date
from services import moex


router = APIRouter(prefix="/securities", tags=["Securities"])


@router.get("/")
async def list_securities(year: int = Query(date.today().year), quarter: int = Query(1)):
    return await moex.list_securities(year, quarter)
