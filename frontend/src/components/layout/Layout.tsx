import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { healthCheck } from '@/utils/api'
import clsx from 'clsx'

const NAV = [
  { to: '/',         label: 'Dashboard',       icon: '⬡' },
  { to: '/predict',  label: 'Predict Match',   icon: '◎' },
  { to: '/accuracy', label: 'Accuracy',        icon: '◈' },
  { to: '/models',   label: 'Model Registry',  icon: '◉' },
  { to: '/explore',  label: 'Variable Explorer', icon: '◍' },
  { to: '/settings/sheets', label: 'Google Sheets', icon: '◧' },
]

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: healthCheck,
    refetchInterval: 60_000,
    retry: false,
  })

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex flex-col bg-gray-900 border-r border-gray-800 flex-shrink-0">
        {/* Logo */}
        <div className="px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center">
              <span className="text-white text-xs font-bold">FQ</span>
            </div>
            <span className="font-semibold text-gray-100 text-sm">FootballIQ</span>
          </div>
          <p className="text-xs text-gray-600 mt-1">Prediction Engine</p>
        </div>

        {/* Nav links */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-indigo-600/20 text-indigo-400 font-medium'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                )
              }
            >
              <span className="text-base leading-none w-4 text-center shrink-0">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Status indicator */}
        <div className="px-4 py-3 border-t border-gray-800">
          <div className="flex items-center gap-2">
            <div className={clsx(
              'w-2 h-2 rounded-full',
              health?.status === 'ok' ? 'bg-green-500' : 'bg-amber-500'
            )} />
            <span className="text-xs text-gray-500">
              {health?.status === 'ok' ? 'All systems operational' : 'Checking…'}
            </span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
