import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Course from './pages/Course'
import Challenge from './pages/Challenge'
import Stats from './pages/Stats'
import Grinder from './pages/Grinder'

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-background text-gray-100 font-mono">
        <nav className="border-b border-border bg-surface px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <h1 className="text-2xl font-bold text-primary">CyberLab</h1>
            <div className="flex gap-6">
              <a href="/" className="text-gray-400 hover:text-primary transition-colors">Courses</a>
              <a href="/grinder" className="text-gray-400 hover:text-primary transition-colors">Grinder</a>
              <a href="/stats" className="text-gray-400 hover:text-primary transition-colors">Stats</a>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/grinder" element={<Grinder />} />
            <Route path="/course/:id" element={<Course />} />
            <Route path="/challenge/:id" element={<Challenge />} />
            <Route path="/stats" element={<Stats />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
