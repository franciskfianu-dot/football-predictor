import { create } from 'zustand'
import type { PredictionResponse, PredictRequest } from '@/utils/api'

interface PredictionStore {
  lastRequest: PredictRequest | null
  lastResult: PredictionResponse | null
  history: { req: PredictRequest; res: PredictionResponse; timestamp: string }[]
  setResult: (req: PredictRequest, res: PredictionResponse) => void
  clearResult: () => void
}

export const usePredictionStore = create<PredictionStore>((set) => ({
  lastRequest: null,
  lastResult: null,
  history: [],
  setResult: (req, res) =>
    set((s) => ({
      lastRequest: req,
      lastResult: res,
      history: [
        { req, res, timestamp: new Date().toISOString() },
        ...s.history.slice(0, 19),
      ],
    })),
  clearResult: () => set({ lastRequest: null, lastResult: null }),
}))
