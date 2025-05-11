from fastapi import FastAPI
from database import create_db_and_tables
from routers.index import router as index_router
from routers.securities import router as sec_router
from routers.forecast import router as forecast_router

app = FastAPI(title="Custom MOEX Index Builder", version="0.1.0")

create_db_and_tables()

app.include_router(index_router, prefix="/api")
app.include_router(sec_router, prefix="/api")
app.include_router(forecast_router, prefix="/api")