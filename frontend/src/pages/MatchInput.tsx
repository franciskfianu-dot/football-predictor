import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { predictMatch, getLeagues, getTeams, type PredictRequest } from '@/utils/api'
import { usePredictionStore } from '@/store/predictionStore'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const LEAGUE_FLAGS: Record<string, string> = {
  epl: '🏴󠁧󠁢󠁥󠁮󠁧󠁿', laliga: '🇪🇸', seriea: '🇮🇹', bundesliga: '🇩🇪', ligue1: '🇫🇷',
}

const STEPS = ['League', 'Teams', 'Date & Options', 'Predict']

function StepIndicator({ step, current }: { step: number; current: number }) {
  return (
    <div className="flex items-center">
      <div className={clsx(
        'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all',
        step < current ? 'bg-indigo-600 text-white' :
        step === current ? 'bg-indigo-600 text-white ring-2 ring-indigo-400 ring-offset-2 ring-offset-gray-950' :
        'bg-gray-800 text-gray-600'
      )}>
        {step < current ? '✓' : step + 1}
      </div>
      {step < STEPS.length - 1 && (
        <div className={clsx('h-0.5 w-10 mx-1 transition-all', step < current ? 'bg-indigo-600' : 'bg-gray-800')} />
      )}
    </div>
  )
}

