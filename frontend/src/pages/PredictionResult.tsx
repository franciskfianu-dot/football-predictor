import { useNavigate } from 'react-router-dom'
import { usePredictionStore } from '@/store/predictionStore'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import clsx from 'clsx'

function ProbBar({ label, prob, color }: { label: string; prob: number; color: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-200 font-mono">{(prob * 100).toFixed(1)}%</span>
      </div>
      <div className="prob-bar">
        <div className={clsx('prob-bar-fill', color)} style={{ width: `${prob * 100}%` }} />
      </div>
    </div>
  )
}

function ConfidenceBadge({ band }: { band: string }) {
  const map: Record<string, { cls: string; label: string }> = {
    high:   { cls: 'badge-green', label: 'High confidence' },
    medium: { cls: 'badge-amber', label: 'Medium confidence' },
    low:    { cls: 'badge-red',   label: 'Low confidence' },
  }
  const { cls, label } = map[band] || map.low
  return <span className={cls}>{label}</span>
}

function EVCard({ flag }: { flag: any }) {
  return (
    <div className={clsx(
      'p-3 rounded-lg border',
      flag.ev_pct >= 10
        ? 'border-green-800/60 bg-green-900/20'
        : 'border-green-800/40 bg-green-900/10'
    )}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">
            {flag.market} · {flag.selection}
          </p>
          <div className="flex items-baseline gap-2 mt-0.5">
            <span className="text-base font-bold text-green-400">+{flag.ev_pct}% EV</span>
            <span className="text-xs text-gray-500">@ {flag.odds}</span>
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-500">Kelly stake</p>
          <p className="text-sm font-semibold text-amber-400">{flag.kelly_pct}%</p>
        </div>
      </div>
      <div className="mt-2 flex gap-3 text-xs text-gray-500">
        <span>Model: {(flag.model_prob * 100).toFixed(1)}%</span>
        <span>Implied: {(100 / flag.odds).toFixed(1)}%</span>
        <span>{flag.bookmaker}</span>
      </div>
    </div>
  )
}

