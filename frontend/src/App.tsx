import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import Dashboard from '@/pages/Dashboard'
import MatchInput from '@/pages/MatchInput'
import PredictionResult from '@/pages/PredictionResult'
import Accuracy from '@/pages/Accuracy'
import SheetsConnector from '@/pages/SheetsConnector'
import VariableExplorer from '@/pages/VariableExplorer'
import ModelRegistry from '@/pages/ModelRegistry'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="predict" element={<MatchInput />} />
          <Route path="predict/result" element={<PredictionResult />} />
          <Route path="accuracy" element={<Accuracy />} />
          <Route path="settings/sheets" element={<SheetsConnector />} />
          <Route path="explore" element={<VariableExplorer />} />
          <Route path="models" element={<ModelRegistry />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
