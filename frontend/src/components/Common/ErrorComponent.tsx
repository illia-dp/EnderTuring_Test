import { Link } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { Button } from "@/components/ui/button"
import { AccessDeniedError } from "@/lib/access"

const ErrorComponent = ({ error }: { error?: unknown }) => {
  const forbidden =
    error instanceof AccessDeniedError ||
    (error instanceof AxiosError && error.response?.status === 403)
  return (
    <div
      className="flex min-h-screen items-center justify-center flex-col p-4"
      data-testid="error-component"
    >
      <div className="flex items-center z-10">
        <div className="flex flex-col ml-4 items-center justify-center p-4">
          <span className="text-6xl md:text-8xl font-bold leading-none mb-4">
            {forbidden ? "403" : "Error"}
          </span>
          <h1 className="text-2xl font-bold mb-2">
            {forbidden ? "Access Denied" : "Oops!"}
          </h1>
        </div>
      </div>

      <p className="text-lg text-muted-foreground mb-4 text-center z-10">
        {forbidden
          ? "You don’t have permission to view this page."
          : "Something went wrong. Please try again."}
      </p>
      <Link to="/">
        <Button>Go Home</Button>
      </Link>
    </div>
  )
}

export default ErrorComponent
