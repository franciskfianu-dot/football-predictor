/// <reference types="vite/client" />

import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || 'Unknown error'
    console.error('[API Error]', msg)
    return Promise.reject(new Error(msg))
  }
)

// ── Types ─────────────────────────────────────────────────────────────

export interface PredictRequest {
  home_team: string
  away_team: string
  league: string
  match_date: string
  override_features?: Record<string, number>
}

export interface ScoreEntry { score: string; prob: number; home: number; away: number }

export interface EVFlag {
  market: string
  selection: string
  model_prob: number
  odds: number
  ev_pct: number
  kelly_pct: number
  bookmaker: string
  value_rating: 'high' | 'medium'
}

export interface ShapDriver { feature: string; importance: number; value: number }

export interface PredictionResult {
  confidence_band: 'high' | 'medium' | 'low'
  prob_home_win: number
  prob_draw: number
  prob_away_win: number
  prob_btts: number
  prob_over_05: number
  prob_over_15: number
  prob_over_25: number
  prob_over_35: number
  prob_over_45: number
  top_scores: ScoreEntry[]
  score_matrix: number[][]
  htft: Record<string, number>
  asian_handicap: Record<string, { home: number; push: number; away: number }>
  winning_margin: Record<string, number>
  double_chance: { '1x': number; x2: number; '12': number }
  draw_no_bet: { home: number; away: number }
  ev_flags: EVFlag[]
  shap_drivers: ShapDriver[]
  model_name: string
  warning?: string
}

export interface PredictionResponse {
  home_team: string
  away_team: string
  league: string
  match_date: string
  prediction: PredictionResult
  features_used: string[]
  data_coverage: 'full' | 'partial' | 'limited'
  disclaimer: string
}

export interface Fixture {
  match_id: string
  home_team: string
  away_team: string
  match_date: string
  matchday?: number
}

export interface League {
  id: string
  slug: string
  name: string
  country: string
}

export interface ModelVersion {
  id: string
  model_name: string
  league_id: string
  version: string
  is_champion: boolean
  rps_score?: number
  brier_score?: number
  exact_score_acc?: number
  top3_score_acc?: number
  trained_at: string
}

// ── API Methods ───────────────────────────────────────────────────────

export const predictMatch = (req: PredictRequest) =>
  api.post<PredictionResponse>('/api/v1/predictions/predict', req).then(r => r.data)

export const batchPredict = (matches: PredictRequest[]) =>
  api.post('/api/v1/predictions/batch', { matches }).then(r => r.data)

export const getUpcomingFixtures = (league: string) =>
  api.get<{ league: string; fixtures: Fixture[] }>(`/api/v1/predictions/upcoming/${league}`).then(r => r.data)

export const getLeagues = () =>
  api.get<League[]>('/api/v1/leagues/').then(r => r.data)

export const getTeams = (leagueSlug: string) =>
  api.get<{ id: string; name: string }[]>(`/api/v1/leagues/${leagueSlug}/teams`).then(r => r.data)

export const getModelVersions = () =>
  api.get<ModelVersion[]>('/api/v1/models/').then(r => r.data)

export const getAccuracyStats = (league?: string) =>
  api.get('/api/v1/models/accuracy', { params: { league } }).then(r => r.data)

export const getScrapeHealth = () =>
  api.get('/api/v1/admin/status', {
    headers: { 'x-admin-token': import.meta.env.VITE_ADMIN_TOKEN || '' }
  }).then(r => r.data)

export const syncSheets = (spreadsheetId: string) =>
  api.post('/api/v1/sheets/sync', { spreadsheet_id: spreadsheetId }).then(r => r.data)

export const getSheetsConfig = () =>
  api.get('/api/v1/sheets/config').then(r => r.data)

export const saveSheetsConfig = (config: { spreadsheet_id: string; service_account_json: string }) =>
  api.post('/api/v1/sheets/config', config).then(r => r.data)

export const healthCheck = () =>
  api.get('/health').then(r => r.data)

export default api
