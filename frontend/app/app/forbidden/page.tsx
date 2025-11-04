"use client";

import { AdminAuthGate } from "@/components/auth/admin-auth-gate";
import { Button } from "@/components/ui/button";
import { useSupabaseAuth } from "@/providers/supabase-provider";

export default function ForbiddenPage() {
  const { signOut, user } = useSupabaseAuth();

  const handleSignOut = async () => {
    try {
      await signOut();
    } catch (error) {
      console.error("Failed to sign out", error);
    }
  };

  return (
    <AdminAuthGate>
      <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-6">
        <div className="w-full max-w-lg rounded-lg border border-red-200 bg-white p-10 text-center shadow-sm">
          <span className="inline-flex items-center rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-700">
            Access pending
          </span>
          <h1 className="mt-4 text-2xl font-semibold text-zinc-900">Waiting for approval</h1>
          <p className="mt-3 text-sm leading-6 text-zinc-600">
            {user?.email ?? "Your account"} is linked to an organization, but an owner still needs to
            approve your access. We&apos;ll send you an email as soon as your role is activated.
          </p>
          <div className="mt-8 space-y-3">
            <p className="text-xs text-zinc-500">
              Reach out to your organization owner or contact <a href="mailto:admin@afterquery.com" className="text-blue-600">admin@afterquery.com</a> if you believe this is a mistake.
            </p>
            <Button onClick={handleSignOut} variant="link" className="text-sm text-zinc-500">
              Sign out
            </Button>
          </div>
        </div>
      </div>
    </AdminAuthGate>
  );
}
