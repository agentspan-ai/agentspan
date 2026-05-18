import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './docs/index.css'
import { ApiDocsPage } from './docs/api-docs-page'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ApiDocsPage />
  </StrictMode>,
)
