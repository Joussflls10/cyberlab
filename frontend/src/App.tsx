import { BrowserRouter as Router, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { BookOpen, Sparkles, BarChart3, Shield } from 'lucide-react'
import Home from './pages/Home'
import Course from './pages/Course'
import Challenge from './pages/Challenge'
import Stats from './pages/Stats'
import Grinder from './pages/Grinder'
import AdminCourseChallenges from './pages/AdminCourseChallenges'

const navItems = [
  { to: '/', label: 'Courses', icon: BookOpen },
  { to: '/grinder', label: 'Grinder', icon: Sparkles },
  { to: '/stats', label: 'Stats', icon: BarChart3 },
]

function AppContent() {
  const location = useLocation()
  const isImmersiveChallenge = location.pathname.startsWith('/challenge/')

  if (isImmersiveChallenge) {
    return (
      <Routes>
        <Route path="/challenge/:id" element={<Challenge />} />
      </Routes>
    )
  }

  return (
    <div className="min-h-screen bg-background text-gray-100 font-mono">
      <div className="mx-auto flex min-h-screen max-w-[1800px]">
        <aside className="hidden w-72 flex-col border-r border-border/80 bg-black/30 p-6 backdrop-blur-xl lg:flex">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/20 text-primary">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-white">CyberLab</h1>
              <p className="text-xs text-gray-500">Interactive Security Labs</p>
            </div>
          </div>

          <nav className="space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `group flex items-center gap-3 rounded-xl px-4 py-3 text-sm transition-all ${
                      isActive
                        ? 'border border-primary/30 bg-primary/10 text-primary shadow-[0_0_0_1px_rgba(0,255,136,0.08)]'
                        : 'border border-transparent text-gray-400 hover:border-border hover:bg-surface/80 hover:text-gray-200'
                    }`
                  }
                >
                  <Icon className="h-4 w-4" />
                  <span className="font-medium">{item.label}</span>
                </NavLink>
              )
            })}
          </nav>

          <div className="mt-auto rounded-xl border border-border bg-surface/70 p-4">
            <p className="text-xs uppercase tracking-wide text-gray-500">Environment</p>
            <p className="mt-1 text-sm text-gray-300">Backend + Sandbox Monitor</p>
            <div className="mt-3 flex items-center gap-2 text-xs text-primary">
              <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              Ready
            </div>
          </div>

        </aside>

        <main className="flex-1 px-4 py-4 sm:px-6 sm:py-6 lg:px-10 lg:py-8">
          <header className="mb-6 flex items-center justify-between rounded-2xl border border-border/70 bg-black/20 px-5 py-4 backdrop-blur-md lg:hidden">
            <div>
              <h1 className="text-lg font-semibold text-white">CyberLab</h1>
              <p className="text-xs text-gray-500">Security Learning Interface</p>
            </div>
            <span className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs text-primary">Live</span>
          </header>

          <div className="rounded-2xl border border-border/70 bg-gradient-to-b from-surface/80 to-black/20 p-4 pb-24 sm:p-6 sm:pb-24 lg:p-8 lg:pb-8">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/grinder" element={<Grinder />} />
              <Route path="/course/:id" element={<Course />} />
              <Route path="/challenge/:id" element={<Challenge />} />
              <Route path="/stats" element={<Stats />} />
              <Route path="/admin/courses/:id/challenges" element={<AdminCourseChallenges />} />
            </Routes>
          </div>
        </main>
      </div>

      <nav className="fixed inset-x-3 bottom-3 z-40 rounded-2xl border border-border/80 bg-black/85 px-2 py-2 backdrop-blur-xl lg:hidden">
        <div className="grid grid-cols-3 gap-1">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `flex items-center justify-center gap-2 rounded-xl px-2 py-2.5 text-xs transition-colors ${
                    isActive ? 'bg-primary/15 text-primary' : 'text-gray-400 hover:text-gray-200'
                  }`
                }
              >
                <Icon className="h-4 w-4" />
                <span className="font-medium">{item.label}</span>
              </NavLink>
            )
          })}
        </div>
      </nav>
    </div>
  )
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  )
}

export default App
