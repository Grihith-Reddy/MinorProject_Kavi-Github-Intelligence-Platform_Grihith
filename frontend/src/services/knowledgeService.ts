import { AxiosInstance } from 'axios'

export interface GitVisualizationPullRequest {
  github_pr_number?: number | null
  title?: string | null
  state?: string | null
  base_branch?: string | null
  head_branch?: string | null
  created_at?: string | null
  merged_at?: string | null
  event_at?: string | null
}

export interface GitVisualizationResponse {
  repository?: {
    id?: string
    full_name?: string
    default_branch?: string | null
  }
  pull_requests?: GitVisualizationPullRequest[]
}

export const listKnowledgeEntries = async (api: AxiosInstance, repoId: string) => {
  const { data } = await api.get(`/knowledge/repositories/${repoId}/entries`)
  return data
}

export const getKnowledgeEntry = async (api: AxiosInstance, entryId: string) => {
  const { data } = await api.get(`/knowledge/entries/${entryId}`)
  return data
}

export const listKnowledgeTimeline = async (api: AxiosInstance, repoId: string) => {
  const { data } = await api.get(`/knowledge/repositories/${repoId}/timeline`)
  return data
}

export const getGitVisualization = async (api: AxiosInstance, repoId: string, limit = 500) => {
  const { data } = await api.get(`/knowledge/repositories/${repoId}/git-visualization`, {
    params: { limit },
  })
  return data as GitVisualizationResponse
}

export const getProjectEvolution = async (api: AxiosInstance, repoId: string) => {
  const { data } = await api.get(`/knowledge/repositories/${repoId}/evolution`)
  return data
}

export const listKnowledgeFiles = async (api: AxiosInstance, repoId: string) => {
  const { data } = await api.get(`/knowledge/repositories/${repoId}/files`)
  return data
}

export const getFileDetails = async (api: AxiosInstance, repoId: string, path: string) => {
  const { data } = await api.get(`/knowledge/files`, { params: { repo_id: repoId, path } })
  return data
}