export default function MatchInput() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const setResult = usePredictionStore(s => s.setResult)

  const [step, setStep] = useState(0)
  const [league, setLeague] = useState(params.get('league') || '')
  const [homeTeam, setHomeTeam] = useState(params.get('home') || '')
  const [awayTeam, setAwayTeam] = useState(params.get('away') || '')
  const [matchDate, setMatchDate] = useState(
    params.get('date') || new Date().toISOString().slice(0, 16)
  )
  const [showOverrides, setShowOverrides] = useState(false)
  const [overrides, setOverrides] = useState<Record<string, string>>({})

  // Auto-advance if URL params prefilled
  useEffect(() => {
    if (league && homeTeam && awayTeam) setStep(2)
  }, [])

  const { data: leagues } = useQuery({
    queryKey: ['leagues'],
    queryFn: getLeagues,
  })

  const { data: teams } = useQuery({
    queryKey: ['teams', league],
    queryFn: () => getTeams(league),
    enabled: !!league,
  })

  const mutation = useMutation({
    mutationFn: (req: PredictRequest) => predictMatch(req),
    onSuccess: (data, req) => {
      setResult(req, data)
      navigate('/predict/result')
    },
    onError: (err: Error) => {
      toast.error(err.message || 'Prediction failed. Check API connection.')
    },
  })

  const handlePredict = () => {
    if (!league || !homeTeam || !awayTeam || !matchDate) {
      toast.error('Please fill in all required fields')
      return
    }

    const cleanOverrides: Record<string, number> = {}
    Object.entries(overrides).forEach(([k, v]) => {
      const n = parseFloat(v)
      if (!isNaN(n)) cleanOverrides[k] = n
    })

    mutation.mutate({
      home_team: homeTeam,
      away_team: awayTeam,
      league,
      match_date: new Date(matchDate).toISOString(),
      override_features: Object.keys(cleanOverrides).length > 0 ? cleanOverrides : undefined,
    })
  }

  const leagueTeams = teams || []

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100">Predict a Match</h1>
        <p className="text-sm text-gray-500 mt-1">Configure match details to generate predictions</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center mb-8">
        {STEPS.map((label, i) => (
          <div key={i} className="flex items-center">
            <div className="flex flex-col items-center">
              <StepIndicator step={i} current={step} />
              <span className={clsx(
                'text-xs mt-1.5 text-center',
                i === step ? 'text-gray-300' : 'text-gray-600'
              )}>{label}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="card p-6 space-y-5">

        {/* Step 0: League */}
        <div className={clsx(step !== 0 && 'hidden')}>
          <label className="block text-sm font-medium text-gray-300 mb-3">Select league</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {(leagues || [
              { slug: 'epl', name: 'Premier League', country: 'England' },
              { slug: 'laliga', name: 'La Liga', country: 'Spain' },
              { slug: 'seriea', name: 'Serie A', country: 'Italy' },
              { slug: 'bundesliga', name: 'Bundesliga', country: 'Germany' },
              { slug: 'ligue1', name: 'Ligue 1', country: 'France' },
            ]).map(l => (
              <button
                key={l.slug}
                onClick={() => { setLeague(l.slug); setStep(1) }}
                className={clsx(
                  'flex flex-col items-center gap-1 p-4 rounded-xl border transition-all',
                  league === l.slug
                    ? 'border-indigo-500 bg-indigo-600/10 text-indigo-300'
                    : 'border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600 hover:text-gray-200'
                )}
              >
                <span className="text-2xl">{LEAGUE_FLAGS[l.slug] || '⚽'}</span>
                <span className="text-sm font-medium">{l.name}</span>
                <span className="text-xs opacity-70">{l.country}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Step 1: Teams */}
        <div className={clsx(step !== 1 && 'hidden')}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Home team</label>
              {leagueTeams.length > 0 ? (
                <select
                  className="select"
                  value={homeTeam}
                  onChange={e => setHomeTeam(e.target.value)}
                >
                  <option value="">Select home team…</option>
                  {leagueTeams.map(t => (
                    <option key={t.id} value={t.name}>{t.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  className="input"
                  placeholder="e.g. Arsenal"
                  value={homeTeam}
                  onChange={e => setHomeTeam(e.target.value)}
                />
              )}
            </div>

            <div className="flex justify-center">
              <div className="w-8 h-8 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center">
                <span className="text-xs text-gray-500 font-medium">VS</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Away team</label>
              {leagueTeams.length > 0 ? (
                <select
                  className="select"
                  value={awayTeam}
                  onChange={e => setAwayTeam(e.target.value)}
                >
                  <option value="">Select away team…</option>
                  {leagueTeams.filter(t => t.name !== homeTeam).map(t => (
                    <option key={t.id} value={t.name}>{t.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  className="input"
                  placeholder="e.g. Chelsea"
                  value={awayTeam}
                  onChange={e => setAwayTeam(e.target.value)}
                />
              )}
            </div>
          </div>

          <div className="flex gap-3 mt-5">
            <button className="btn-secondary flex-1" onClick={() => setStep(0)}>← Back</button>
            <button
              className="btn-primary flex-1"
              onClick={() => homeTeam && awayTeam ? setStep(2) : toast.error('Select both teams')}
            >
              Continue →
            </button>
          </div>
        </div>

        {/* Step 2: Date & Options */}
        <div className={clsx(step !== 2 && 'hidden')}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Match date & time</label>
              <input
                type="datetime-local"
                className="input"
                value={matchDate}
                onChange={e => setMatchDate(e.target.value)}
              />
            </div>

            {/* Match summary */}
            <div className="bg-gray-800/60 rounded-lg p-4 border border-gray-700">
              <div className="flex items-center justify-center gap-4">
                <span className="font-semibold text-gray-200">{homeTeam || '—'}</span>
                <div className="text-center">
                  <span className="text-xs text-gray-600 block">{LEAGUE_FLAGS[league]} {league?.toUpperCase()}</span>
                  <span className="text-gray-600 font-mono">vs</span>
                </div>
                <span className="font-semibold text-gray-200">{awayTeam || '—'}</span>
              </div>
            </div>

            {/* Override toggle */}
            <button
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1"
              onClick={() => setShowOverrides(!showOverrides)}
            >
              {showOverrides ? '▾' : '▸'} Advanced: override input variables
            </button>

            {showOverrides && (
              <div className="bg-gray-800/50 rounded-lg p-4 space-y-3 border border-gray-700">
                <p className="text-xs text-gray-500">
                  Override specific features sent to the model. Leave blank to use scraped values.
                </p>
                {[
                  { key: 'home_all_form_points_5', label: 'Home avg pts (last 5)' },
                  { key: 'away_all_form_points_5', label: 'Away avg pts (last 5)' },
                  { key: 'home_key_players_available', label: 'Home availability (0–1)' },
                  { key: 'away_key_players_available', label: 'Away availability (0–1)' },
                  { key: 'weather_precipitation_mm', label: 'Rain (mm)' },
                ].map(({ key, label }) => (
                  <div key={key} className="flex items-center gap-3">
                    <label className="text-xs text-gray-400 w-44 shrink-0">{label}</label>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="auto"
                      className="input text-xs py-1.5"
                      value={overrides[key] || ''}
                      onChange={e => setOverrides(prev => ({
                        ...prev,
                        [key]: e.target.value,
                      }))}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex gap-3 mt-5">
            <button className="btn-secondary flex-1" onClick={() => setStep(1)}>← Back</button>
            <button className="btn-primary flex-1" onClick={() => setStep(3)}>Review →</button>
          </div>
        </div>

        {/* Step 3: Confirm & Predict */}
        <div className={clsx(step !== 3 && 'hidden')}>
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-300">Prediction summary</h3>

            <div className="bg-gray-800/60 rounded-xl p-5 border border-gray-700 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">League</span>
                <span className="text-gray-200 font-medium">{league?.toUpperCase()} {LEAGUE_FLAGS[league]}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Home team</span>
                <span className="text-gray-200 font-medium">{homeTeam}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Away team</span>
                <span className="text-gray-200 font-medium">{awayTeam}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Match date</span>
                <span className="text-gray-200 font-medium">{matchDate}</span>
              </div>
              {Object.keys(overrides).filter(k => overrides[k]).length > 0 && (
                <div className="pt-2 border-t border-gray-700">
                  <p className="text-xs text-amber-400">
                    ⚠ {Object.keys(overrides).filter(k => overrides[k]).length} variable(s) overridden
                  </p>
                </div>
              )}
            </div>

            <div className="text-xs text-gray-600 bg-gray-800/30 rounded-lg p-3 border border-gray-800">
              <strong className="text-gray-500">What happens next:</strong> The engine scrapes live data,
              engineers 50+ features, runs all 6 models, selects the champion, and returns predictions
              across all markets plus EV value analysis.
            </div>
          </div>

          {mutation.isPending && (
            <div className="mt-4">
              <div className="flex items-center gap-2 text-sm text-indigo-400 mb-2">
                <div className="w-3 h-3 rounded-full bg-indigo-500 animate-pulse" />
                Running prediction pipeline…
              </div>
              <div className="space-y-1.5 text-xs text-gray-600">
                <p>✓ Feature engineering</p>
                <p>✓ Loading champion model</p>
                <p className="animate-pulse">· Computing all markets…</p>
              </div>
            </div>
          )}

          <div className="flex gap-3 mt-5">
            <button className="btn-secondary" onClick={() => setStep(2)}>← Back</button>
            <button
              className="btn-primary flex-1"
              onClick={handlePredict}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? 'Predicting…' : '⚡ Run Prediction'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
