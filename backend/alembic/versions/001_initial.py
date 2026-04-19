"""Initial schema — all tables

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # leagues
    op.create_table('leagues',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('slug', sa.String(20), unique=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('country', sa.String(50)),
        sa.Column('logo_url', sa.String(500)),
        sa.Column('fbref_id', sa.String(50)),
        sa.Column('understat_name', sa.String(50)),
        sa.Column('active', sa.Boolean(), default=True),
    )

    # teams
    op.create_table('teams',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('league_id', sa.String(), sa.ForeignKey('leagues.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('short_name', sa.String(30)),
        sa.Column('fbref_id', sa.String(50)),
        sa.Column('understat_id', sa.String(50)),
        sa.Column('transfermarkt_id', sa.String(50)),
        sa.Column('sofascore_id', sa.String(50)),
        sa.Column('stadium_name', sa.String(100)),
        sa.Column('stadium_lat', sa.Float()),
        sa.Column('stadium_lon', sa.Float()),
        sa.Column('stadium_capacity', sa.Integer()),
        sa.Column('founded_year', sa.Integer()),
        sa.Column('logo_url', sa.String(500)),
        sa.UniqueConstraint('league_id', 'name', name='uq_team_league_name'),
    )

    # referees
    op.create_table('referees',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('nationality', sa.String(50)),
        sa.Column('avg_yellow_cards', sa.Float()),
        sa.Column('avg_red_cards', sa.Float()),
        sa.Column('avg_penalties_awarded', sa.Float()),
        sa.Column('home_win_rate', sa.Float()),
        sa.Column('matches_count', sa.Integer(), default=0),
        sa.Column('updated_at', sa.DateTime()),
    )

    # matches
    op.create_table('matches',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('league_id', sa.String(), sa.ForeignKey('leagues.id'), nullable=False),
        sa.Column('season', sa.String(10), nullable=False),
        sa.Column('matchday', sa.Integer()),
        sa.Column('match_date', sa.DateTime(), nullable=False),
        sa.Column('home_team_id', sa.String(), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('away_team_id', sa.String(), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('status', sa.String(20), default='scheduled'),
        sa.Column('home_goals', sa.Integer()),
        sa.Column('away_goals', sa.Integer()),
        sa.Column('home_goals_ht', sa.Integer()),
        sa.Column('away_goals_ht', sa.Integer()),
        sa.Column('home_xg', sa.Float()),
        sa.Column('away_xg', sa.Float()),
        sa.Column('home_shots', sa.Integer()),
        sa.Column('away_shots', sa.Integer()),
        sa.Column('home_shots_on_target', sa.Integer()),
        sa.Column('away_shots_on_target', sa.Integer()),
        sa.Column('home_possession', sa.Float()),
        sa.Column('away_possession', sa.Float()),
        sa.Column('home_pass_accuracy', sa.Float()),
        sa.Column('away_pass_accuracy', sa.Float()),
        sa.Column('home_ppda', sa.Float()),
        sa.Column('away_ppda', sa.Float()),
        sa.Column('home_set_piece_goals', sa.Integer()),
        sa.Column('away_set_piece_goals', sa.Integer()),
        sa.Column('home_corner_goals', sa.Integer()),
        sa.Column('away_corner_goals', sa.Integer()),
        sa.Column('referee_id', sa.String(), sa.ForeignKey('referees.id')),
        sa.Column('attendance', sa.Integer()),
        sa.Column('weather_temp_c', sa.Float()),
        sa.Column('weather_humidity', sa.Float()),
        sa.Column('weather_precipitation_mm', sa.Float()),
        sa.Column('weather_wind_kmh', sa.Float()),
        sa.Column('weather_condition', sa.String(50)),
        sa.Column('fbref_id', sa.String(50), unique=True),
        sa.Column('sofascore_id', sa.String(50)),
        sa.Column('scraped_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.UniqueConstraint('home_team_id', 'away_team_id', 'match_date', name='uq_match'),
    )
    op.create_index('ix_match_date', 'matches', ['match_date'])
    op.create_index('ix_match_league_season', 'matches', ['league_id', 'season'])

    # match_odds
    op.create_table('match_odds',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('match_id', sa.String(), sa.ForeignKey('matches.id'), nullable=False),
        sa.Column('bookmaker', sa.String(50), nullable=False),
        sa.Column('market', sa.String(30), nullable=False),
        sa.Column('selection', sa.String(50), nullable=False),
        sa.Column('opening_odds', sa.Float()),
        sa.Column('closing_odds', sa.Float()),
        sa.Column('implied_prob_opening', sa.Float()),
        sa.Column('implied_prob_closing', sa.Float()),
        sa.Column('scraped_at', sa.DateTime()),
        sa.UniqueConstraint('match_id', 'bookmaker', 'market', 'selection', name='uq_odds'),
    )
    op.create_index('ix_odds_match_market', 'match_odds', ['match_id', 'market'])

    # elo_ratings
    op.create_table('elo_ratings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('team_id', sa.String(), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('rating', sa.Float(), nullable=False, default=1500.0),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('match_id', sa.String(), sa.ForeignKey('matches.id')),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('ix_elo_team_date', 'elo_ratings', ['team_id', 'date'])

    # dixon_coles_params
    op.create_table('dixon_coles_params',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('league_id', sa.String(), sa.ForeignKey('leagues.id'), nullable=False),
        sa.Column('team_id', sa.String(), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('attack_param', sa.Float()),
        sa.Column('defence_param', sa.Float()),
        sa.Column('home_advantage', sa.Float()),
        sa.Column('rho', sa.Float()),
        sa.Column('calculated_at', sa.DateTime()),
        sa.UniqueConstraint('league_id', 'team_id', name='uq_dc_team'),
    )

    # match_features
    op.create_table('match_features',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('match_id', sa.String(), sa.ForeignKey('matches.id'), nullable=False, unique=True),
        sa.Column('features_json', sa.JSON()),
        sa.Column('feature_version', sa.String(20)),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    # model_versions
    op.create_table('model_versions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('model_name', sa.String(50), nullable=False),
        sa.Column('league_id', sa.String(), sa.ForeignKey('leagues.id')),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('mlflow_run_id', sa.String(50)),
        sa.Column('is_champion', sa.Boolean(), default=False),
        sa.Column('rps_score', sa.Float()),
        sa.Column('brier_score', sa.Float()),
        sa.Column('log_loss', sa.Float()),
        sa.Column('exact_score_acc', sa.Float()),
        sa.Column('top3_score_acc', sa.Float()),
        sa.Column('rmse_total_goals', sa.Float()),
        sa.Column('roi_ev_bets', sa.Float()),
        sa.Column('model_path', sa.String(500)),
        sa.Column('feature_list', sa.JSON()),
        sa.Column('trained_at', sa.DateTime()),
        sa.Column('trained_on_seasons', sa.JSON()),
    )
    op.create_index('ix_model_champion', 'model_versions', ['model_name', 'is_champion'])

    # predictions
    op.create_table('predictions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('match_id', sa.String(), sa.ForeignKey('matches.id'), nullable=False),
        sa.Column('model_version_id', sa.String(), sa.ForeignKey('model_versions.id')),
        sa.Column('predicted_at', sa.DateTime()),
        sa.Column('confidence_band', sa.String(10)),
        sa.Column('prob_home_win', sa.Float()),
        sa.Column('prob_draw', sa.Float()),
        sa.Column('prob_away_win', sa.Float()),
        sa.Column('prob_over_05', sa.Float()),
        sa.Column('prob_over_15', sa.Float()),
        sa.Column('prob_over_25', sa.Float()),
        sa.Column('prob_over_35', sa.Float()),
        sa.Column('prob_over_45', sa.Float()),
        sa.Column('prob_btts', sa.Float()),
        sa.Column('top_scores_json', sa.JSON()),
        sa.Column('score_heatmap_json', sa.JSON()),
        sa.Column('htft_json', sa.JSON()),
        sa.Column('asian_handicap_json', sa.JSON()),
        sa.Column('ev_flags_json', sa.JSON()),
        sa.Column('shap_values_json', sa.JSON()),
    )

    # bet_records
    op.create_table('bet_records',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('match_id', sa.String(), sa.ForeignKey('matches.id'), nullable=False),
        sa.Column('market', sa.String(30), nullable=False),
        sa.Column('selection', sa.String(50), nullable=False),
        sa.Column('model_prob', sa.Float()),
        sa.Column('odds_taken', sa.Float()),
        sa.Column('bookmaker', sa.String(50)),
        sa.Column('ev_at_flag', sa.Float()),
        sa.Column('kelly_fraction', sa.Float()),
        sa.Column('stake_units', sa.Float()),
        sa.Column('actual_result', sa.String(10)),
        sa.Column('pnl_units', sa.Float()),
        sa.Column('flagged_at', sa.DateTime()),
        sa.Column('settled_at', sa.DateTime()),
    )

    # scrape_logs
    op.create_table('scrape_logs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('target_url', sa.String(1000)),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('records_scraped', sa.Integer(), default=0),
        sa.Column('error_message', sa.Text()),
        sa.Column('duration_seconds', sa.Float()),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
    )
    op.create_index('ix_scrape_log_source_date', 'scrape_logs', ['source', 'started_at'])

    # sheets_config
    op.create_table('sheets_config',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('spreadsheet_id', sa.String(100), nullable=False),
        sa.Column('spreadsheet_name', sa.String(200)),
        sa.Column('input_sheet_name', sa.String(100), default='Predictions Input'),
        sa.Column('output_sheet_name', sa.String(100), default='Predictions Output'),
        sa.Column('betslip_sheet_name', sa.String(100), default='Bet Slip'),
        sa.Column('last_synced_at', sa.DateTime()),
        sa.Column('sync_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime()),
    )


def downgrade() -> None:
    tables = [
        'sheets_config', 'scrape_logs', 'bet_records', 'predictions',
        'model_versions', 'match_features', 'dixon_coles_params',
        'elo_ratings', 'match_odds', 'matches', 'referees', 'teams', 'leagues',
    ]
    for t in tables:
        op.drop_table(t)
