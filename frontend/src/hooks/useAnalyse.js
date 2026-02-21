import { useState } from 'react'
import axios from 'axios'

export function useAnalyse() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]         = useState(null)
  const [result, setResult]       = useState(null)

  async function analyse(file, sensitivity, maxGap) {
    setIsLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await axios.post('/api/analyse/all', formData, {
        params: {
          sensitivity,
          max_gap: maxGap,
        },
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      setResult(response.data)
      return response.data
    } catch (err) {
      const message =
        err.response?.data?.detail ||
        err.message ||
        'An unexpected error occurred.'
      setError(message)
      return null
    } finally {
      setIsLoading(false)
    }
  }

  return { analyse, isLoading, error, result }
}
