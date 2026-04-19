from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date,
    ForeignKey, Text, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func
from datetime import datetime
import uuid


class Base(DeclarativeBase):
    pass


def gen_uuid():
    return str(uuid.uuid4())


# ─── Reference Tables ───────────────────────────────────────────────

class League(Base):
    __tablename__ = "leagues"

    id = Column(String, primary_key=True, default=gen_uuid)
    slug = Column(String(20), unique=True, nullable=False)   # epl, laliga, etc.
    name = Column(String(100), nullable=False)
    country = Column(String(50))
    logo_url = Column(String(500))
    fbref_id = Column(String(50))
    understat_name = Column(String(50))
    active = Column(Boolean, default=True)

    teams = relationship("Team", back_populates="league")
    matches = relationship("Match", back_populates="league")


class Team(Base):
    __tablename__ = "teams"

    id = Column(String, primary_key=True, default=gen_uuid)
    league_id = Column(String, ForeignKey("leagues.id"), nullable=False)
    name = Column(String(100), nullable=False)
    short_name = Column(String(30))
    fbref_id = Column(String(50))
    understat_id = Column(String(50))
    transfermarkt_id = Column(String(50))
    sofascore_id = Column(String(50))
    stadium_name = Column(String(100))
    stadium_lat = Column(Float)
    stadium_lon = Column(Float)
    stadium_capacity = Column(Integer)
    founded_year = Column(Integer)
    logo_url = Column(String(500))

    league = relationship("League", back_populates="teams")
    home_matches = relationship("Match", foreign_keys="Match.home_team_id", back_populates="home_team")
    away_matches = relationship("Match", foreign_keys="Match.away_team_id", back_populates="away_team")
    elo_history = relationship("EloRating", back_populates="team")

    __table_args__ = (
        UniqueConstraint("league_id", "name", name="uq_team_league_name"),
    )


# ─── Match Data ─────────────────────────────────────────────────────

class Match(Base):
    __tablename__ = "matches"

    id = Column(String, primary_key=True, default=gen_uuid)
    league_id = Column(String, ForeignKey("leagues.id"), nullable=False)
    season = Column(String(10), nullable=False)             # e.g. "2023-24"
    matchday = Column(Integer)
    match_date = Column(DateTime, nullable=False)
    home_team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    status = Column(String(20), default="scheduled")        # scheduled, live, finished

    # Full-time score
    home_goals = Column(Integer)
    away_goals = Column(Integer)

    # Half-time score
    home_goals_ht = Column(Integer)
    away_goals_ht = Column(Integer)

    # Extended stats
    home_xg = Column(Float)
    away_xg = Column(Float)
    home_shots = Column(Integer)
    away_shots = Column(Integer)
    home_shots_on_target = Column(Integer)
    away_shots_on_target = Column(Integer)
    home_possession = Column(Float)
    away_possession = Column(Float)
    home_pass_accuracy = Column(Float)
    away_pass_accuracy = Column(Float)
    home_ppda = Column(Float)                               # Passes Per Defensive Action
    away_ppda = Column(Float)
    home_set_piece_goals = Column(Integer)
    away_set_piece_goals = Column(Integer)
    home_corner_goals = Column(Integer)
    away_corner_goals = Column(Integer)

    # Contextual
    referee_id = Column(String, ForeignKey("referees.id"))
    attendance = Column(Integer)
    weather_temp_c = Column(Float)
    weather_humidity = Column(Float)
    weather_precipitation_mm = Column(Float)
    weather_wind_kmh = Column(Float)
    weather_condition = Column(String(50))

    # Metadata
    fbref_id = Column(String(50), unique=True)
    sofascore_id = Column(String(50))
    scraped_at = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    league = relationship("League", back_populates="matches")
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_matches")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_matches")
    referee = relationship("Referee", back_populates="matches")
    odds = relationship("MatchOdds", back_populates="match")
    predictions = relationship("Prediction", back_populates="match")

    __table_args__ = (
        Index("ix_match_date", "match_date"),
        Index("ix_match_league_season", "league_id", "season"),
        UniqueConstraint("home_team_id", "away_team_id", "match_date", name="uq_match"),
    )


class Referee(Base):
    __tablename__ = "referees"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False, unique=True)
    nationality = Column(String(50))
    avg_yellow_cards = Column(Float)
    avg_red_cards = Column(Float)
    avg_penalties_awarded = Column(Float)
    home_win_rate = Column(Float)
    matches_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    matches = relationship("Match", back_populates="referee")


# ─── Odds ────────────────────────────────────────────────────────────

class MatchOdds(Base):
    __tablename__ = "match_odds"

    id = Column(String, primary_key=True, default=gen_uuid)
    match_id = Column(String, ForeignKey("matches.id"), nullable=False)
    bookmaker = Column(String(50), nullable=False)
    market = Column(String(30), nullable=False)             # 1x2, btts, o25, cs, htft, ah
    selection = Column(String(50), nullable=False)          # home, draw, away, yes, no, 1-0, etc.
    opening_odds = Column(Float)
    closing_odds = Column(Float)
    implied_prob_opening = Column(Float)
    implied_prob_closing = Column(Float)
    scraped_at = Column(DateTime, default=func.now())

    match = relationship("Match", back_populates="odds")

    __table_args__ = (
        Index("ix_odds_match_market", "match_id", "market"),
        UniqueConstraint("match_id", "bookmaker", "market", "selection", name="uq_odds"),
    )


# ─── Team Strength Ratings ───────────────────────────────────────────

