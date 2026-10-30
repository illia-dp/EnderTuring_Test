import { queryOptions } from "@tanstack/react-query"
import { redirect } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { type Role, UsersService } from "@/client"
import { queryClient } from "./queryClient"

const roles = {
  viewUsers: ["admin", "manager"],
  manageUsers: ["admin"],
  viewMetrics: ["admin", "manager"],
} satisfies Record<string, Role[]>

type Access = keyof typeof roles

export function can(role: Role | undefined, access: Access): boolean {
  return role !== undefined && (roles[access] as Role[]).includes(role)
}

export const currentUserQueryOptions = queryOptions({
  queryKey: ["currentUser"],
  queryFn: async () => (await UsersService.readUserMe()).data,
  retry: false,
})

export class AccessDeniedError extends Error {}

export async function requireAccess(access: Access) {
  try {
    const user = await queryClient.fetchQuery(currentUserQueryOptions)
    if (!can(user.role, access)) throw new AccessDeniedError()
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 401) {
      throw redirect({ to: "/login" })
    }
    throw error
  }
}
