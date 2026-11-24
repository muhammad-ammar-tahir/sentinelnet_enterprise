/**
 * hooks/usePolicies.ts — Recovery Policies Hook
 *
 * Fetches all recovery policies from GET /api/policies.
 * Also exposes a mutation for creating a new policy.
 *
 * Usage:
 *   const { data: policies, isLoading } = usePolicies()
 *   const { mutate: createPolicy } = useCreatePolicy()
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPolicies, createPolicy, updatePolicy, deletePolicy, type Policy, type CreatePolicyPayload } from '@/api/policies'

export function usePolicies() {
  return useQuery<Policy[]>({
    queryKey: ['policies'],
    queryFn: fetchPolicies,
  })
}

export function useCreatePolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreatePolicyPayload) => createPolicy(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] })
    },
  })
}

export function useUpdatePolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<CreatePolicyPayload> }) =>
      updatePolicy(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] })
    },
  })
}

export function useDeletePolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deletePolicy(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] })
    },
  })
}
