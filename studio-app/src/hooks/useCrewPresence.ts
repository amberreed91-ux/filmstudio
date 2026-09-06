import { useQuery } from '@tanstack/react-query'
import { crewPresenceRows } from '../lib/crewPresence'
import { getCrewIntelligenceOverview } from '../lib/studioApi'

export function useCrewPresence(projectId?: string) {
  const query = useQuery({
    queryKey: ['crew-presence', projectId],
    enabled: Boolean(projectId),
    queryFn: async () => {
      const overview = await getCrewIntelligenceOverview(projectId!)
      if (overview.project_id !== projectId) throw new Error('Crew status belongs to a different film.')
      return overview
    },
    staleTime: 10_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: 1,
  })
  return {
    agents: query.isError ? [] : crewPresenceRows(query.data, projectId),
    loading: Boolean(projectId) && query.isPending,
    error: query.isError ? 'Crew status is unavailable. You can still open the co-director to ask for guidance.' : '',
    refresh: query.refetch,
  }
}
