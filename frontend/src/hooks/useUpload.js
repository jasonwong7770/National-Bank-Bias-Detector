import { useState } from 'react'
import axios from 'axios'

export function useUpload() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]         = useState(null)
  const [result, setResult]       = useState(null)

  async function upload(file) {
    setIsLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResult(response.data)
      return response.data
    } catch (err) {
      const message =
        err.response?.data?.detail ||
        err.message ||
        'Upload failed.'
      setError(message)
      return null
    } finally {
      setIsLoading(false)
    }
  }

  return { upload, isLoading, error, result }
}
