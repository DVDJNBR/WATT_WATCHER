/**
 * App — router shell. Layout provides shared chrome (header, tab nav);
 * routes swap between the dashboard and the "À propos" page.
 */
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import OriginPage from './pages/OriginPage.jsx'
import PipelinePage from './pages/PipelinePage.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="origine" element={<OriginPage />} />
          <Route path="pipeline" element={<PipelinePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
