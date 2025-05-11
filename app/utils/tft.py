import numpy as np
import pandas as pd
import lightning.pytorch as pl
from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
from pytorch_forecasting.data import GroupNormalizer
from pytorch_forecasting.metrics import QuantileLoss


default_params = {
    'learning_rate': 0.0023,
    'hidden_size': 43,
    'attention_head_size': 6,
    'dropout': 0.3,
    'hidden_continuous_size': 16
}


def _to_long_df(port: pd.Series, idx: pd.Series) -> pd.DataFrame:
    df_p = port.to_frame("value").reset_index().rename(columns={"index": "date"})
    df_p["group_id"] = "FUND"
    df_i = idx.to_frame("value").reset_index().rename(columns={"index": "date"})
    df_i["group_id"] = "IMOEX"
    res = pd.concat([df_p, df_i], ignore_index=True)
    res["date"] = pd.to_datetime(res["date"])
    return res


def _append_future(
    df_long: pd.DataFrame,
    pred_len: int,
) -> pd.DataFrame:
    extra = []
    for g, grp in df_long.groupby("group_id"):
        last_idx = grp["time_idx"].max()
        last_val = grp["value"].iloc[-1]
        future_idx = np.arange(last_idx + 1, last_idx + pred_len + 1)
        extra.append(
            pd.DataFrame({
                "group_id": g,
                "time_idx": future_idx,
                "value": last_val
            })
        )
    return pd.concat([df_long, *extra], ignore_index=True)


def fit_tft(
    portfolio: pd.Series,
    imoex: pd.Series,
    encoder_len: int = 60,
    pred_len: int = 60,
    quantiles: list[float] | None = None,
    params: dict | None = None
):
    """
    Обучает Temporal Fusion Transformer на объединённом ряде Фонда и IMOEX.
    Возвращает model и DataFrame последнего encoder-окна.
    """
    if quantiles is None:
        quantiles = [0.025, 0.5, 0.975]
    if params is None:
        params = default_params

    df = _to_long_df(portfolio, imoex)
    df["time_idx"] = (df["date"] - df["date"].min()).dt.days

    max_encoder = encoder_len
    max_pred = pred_len

    dataset = TimeSeriesDataSet(
        df,
        time_idx="time_idx",
        target="value",
        group_ids=["group_id"],
        min_encoder_length=max_encoder,
        max_encoder_length=max_encoder,
        min_prediction_length=max_pred,
        max_prediction_length=max_pred,
        time_varying_unknown_reals=["value"],
        target_normalizer=GroupNormalizer(groups=["group_id"]),
        allow_missing_timesteps=True
    )

    train_loader = dataset.to_dataloader(train=True, batch_size=64, num_workers=4, persistent_workers=True)

    tft = TemporalFusionTransformer.from_dataset(
        dataset,
        output_size=3,
        loss=QuantileLoss(quantiles=quantiles),
        **params
    )

    trainer = pl.Trainer(
        max_epochs=25,
        gradient_clip_val=0.1,
        enable_checkpointing=False,
        logger=False,
        enable_model_summary=False
    )
    trainer.fit(tft, train_loader)

    last_encoder = df.groupby("group_id").tail(max_encoder).copy()
    return tft, dataset, last_encoder


def forecast_tft(
    model: TemporalFusionTransformer,
    train_ds: TimeSeriesDataSet,
    encoder_df: pd.DataFrame,
    pred_len: int = 60,
    quantiles: tuple[float, float] = (0.025, 0.975)
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Возвращает медианный прогноз + нижний/верхний квантиль
    (для 95%-го доверительного интервала по умолчанию).
    """
    group = encoder_df[encoder_df["group_id"] == "FUND"].copy()
    full_df = _append_future(group, pred_len)
    dataset = TimeSeriesDataSet.from_dataset(
        train_ds,
        full_df,
        predict=True,
        stop_randomization=True
    )
    preds = model.predict(dataset, mode="quantiles")
    lo_q = preds[0, :, 0]
    point = preds[0, :, 1]
    hi_q = preds[0, :, 2]
    return point, lo_q, hi_q