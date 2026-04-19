"""
Model training pipeline.
Trains all 6 models with walk-forward cross-validation and Optuna hyperparameter tuning.
Selects champion by lowest out-of-sample RPS.
"""
import os
import json
import joblib
import numpy as np
import pandas as pd
import mlflow
from datetime import datetime
from typing import Optional
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import log_loss, brier_score_loss
import optuna
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostClassifier
import torch
import torch.nn as nn

from features.dixon_coles import DixonColesModel, _score_matrix_to_markets
from app.core.config import settings
from app.core.logging import logger

optuna.logging.set_verbosity(optuna.logging.WARNING)

MODEL_STORAGE = Path(settings.MODEL_STORAGE_PATH)
MODEL_STORAGE.mkdir(exist_ok=True)


# ─── Target Encoding ─────────────────────────────────────────────────

def encode_score_target(home_goals: pd.Series, away_goals: pd.Series) -> pd.Series:
    """Encode score as 'H_A' string label, capped at 5-5+."""
    h = home_goals.clip(upper=5).astype(int).astype(str)
    a = away_goals.clip(upper=5).astype(int).astype(str)
    return h + "_" + a


# ─── Evaluation Metrics ──────────────────────────────────────────────

def ranked_probability_score(y_true_goals: np.ndarray, y_pred_probs: np.ndarray) -> float:
    """
    Compute RPS for match outcome (home/draw/away) from goal predictions.
    Lower is better.
    """
    outcomes = []
    for hg, ag in y_true_goals:
        if hg > ag:
            outcomes.append([1, 0, 0])
        elif hg == ag:
            outcomes.append([0, 1, 0])
        else:
            outcomes.append([0, 0, 1])

    outcomes = np.array(outcomes)
    cum_pred = np.cumsum(y_pred_probs[:, :3], axis=1)
    cum_true = np.cumsum(outcomes, axis=1)
    rps_per_match = np.mean((cum_pred - cum_true) ** 2, axis=1)
    return float(np.mean(rps_per_match))


def exact_score_accuracy(y_true: np.ndarray, y_pred_labels: np.ndarray) -> float:
    return float(np.mean(y_true == y_pred_labels))


def top_n_score_accuracy(y_true: np.ndarray, y_pred_probs: np.ndarray,
                          classes: np.ndarray, n: int = 3) -> float:
    """Check if true score is in top-N predicted scores."""
    top_n_indices = np.argsort(y_pred_probs, axis=1)[:, -n:]
    hits = sum(
        classes[top_n_indices[i]].tolist().__contains__(y_true[i])
        for i in range(len(y_true))
    )
    return hits / len(y_true)


# ─── Base Trainer ────────────────────────────────────────────────────

class BaseModelTrainer:
    MODEL_NAME: str = "base"

    def __init__(self, league_id: str):
        self.league_id = league_id
        self.model = None
        self.label_encoder = LabelEncoder()
        self.feature_names: list[str] = []
        self.is_trained: bool = False

    def prepare_data(self, df: pd.DataFrame):
        """Prepare feature matrix X and encoded target y."""
        drop_cols = ["match_id", "target_home_goals", "target_away_goals",
                     "data_insufficient"]
        feature_cols = [c for c in df.columns if c not in drop_cols
                        and not df[c].dtype == object]

        X = df[feature_cols].fillna(-1).values
        self.feature_names = feature_cols

        target = encode_score_target(df["target_home_goals"], df["target_away_goals"])
        y = self.label_encoder.fit_transform(target)
        return X, y, target.values

    def evaluate(self, X: np.ndarray, y_true_encoded: np.ndarray,
                 y_true_goals: np.ndarray) -> dict:
        """Compute all evaluation metrics."""
        y_pred_probs = self.model.predict_proba(X)
        y_pred_labels = self.label_encoder.classes_[np.argmax(y_pred_probs, axis=1)]
        y_true_labels = self.label_encoder.inverse_transform(y_true_encoded)

        # 1X2 probabilities from score probabilities
        outcome_probs = self._score_probs_to_outcome(y_pred_probs)

        return {
            "rps": ranked_probability_score(y_true_goals, outcome_probs),
            "log_loss": float(log_loss(y_true_encoded, y_pred_probs,
                                       labels=list(range(len(self.label_encoder.classes_))))),
            "exact_score_acc": exact_score_accuracy(y_true_labels, y_pred_labels),
            "top3_score_acc": top_n_score_accuracy(y_true_labels, y_pred_probs,
                                                    self.label_encoder.classes_, n=3),
        }

    def _score_probs_to_outcome(self, probs: np.ndarray) -> np.ndarray:
        """Sum score probabilities into home/draw/away probabilities."""
        outcome = np.zeros((len(probs), 3))
        for i, cls in enumerate(self.label_encoder.classes_):
            h, a = map(int, cls.split("_"))
            if h > a:
                outcome[:, 0] += probs[:, i]
            elif h == a:
                outcome[:, 1] += probs[:, i]
            else:
                outcome[:, 2] += probs[:, i]
        return outcome

    def save(self, version: str) -> str:
        path = MODEL_STORAGE / f"{self.MODEL_NAME}_{self.league_id}_{version}.pkl"
        joblib.dump({
            "model": self.model,
            "label_encoder": self.label_encoder,
            "feature_names": self.feature_names,
        }, path)
        return str(path)

    def load(self, path: str) -> None:
        data = joblib.load(path)
        self.model = data["model"]
        self.label_encoder = data["label_encoder"]
        self.feature_names = data["feature_names"]
        self.is_trained = True


