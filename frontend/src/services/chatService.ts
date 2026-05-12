import { AxiosInstance } from 'axios'

export type ChatMode = 'default' | 'repo_overview'

export const queryChat = async (
  api: AxiosInstance,
  repoId: string,
  query: string,
  mode: ChatMode = 'default',
  conversationId?: string | null
) => {
  const { data } = await api.post('/chat/query', {
    repo_id: repoId,
    query,
    mode,
    conversation_id: conversationId ?? undefined
  })
  return data
}
