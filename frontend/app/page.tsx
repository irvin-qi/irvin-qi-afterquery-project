import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function LandingPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center px-6 text-center">
      <span className="rounded-full bg-blue-100 px-4 py-1 text-xs font-semibold uppercase tracking-wide text-blue-700">
        Afterquery Platform
      </span>
      <h1 className="mt-6 text-balance text-4xl font-bold tracking-tight text-zinc-900 sm:text-5xl">
        Candidate code reviews without the GitHub headaches.
      </h1>
      <p className="mt-4 max-w-2xl text-balance text-lg text-zinc-600">
        Manage seeds, invite candidates, and review submissions across your engineering org.
        Purpose-built workflows from the architecture plan bring clarity to every take-home.
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
        <Button asChild>
          <Link href="/app/login">Sign in as admin</Link>
        </Button>
      </div>
    </div>
  );
}
