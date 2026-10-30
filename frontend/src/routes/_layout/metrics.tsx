import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Suspense } from "react"
import { MetricsService } from "@/client"
import { requireAccess } from "@/lib/access"

export const Route = createFileRoute("/_layout/metrics")({
  beforeLoad: () => requireAccess("viewMetrics"),
  component: Metrics,
})

function MetricsContent() {
  const { data } = useSuspenseQuery({
    queryKey: ["metrics"],
    queryFn: async () => (await MetricsService.readMetrics()).data,
    retry: false,
  })
  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-lg border p-6">
        <dt>Active users</dt>
        <dd className="text-3xl font-bold">{data.active_users}</dd>
      </div>
      <div className="rounded-lg border p-6">
        <dt>Completed tasks</dt>
        <dd className="text-3xl font-bold">{data.completed_tasks}</dd>
      </div>
    </dl>
  )
}

function Metrics() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold">Metrics</h1>
      <p className="text-muted-foreground">
        Demo data — these are sample metrics.
      </p>
      <Suspense fallback={<p>Loading metrics…</p>}>
        <MetricsContent />
      </Suspense>
    </div>
  )
}