class EloRating(Base):
    __tablename__ = "elo_ratings"

    id = Column(String, primary_key=True, default=gen_uuid)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    rating = Column(Float, nullable=False, default=1500.0)
    date = Column(Date, nullable=False)
    match_id = Column(String, ForeignKey("matches.id"))
    updated_at = Column(DateTime, default=func.now())

    team = relationship("Team", back_populates="elo_history")

    __table_args__ = (
        Index("ix_elo_team_date", "team_id", "date"),
    )


class DixonColesParams(Base):
    __tablename__ = "dixon_coles_params"

    id = Column(String, primary_key=True, default=gen_uuid)
    league_id = Column(String, ForeignKey("leagues.id"), nullable=False)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    attack_param = Column(Float)
    defence_param = Column(Float)
    home_advantage = Column(Float)
    rho = Column(Float)                                     # low-score correction
    calculated_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("league_id", "team_id", name="uq_dc_team"),
    )


# ─── Engineered Features (cached per match) ──────────────────────────

class MatchFeatures(Base):
    __tablename__ = "match_features"

    id = Column(String, primary_key=True, default=gen_uuid)
    match_id = Column(String, ForeignKey("matches.id"), nullable=False, unique=True)
    features_json = Column(JSON)                            # full feature vector
    feature_version = Column(String(20))                    # version tag for recompute
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    match = relationship("Match")


# ─── ML Models Registry ──────────────────────────────────────────────

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(String, primary_key=True, default=gen_uuid)
    model_name = Column(String(50), nullable=False)         # xgboost, lgbm, dixon_coles, etc.
    league_id = Column(String, ForeignKey("leagues.id"))    # null = cross-league
    version = Column(String(20), nullable=False)
    mlflow_run_id = Column(String(50))
    is_champion = Column(Boolean, default=False)

    # Metrics
    rps_score = Column(Float)
    brier_score = Column(Float)
    log_loss = Column(Float)
    exact_score_acc = Column(Float)
    top3_score_acc = Column(Float)
    rmse_total_goals = Column(Float)
    roi_ev_bets = Column(Float)

    # Storage
    model_path = Column(String(500))                        # path on Fly.io volume
    feature_list = Column(JSON)
    trained_at = Column(DateTime, default=func.now())
    trained_on_seasons = Column(JSON)

    __table_args__ = (
        Index("ix_model_champion", "model_name", "is_champion"),
    )


# ─── Predictions ────────────────────────────────────────────────────

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(String, primary_key=True, default=gen_uuid)
    match_id = Column(String, ForeignKey("matches.id"), nullable=False)
    model_version_id = Column(String, ForeignKey("model_versions.id"))
    predicted_at = Column(DateTime, default=func.now())
    confidence_band = Column(String(10))                    # high, medium, low

    # 1X2
    prob_home_win = Column(Float)
    prob_draw = Column(Float)
    prob_away_win = Column(Float)

    # Goals
    prob_over_05 = Column(Float)
    prob_over_15 = Column(Float)
    prob_over_25 = Column(Float)
    prob_over_35 = Column(Float)
    prob_over_45 = Column(Float)
    prob_btts = Column(Float)

    # Score
    top_scores_json = Column(JSON)                          # [{score:"1-0", prob:0.12}, ...]
    score_heatmap_json = Column(JSON)                       # 6x6 matrix 0-0 to 5-5

    # HT/FT
    htft_json = Column(JSON)

    # Asian Handicap
    asian_handicap_json = Column(JSON)

    # EV analysis
    ev_flags_json = Column(JSON)                            # [{market, selection, ev, kelly, odds}]

    # SHAP
    shap_values_json = Column(JSON)                         # top 5 feature drivers

    match = relationship("Match", back_populates="predictions")


# ─── Betting Slip Tracking ───────────────────────────────────────────

class BetRecord(Base):
    __tablename__ = "bet_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    match_id = Column(String, ForeignKey("matches.id"), nullable=False)
    market = Column(String(30), nullable=False)
    selection = Column(String(50), nullable=False)
    model_prob = Column(Float)
    odds_taken = Column(Float)
    bookmaker = Column(String(50))
    ev_at_flag = Column(Float)
    kelly_fraction = Column(Float)
    stake_units = Column(Float)                             # in units of bankroll %
    actual_result = Column(String(10))                      # win, loss, void
    pnl_units = Column(Float)
    flagged_at = Column(DateTime, default=func.now())
    settled_at = Column(DateTime)


# ─── Scrape Health Log ───────────────────────────────────────────────

class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    source = Column(String(50), nullable=False)             # fbref, understat, etc.
    target_url = Column(String(1000))
    status = Column(String(20), nullable=False)             # success, failed, partial
    records_scraped = Column(Integer, default=0)
    error_message = Column(Text)
    duration_seconds = Column(Float)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)

    __table_args__ = (
        Index("ix_scrape_log_source_date", "source", "started_at"),
    )


# ─── Google Sheets Config ────────────────────────────────────────────

class SheetsConfig(Base):
    __tablename__ = "sheets_config"

    id = Column(String, primary_key=True, default=gen_uuid)
    spreadsheet_id = Column(String(100), nullable=False)
    spreadsheet_name = Column(String(200))
    input_sheet_name = Column(String(100), default="Predictions Input")
    output_sheet_name = Column(String(100), default="Predictions Output")
    betslip_sheet_name = Column(String(100), default="Bet Slip")
    last_synced_at = Column(DateTime)
    sync_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
