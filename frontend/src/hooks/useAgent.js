import { useCallback, useEffect, useRef, useState } from 'react'
import { postAgent } from '../lib/api'

// Drives the natural-language agent. On a response it stores the plain-English
// answer and calls onResult(res) so App can draw any route/area the agent produced
// (reusing the existing map flow). Keeps a small text history for multi-turn.
export function useAgent(onResult) {
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer] = useState(null)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])

  // Keep the latest onResult without making `ask` change every render.
  const onResultRef = useRef(onResult)
  useEffect(() => {
    onResultRef.current = onResult
  }, [onResult])

  const ask = useCallback(
    async (message) => {
      setLoading(true)
      setError(null)
      setAnswer(null)
      try {
        const res = await postAgent({ message, history })
        setAnswer(res.answer)
        setHistory(res.history || [])
        onResultRef.current?.(res)
      } catch (err) {
        setError(err.message || 'The assistant is unavailable right now.')
      } finally {
        setLoading(false)
      }
    },
    [history],
  )

  return { ask, loading, answer, error }
}