export default function PredictionResult() {
  const navigate = useNavigate()
  const { lastResult: res, lastRequest: req } = usePredictionStore()

  if (!res || !req) {
    return (
      <div className="p-6 text-center">
        <p className="text-gray-500">No prediction loaded.</p>
        <button className="btn-primary mt-4" onClick={() => navigate('/predict')}>Make a prediction</button>
      </div>
    )
  }

  const pred = res.prediction
  const topScore = pred.top_scores?.[0]

  const scoreChartData = (pred.top_scores || []).slice(0, 8).map(s => ({
    name: s.score,
    prob: parseFloat((s.prob * 100).toFixed(1)),
    home: s.home,
    away: s.away,
  }))

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            className="text-xs text-gray-500 hover:text-gray-300 mb-2 flex items-center gap-1"
            onClick={() => navigate('/predict')}
          >
            ← New prediction
          </button>
          <h1 className="text-xl font-bold text-gray-100">
            {req.home_team} <span className="text-gray-600">vs</span> {req.away_team}
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-sm text-gray-500">{req.league?.toUpperCase()}</span>
            <span className="text-gray-700">·</span>
            <span className="text-sm text-gray-500">{new Date(req.match_date).toLocaleDateString()}</span>
            <ConfidenceBadge band={pred.confidence_band} />
            {res.data_coverage !== 'full' && (
              <span className="badge-amber">⚠ {res.data_coverage} data</span>
            )}
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-600">Model</p>
          <p className="text-xs text-gray-400 font-mono">{pred.model_name}</p>
        </div>
      </div>

      {/* Top predicted score + 1X2 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Most likely score */}
        <div className="card p-5 text-center md:col-span-1">
          <p className="stat-label mb-2">Most likely score</p>
          {topScore ? (
            <>
              <div className="text-5xl font-bold text-gray-100 font-mono tracking-tight my-3">
                {topScore.home}
                <span className="text-gray-600 mx-1">–</span>
                {topScore.away}
              </div>
              <p className="text-sm text-indigo-400 font-medium">{(topScore.prob * 100).toFixed(1)}% probability</p>
            </>
          ) : <p className="text-gray-600">—</p>}
          {pred.top_scores?.[1] && (
            <p className="text-xs text-gray-600 mt-2">
              Alt: {pred.top_scores[1].score} ({(pred.top_scores[1].prob * 100).toFixed(1)}%)
            </p>
          )}
        </div>

        {/* 1X2 probabilities */}
        <div className="card p-5 md:col-span-2">
          <p className="stat-label mb-3">Match result</p>
          <div className="space-y-3">
            <ProbBar label={`${req.home_team} Win`} prob={pred.prob_home_win} color="bg-blue-500" />
            <ProbBar label="Draw" prob={pred.prob_draw} color="bg-gray-500" />
            <ProbBar label={`${req.away_team} Win`} prob={pred.prob_away_win} color="bg-red-500" />
          </div>
          <div className="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-gray-800">
            {[
              { label: '1X', val: pred.double_chance?.['1x'] },
              { label: 'X2', val: pred.double_chance?.x2 },
              { label: '12', val: pred.double_chance?.['12'] },
            ].map(({ label, val }) => (
              <div key={label} className="text-center">
                <p className="text-xs text-gray-600">Dbl {label}</p>
                <p className="text-sm font-semibold text-gray-300">{val ? `${(val * 100).toFixed(1)}%` : '—'}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Score probability chart */}
      <div className="card p-5">
        <p className="stat-label mb-4">Top 8 score probabilities</p>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={scoreChartData} barSize={28}>
            <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis hide />
            <Tooltip
              contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
              formatter={(v: number) => [`${v}%`, 'Probability']}
            />
            <Bar dataKey="prob" radius={[4, 4, 0, 0]}>
              {scoreChartData.map((_entry, i) => (
                <Cell
                  key={i}
                  fill={i === 0 ? '#6366f1' : i < 3 ? '#4338ca' : '#1e1b4b'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Goals markets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5">
          <p className="stat-label mb-3">Goals markets</p>
          <div className="space-y-2.5">
            {[
              { label: 'Over 0.5', val: pred.prob_over_05 },
              { label: 'Over 1.5', val: pred.prob_over_15 },
              { label: 'Over 2.5', val: pred.prob_over_25 },
              { label: 'Over 3.5', val: pred.prob_over_35 },
              { label: 'Over 4.5', val: pred.prob_over_45 },
              { label: 'BTTS',     val: pred.prob_btts },
            ].map(({ label, val }) => (
              <div key={label} className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{label}</span>
                <div className="flex items-center gap-3">
                  <div className="w-24 prob-bar">
                    <div
                      className={clsx('prob-bar-fill', val > 0.6 ? 'bg-green-500' : val > 0.4 ? 'bg-amber-500' : 'bg-gray-500')}
                      style={{ width: `${(val || 0) * 100}%` }}
                    />
                  </div>
                  <span className={clsx(
                    'text-xs font-mono w-10 text-right',
                    val > 0.6 ? 'text-green-400' : val > 0.4 ? 'text-amber-400' : 'text-gray-500'
                  )}>{val ? `${(val * 100).toFixed(1)}%` : '—'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Asian Handicap */}
        <div className="card p-5">
          <p className="stat-label mb-3">Asian handicap</p>
          <div className="space-y-2">
            {pred.asian_handicap && Object.entries(pred.asian_handicap)
              .filter(([k]) => [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5].includes(parseFloat(k)))
              .map(([hcp, vals]) => {
                const v = vals as any
                return (
                  <div key={hcp} className="flex items-center justify-between text-xs">
                    <span className="text-gray-500 w-12">{parseFloat(hcp) > 0 ? '+' : ''}{hcp}</span>
                    <div className="flex gap-3 flex-1 justify-end">
                      <span className="text-blue-400 w-10 text-right">{(v.home * 100).toFixed(1)}%</span>
                      {v.push > 0.001 && <span className="text-gray-600 w-10 text-right">{(v.push * 100).toFixed(1)}%</span>}
                      <span className="text-red-400 w-10 text-right">{(v.away * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                )
              })}
          </div>
          <p className="text-xs text-gray-700 mt-2">Blue = home · Red = away</p>
        </div>
      </div>

      {/* HT/FT */}
      <div className="card p-5">
        <p className="stat-label mb-3">Half-time / Full-time</p>
        <div className="grid grid-cols-3 gap-2">
          {pred.htft && Object.entries(pred.htft).map(([combo, prob]) => {
            const [ht, ft] = combo.split('')
            const labels: Record<string, string> = { H: 'Home', D: 'Draw', A: 'Away' }
            return (
              <div key={combo} className={clsx(
                'p-2 rounded-lg text-center border',
                (prob as number) > 0.12 ? 'border-indigo-700/50 bg-indigo-900/20' : 'border-gray-800 bg-gray-800/30'
              )}>
                <p className="text-xs text-gray-500">{labels[ht]} / {labels[ft]}</p>
                <p className={clsx(
                  'text-sm font-semibold mt-0.5',
                  (prob as number) > 0.12 ? 'text-indigo-300' : 'text-gray-400'
                )}>{((prob as number) * 100).toFixed(1)}%</p>
              </div>
            )
          })}
        </div>
      </div>

      {/* EV Betting Value */}
      {pred.ev_flags && pred.ev_flags.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <p className="stat-label">Value bets identified</p>
            <span className="badge-green">{pred.ev_flags.length} flagged</span>
          </div>
          <div className="space-y-2">
            {pred.ev_flags.map((flag, i) => <EVCard key={i} flag={flag} />)}
          </div>
          <p className="text-xs text-gray-700 mt-3 bg-gray-800/40 rounded p-2">
            ⚠ Statistical model outputs only. Not financial or gambling advice.
            Kelly % is a maximum suggested allocation — never bet more than you can afford to lose. 18+
          </p>
        </div>
      )}

      {/* SHAP Feature Drivers */}
      {pred.shap_drivers && pred.shap_drivers.length > 0 && (
        <div className="card p-5">
          <p className="stat-label mb-3">Key prediction drivers</p>
          <div className="space-y-2">
            {pred.shap_drivers.map((d, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-400 font-mono text-xs truncate flex-1">{d.feature}</span>
                <div className="flex items-center gap-3 ml-4">
                  <span className="text-gray-500 text-xs w-12 text-right font-mono">{d.value.toFixed(2)}</span>
                  <div className="w-20 prob-bar">
                    <div
                      className="prob-bar-fill bg-indigo-500"
                      style={{ width: `${Math.min(d.importance / (pred.shap_drivers[0]?.importance || 1) * 100, 100)}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-xs text-gray-700 text-center pb-4">
        {res.disclaimer}
      </p>
    </div>
  )
}