# ─── XGBoost Trainer ─────────────────────────────────────────────────

class XGBoostTrainer(BaseModelTrainer):
    MODEL_NAME = "xgboost"

    def train(self, df: pd.DataFrame, n_trials: int = settings.OPTUNA_TRIALS) -> dict:
        X, y, y_raw = self.prepare_data(df)
        n_classes = len(self.label_encoder.classes_)

        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-5, 1.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-5, 1.0, log=True),
                "objective": "multi:softprob",
                "num_class": n_classes,
                "eval_metric": "mlogloss",
                "use_label_encoder": False,
                "random_state": 42,
            }
            tscv = TimeSeriesSplit(n_splits=3)
            scores = []
            for train_idx, val_idx in tscv.split(X):
                model = xgb.XGBClassifier(**params)
                model.fit(X[train_idx], y[train_idx], eval_set=[(X[val_idx], y[val_idx])],
                          verbose=False)
                probs = model.predict_proba(X[val_idx])
                scores.append(log_loss(y[val_idx], probs))
            return np.mean(scores)

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best_params = study.best_params
        best_params.update({
            "objective": "multi:softprob",
            "num_class": n_classes,
            "random_state": 42,
        })

        base_model = xgb.XGBClassifier(**best_params)
        base_model.fit(X, y)
        self.model = CalibratedClassifierCV(base_model, cv=3, method="isotonic")
        self.model.fit(X, y)
        self.is_trained = True
        return study.best_params


# ─── LightGBM Trainer ────────────────────────────────────────────────

class LightGBMTrainer(BaseModelTrainer):
    MODEL_NAME = "lightgbm"

    def train(self, df: pd.DataFrame, n_trials: int = settings.OPTUNA_TRIALS) -> dict:
        X, y, _ = self.prepare_data(df)
        n_classes = len(self.label_encoder.classes_)

        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 20, 150),
                "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
                "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
                "bagging_freq": trial.suggest_int("bagging_freq", 1, 7),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
                "objective": "multiclass",
                "num_class": n_classes,
                "random_state": 42,
                "verbose": -1,
            }
            tscv = TimeSeriesSplit(n_splits=3)
            scores = []
            for train_idx, val_idx in tscv.split(X):
                model = lgb.LGBMClassifier(**params)
                model.fit(X[train_idx], y[train_idx],
                          eval_set=[(X[val_idx], y[val_idx])],
                          callbacks=[lgb.early_stopping(20, verbose=False),
                                     lgb.log_evaluation(-1)])
                probs = model.predict_proba(X[val_idx])
                scores.append(log_loss(y[val_idx], probs))
            return np.mean(scores)

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best = study.best_params
        best.update({"objective": "multiclass", "num_class": n_classes,
                     "random_state": 42, "verbose": -1})

        base = lgb.LGBMClassifier(**best)
        base.fit(X, y)
        self.model = CalibratedClassifierCV(base, cv=3, method="isotonic")
        self.model.fit(X, y)
        self.is_trained = True
        return study.best_params


# ─── CatBoost Trainer ────────────────────────────────────────────────

