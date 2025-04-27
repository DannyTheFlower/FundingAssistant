from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from schemas import IndexCreate, IndexOut, IndexValue
from models import Index, IndexComponent
from database import engine
from services import moex, index_builder

router = APIRouter(prefix="/index", tags=["Custom Index"])


def get_session():
    with Session(engine) as session:
        yield session


@router.post("/", response_model=IndexOut)
async def create_index(req: IndexCreate, session: Session = Depends(get_session)):
    df_cap = await moex.cap_table_q(req.base_date.year, (req.base_date.month - 1) // 3 + 1)
    df_sel = df_cap[df_cap.secid.isin([s.secid for s in req.securities])].copy()
    if df_sel.empty:
        raise HTTPException(400, "No securities found in selected quarter table")
    ff_df = await moex.free_float()
    df_sel = df_sel.merge(ff_df[["secid", "free_float"]], on="secid", how="left")
    df_sel = df_sel.loc[df_sel["secid"].isin([sec.secid for sec in req.securities])].copy()
    df_sel = df_sel.set_index("secid")
    custom = {s.secid: s.custom_weight for s in req.securities if s.custom_weight is not None}
    weights = await index_builder.build_weights(df_sel, req.weighting, custom)
    base_value = await index_builder.compute_index_value(weights)
    index_row = Index(
        name=req.name,
        base_date=req.base_date,
        weighting=req.weighting,
        base_value=base_value,
    )
    session.add(index_row)
    session.commit()
    session.refresh(index_row)
    # components
    for secid, w in weights.items():
        session.add(IndexComponent(index_id=index_row.id, secid=secid, weight=w))
    session.commit()
    return IndexOut(id=index_row.id, name=index_row.name, base_value=base_value, weights=weights)


@router.get("/{index_id}/value", response_model=IndexValue)
async def get_value(index_id: int, session: Session = Depends(get_session)):
    index = session.get(Index, index_id)
    if not index:
        raise HTTPException(404, "Index not found")
    comps = session.exec(select(IndexComponent).where(IndexComponent.index_id == index_id)).all()
    weights = {c.secid: c.weight for c in comps}
    current_val = await index_builder.compute_index_value(weights)
    return IndexValue(date=date.today(), value=current_val)


@router.get("/{index_id}/series")
async def index_series(
    index_id: int,
    from_: date = Query(..., alias="from"),
    till: date = Query(..., alias="till"),
    session: Session = Depends(lambda: Session(engine)),
):
    idx = session.get(Index, index_id)
    if not idx:
        raise HTTPException(404, "Index not found")
    comps = session.exec(select(IndexComponent).where(IndexComponent.index_id == index_id)).all()
    weights = {c.secid: c.weight for c in comps}
    return await index_builder.compute_series(weights, from_, till)