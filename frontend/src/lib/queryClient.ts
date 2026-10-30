import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query"
import { AxiosError } from "axios"
import { toast } from "sonner"

function handleApiError(error: Error) {
  if (error instanceof AxiosError && error.response?.status === 401) {
    localStorage.removeItem("access_token")
    queryClient.clear()
    window.location.href = "/login"
  }
  if (error instanceof AxiosError && error.response?.status === 403) {
    toast.error("Access denied. You don't have permission for this action.")
  }
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleApiError }),
  mutationCache: new MutationCache({ onError: handleApiError }),
})