class CatBoostTrainer(BaseModelTrainer):
    MODEL_NAME = "catboost"

    def train(self, df: pd.DataFrame, n_trials: int = settings.OPTUNA_TRIALS) -> dict:
        X, y, _ = self.prepare_data(df)
        n_classes = len(self.label_encoder.classes_)

        def objective(trial):
            params = {
                "iterations": trial.suggest_int("iterations", 100, 500),
                "depth": trial.suggest_int("depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
                "random_strength": trial.suggest_float("random_strength", 0.1, 2.0),
                "loss_function": "MultiClass",
                "classes_count": n_classes,
                "random_seed": 42,
                "verbose": False,
            }
            tscv = TimeSeriesSplit(n_splits=3)
            scores = []
            for train_idx, val_idx in tscv.split(X):
                model = CatBoostClassifier(**params)
                model.fit(X[train_idx], y[train_idx], eval_set=(X[val_idx], y[val_idx]),
                          verbose=False)
                probs = model.predict_proba(X[val_idx])
                scores.append(log_loss(y[val_idx], probs))
            return np.mean(scores)

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best = study.best_params
        best.update({"loss_function": "MultiClass", "classes_count": n_classes,
                     "random_seed": 42, "verbose": False})

        base = CatBoostClassifier(**best)
        base.fit(X, y)
        self.model = CalibratedClassifierCV(base, cv=3, method="isotonic")
        self.model.fit(X, y)
        self.is_trained = True
        return study.best_params


# ─── LSTM Trainer ────────────────────────────────────────────────────

class LSTMModel(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, n_classes: int, n_layers: int = 2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, n_layers, batch_first=True, dropout=0.3)
        self.fc = nn.Linear(hidden_size, n_classes)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class LSTMTrainer(BaseModelTrainer):
    MODEL_NAME = "lstm"
    SEQUENCE_LEN = 10

    def train(self, df: pd.DataFrame, n_trials: int = 20) -> dict:
        X, y, _ = self.prepare_data(df)
        n_classes = len(self.label_encoder.classes_)

        # Reshape into sequences of SEQUENCE_LEN matches per pair
        X_seq, y_seq = self._make_sequences(X, y)
        if len(X_seq) < 50:
            logger.warning("Not enough sequence data for LSTM")
            return {}

        X_t = torch.FloatTensor(X_seq)
        y_t = torch.LongTensor(y_seq)

        model = LSTMModel(X_t.shape[2], hidden_size=64, n_classes=n_classes)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.CrossEntropyLoss()

        for epoch in range(30):
            model.train()
            optimizer.zero_grad()
            output = model(X_t)
            loss = criterion(output, y_t)
            loss.backward()
            optimizer.step()

        self.lstm_model = model
        self.is_trained = True
        return {"hidden_size": 64, "n_layers": 2, "epochs": 30}

    def _make_sequences(self, X: np.ndarray, y: np.ndarray):
        seq_X, seq_y = [], []
        for i in range(self.SEQUENCE_LEN, len(X)):
            seq_X.append(X[i - self.SEQUENCE_LEN:i])
            seq_y.append(y[i])
        return np.array(seq_X), np.array(seq_y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if len(X) < self.SEQUENCE_LEN:
            n_classes = len(self.label_encoder.classes_)
            return np.ones((1, n_classes)) / n_classes

        X_seq = np.expand_dims(X[-self.SEQUENCE_LEN:], 0)
        X_t = torch.FloatTensor(X_seq)
        self.lstm_model.eval()
        with torch.no_grad():
            logits = self.lstm_model(X_t)
            probs = torch.softmax(logits, dim=1).numpy()
        return probs


# ─── Stacking Ensemble ───────────────────────────────────────────────

class StackingEnsembleTrainer(BaseModelTrainer):
    MODEL_NAME = "stacking"

    def __init__(self, league_id: str, base_trainers: list):
        super().__init__(league_id)
        self.base_trainers = base_trainers

    def train(self, df: pd.DataFrame, n_trials: int = 20) -> dict:
        from sklearn.linear_model import LogisticRegression

        X, y, _ = self.prepare_data(df)
        meta_features = []

        for trainer in self.base_trainers:
            if trainer.is_trained:
                probs = trainer.model.predict_proba(X)
                meta_features.append(probs)

        if not meta_features:
            return {}

        X_meta = np.hstack(meta_features)
        self.model = LogisticRegression(C=1.0, max_iter=500, multi_class="multinomial")
        self.model.fit(X_meta, y)

        # Re-use same label encoder as base models
        self.label_encoder = self.base_trainers[0].label_encoder
        self.is_trained = True
        return {"meta_features": X_meta.shape[1]}

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        meta_features = []
        for trainer in self.base_trainers:
            if trainer.is_trained:
                probs = trainer.model.predict_proba(X)
                meta_features.append(probs)
        X_meta = np.hstack(meta_features)
        return self.model.predict_proba(X_meta)


# ─── Master Training Orchestrator ────────────────────────────────────

class ModelTrainingPipeline:
    """Trains all 6 models and selects the champion."""

    def __init__(self, league_id: str):
        self.league_id = league_id
        self.version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        self.trainers = {
            "xgboost": XGBoostTrainer(league_id),
            "lightgbm": LightGBMTrainer(league_id),
            "catboost": CatBoostTrainer(league_id),
            "lstm": LSTMTrainer(league_id),
        }

    def run(self, features_df: pd.DataFrame) -> dict:
        """
        Full training pipeline:
        1. Walk-forward CV (5 folds)
        2. Train all models on full dataset
        3. Back-test on held-out season
        4. Select champion
        5. Log to MLflow
        """
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

        results = {}

        with mlflow.start_run(run_name=f"{self.league_id}_{self.version}"):
            mlflow.log_param("league_id", self.league_id)
            mlflow.log_param("n_samples", len(features_df))
            mlflow.log_param("version", self.version)

            # Sort by date — CRITICAL for temporal validity
            features_df = features_df.sort_values("match_date").reset_index(drop=True)

            # Holdout: last BACKTEST_SEASONS worth of data
            holdout_idx = int(len(features_df) * (1 - 1/max(settings.MIN_SEASONS_HISTORY, 3)))
            train_df = features_df.iloc[:holdout_idx]
            test_df = features_df.iloc[holdout_idx:]

            if len(train_df) < 100 or len(test_df) < 20:
                logger.warning("Insufficient data for training", league=self.league_id)
                return {}

            # Train all models
            for name, trainer in self.trainers.items():
                logger.info("Training model", model=name, league=self.league_id)
                try:
                    with mlflow.start_run(run_name=f"{name}", nested=True):
                        best_params = trainer.train(train_df)
                        mlflow.log_params({f"{name}_{k}": v for k, v in (best_params or {}).items()})

                        if trainer.is_trained and len(test_df) > 0:
                            X_test, y_test, y_raw = trainer.prepare_data(test_df)
                            metrics = trainer.evaluate(X_test, y_test, y_raw)
                            results[name] = metrics
                            mlflow.log_metrics(metrics)
                            logger.info("Model evaluated", model=name, metrics=metrics)

                        # Save model
                        model_path = trainer.save(self.version)
                        mlflow.log_artifact(model_path)

                except Exception as e:
                    logger.error("Model training failed", model=name, error=str(e))
                    results[name] = {"error": str(e)}

            # Dixon-Coles (no sklearn, fits separately)
            dc_result = self._train_dixon_coles(train_df, test_df)
            results["dixon_coles"] = dc_result

            # Stacking ensemble (uses trained base models)
            stacking = StackingEnsembleTrainer(
                self.league_id,
                [t for t in self.trainers.values() if t.is_trained]
            )
            try:
                stacking.train(train_df)
                if stacking.is_trained and len(test_df) > 0:
                    X_test, y_test, y_raw = stacking.prepare_data(test_df)
                    stacking_metrics = stacking.evaluate(X_test, y_test, y_raw)
                    results["stacking"] = stacking_metrics
                    stacking.save(self.version)
            except Exception as e:
                logger.error("Stacking training failed", error=str(e))

            # Select champion (lowest RPS on test set)
            champion = self._select_champion(results)
            mlflow.log_param("champion_model", champion)
            logger.info("Champion selected", model=champion, league=self.league_id)

            return {
                "version": self.version,
                "champion": champion,
                "results": results,
                "train_size": len(train_df),
                "test_size": len(test_df),
            }

    def _train_dixon_coles(self, train_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
        """Fit and evaluate Dixon-Coles model."""
        try:
            dc = DixonColesModel()
            dc.fit(train_df, self.league_id)

            if not dc.is_fitted or test_df.empty:
                return {}

            rps_scores = []
            for _, row in test_df.iterrows():
                markets = dc.predict_all_markets(
                    row.get("home_team_id"), row.get("away_team_id")
                )
                true_h = int(row.get("target_home_goals", 0) or 0)
                true_a = int(row.get("target_away_goals", 0) or 0)
                pred = np.array([[
                    markets["prob_home_win"],
                    markets["prob_draw"],
                    markets["prob_away_win"]
                ]])
                rps_scores.append(
                    ranked_probability_score(np.array([[true_h, true_a]]), pred)
                )

            # Save
            dc_path = MODEL_STORAGE / f"dixon_coles_{self.league_id}_{self.version}.pkl"
            joblib.dump(dc, dc_path)

            return {"rps": float(np.mean(rps_scores))}
        except Exception as e:
            logger.error("Dixon-Coles evaluation failed", error=str(e))
            return {"error": str(e)}

    def _select_champion(self, results: dict) -> str:
        valid = {
            name: m for name, m in results.items()
            if isinstance(m, dict) and "rps" in m and isinstance(m["rps"], float)
        }
        if not valid:
            return "xgboost"
        return min(valid, key=lambda k: valid[k]["rps"])
