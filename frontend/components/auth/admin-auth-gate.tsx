"use client";

import { ReactNode, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSupabaseAuth } from "@/providers/supabase-provider";

export function AdminAuthGate({ children }: { children: ReactNode }) {
  const { session, loading, isConfigured } = useSupabaseAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && isConfigured && !session) {
      router.replace("/app/login");
    }
  }, [loading, session, router, isConfigured]);

  if (!isConfigured) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          Authentication is not configured. Update the required environment keys to access the admin workspace.
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <p className="text-sm text-zinc-500">Loading your admin workspace...</p>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  return <>{children}</>;
}
