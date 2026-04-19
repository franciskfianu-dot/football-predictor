import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import { getUpcomingFixtures, getAccuracyStats, type Fixture } from '@/utils/api'
import { usePredictionStore } from '@/store/predictionStore'
import clsx from 'clsx'

const LEAGUES = ['epl', 'laliga', 'seriea', 'bundesliga', 'ligue1']
const LEAGUE_LABELS: Record<string, string> = {
  epl: 'Premier League', laliga: 'La Liga', seriea: 'Serie A',
  bundesliga: 'Bundesliga', ligue1: 'Ligue 1',
}

function StatCard({ label, value, sub, color = 'indigo' }: {
  label: string; value: string; sub?: string; color?: string
}) {
  const colorMap: Record<string, string> = {
    indigo: 'text-indigo-400', green: 'text-green-400',
    amber: 'text-amber-400', blue: 'text-blue-400',
  }
  return (
    <div className="card p-4">
      <p className="stat-label">{label}</p>
      <p className={clsx('text-2xl font-bold mt-1', colorMap[color] || 'text-indigo-400')}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function FixtureRow({ fixture, league }: { fixture: Fixture; league: string }) {
  const dt = new Date(fixture.match_date)
  return (
    <Link
      to={`/predict?home=${encodeURIComponent(fixture.home_team)}&away=${encodeURIComponent(fixture.away_team)}&league=${league}&date=${fixture.match_date}`}
      className="flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors group"
    >
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <div className="text-center w-12 shrink-0">
          <p className="text-xs text-gray-500">{format(dt, 'EEE')}</p>
          <p className="text-sm font-medium text-gray-300">{format(dt, 'dd MMM')}</p>
          <p className="text-xs text-gray-600">{format(dt, 'HH:mm')}</p>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-200 truncate">{fixture.home_team}</span>
            <span className="text-xs text-gray-600">vs</span>
            <span className="text-sm text-gray-200 truncate">{fixture.away_team}</span>
          </div>
          {fixture.matchday && (
            <p className="text-xs text-gray-600 mt-0.5">Matchday {fixture.matchday}</p>
          )}
        </div>
      </div>
      <span className="text-xs text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity ml-3 shrink-0">
        Predict →
      </span>
    </Link>
  )
}

export default function Dashboard() {
  const history = usePredictionStore(s => s.history)

  const epl = useQuery({ queryKey: ['fixtures', 'epl'], queryFn: () => getUpcomingFixtures('epl') })
  const accuracy = useQuery({ queryKey: ['accuracy'], queryFn: () => getAccuracyStats() })

  const stats = accuracy.data

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          {format(new Date(), 'EEEE, d MMMM yyyy')} · AI-powered match prediction
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Exact score accuracy" value={stats?.exact_score_acc ? `${(stats.exact_score_acc * 100).toFixed(1)}%` : '—'} sub="Out-of-sample" color="green" />
        <StatCard label="Top-3 accuracy" value={stats?.top3_score_acc ? `${(stats.top3_score_acc * 100).toFixed(1)}%` : '—'} sub="Score in top 3 predictions" color="blue" />
        <StatCard label="Best RPS score" value={stats?.rps ? stats.rps.toFixed(4) : '—'} sub="Lower = better" color="indigo" />
        <StatCard label="EV bet ROI" value={stats?.roi_ev ? `${(stats.roi_ev * 100).toFixed(1)}%` : '—'} sub="Flagged bets historical" color="amber" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upcoming fixtures */}
        <div className="lg:col-span-2">
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
              <h2 className="font-semibold text-gray-200 text-sm">Upcoming fixtures</h2>
              <div className="flex gap-2">
                {LEAGUES.slice(0, 3).map(l => (
                  <span key={l} className="text-xs text-gray-500 hover:text-gray-300 cursor-pointer transition-colors">
                    {LEAGUE_LABELS[l]}
                  </span>
                ))}
              </div>
            </div>

            {epl.isLoading ? (
              <div className="p-6 text-center text-gray-600 text-sm">Loading fixtures…</div>
            ) : epl.data?.fixtures && epl.data.fixtures.length > 0 ? (
              <div className="divide-y divide-gray-800/50">
                {epl.data.fixtures.slice(0, 8).map(f => (
                  <FixtureRow key={f.match_id} fixture={f} league="epl" />
                ))}
              </div>
            ) : (
              <div className="p-6 text-center">
                <p className="text-gray-600 text-sm">No upcoming fixtures found.</p>
                <p className="text-gray-700 text-xs mt-1">Run initial data scrape to populate fixtures.</p>
              </div>
            )}

            <div className="px-4 py-3 border-t border-gray-800 bg-gray-900/50">
              <Link to="/predict" className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
                → Enter a custom match
              </Link>
            </div>
          </div>
        </div>

        {/* Recent predictions */}
        <div>
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <h2 className="font-semibold text-gray-200 text-sm">Recent predictions</h2>
            </div>

            {history.length === 0 ? (
              <div className="p-6 text-center">
                <p className="text-gray-600 text-sm">No predictions yet.</p>
                <Link to="/predict" className="btn-primary mt-3 text-xs px-3 py-1.5 inline-flex">
                  Make first prediction
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-gray-800/50">
                {history.slice(0, 6).map((h, i) => {
                  const pred = h.res.prediction
                  const topScore = pred.top_scores?.[0]
                  return (
                    <div key={i} className="px-4 py-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-gray-400 truncate">
                          {h.req.home_team} vs {h.req.away_team}
                        </span>
                        <span className={clsx(
                          'text-xs font-mono ml-2 shrink-0',
                          pred.confidence_band === 'high' ? 'text-green-400' :
                          pred.confidence_band === 'medium' ? 'text-amber-400' : 'text-gray-500'
                        )}>
                          {pred.confidence_band}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        {topScore && (
                          <span className="text-lg font-bold text-gray-100 font-mono">{topScore.score}</span>
                        )}
                        <div className="flex gap-2 text-xs text-gray-500">
                          <span className="text-blue-400">{(pred.prob_home_win * 100).toFixed(0)}%</span>
                          <span>{(pred.prob_draw * 100).toFixed(0)}%</span>
                          <span className="text-red-400">{(pred.prob_away_win * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      {pred.ev_flags?.length > 0 && (
                        <div className="mt-1">
                          <span className="badge-green">+EV {pred.ev_flags[0].ev_pct}%</span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Quick links */}
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Link to="/accuracy" className="card p-3 hover:bg-gray-800 transition-colors text-center">
              <p className="text-xs text-gray-500">Model accuracy</p>
              <p className="text-sm font-medium text-indigo-400 mt-1">View report →</p>
            </Link>
            <Link to="/models" className="card p-3 hover:bg-gray-800 transition-colors text-center">
              <p className="text-xs text-gray-500">Champion model</p>
              <p className="text-sm font-medium text-indigo-400 mt-1">Registry →</p>
            </Link>
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <p className="text-xs text-gray-700 text-center mt-8">
        Statistical model outputs only. Not financial or gambling advice. Gamble responsibly. 18+
      </p>
    </div>
  )
}
