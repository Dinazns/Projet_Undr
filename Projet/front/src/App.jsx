import { HashRouter, Routes, Route } from 'react-router-dom'
import Hud from './pages/Hud'
import Dashboard from './pages/Dashboard'

function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/hud" element={<Hud />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<Hud />} />
      </Routes>
    </HashRouter>
  )
}

export default App
