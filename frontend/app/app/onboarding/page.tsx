"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminAuthGate } from "@/components/auth/admin-auth-gate";
import { Button } from "@/components/ui/button";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import { fetchAdminOverview } from "@/lib/api";

export default function OnboardingPage() {
  const router = useRouter();
  const { signOut, user, accessToken, loading: authLoading, isConfigured } = useSupabaseAuth();
  const [checkingMembership, setCheckingMembership] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleSignOut = async () => {
    try {
      await signOut();
    } catch (error) {
      console.error("Failed to sign out", error);
    }
  };

  useEffect(() => {
    if (authLoading) {
      return;
    }

    if (!isConfigured) {
      setCheckingMembership(false);
      return;
    }

    if (!accessToken) {
      setCheckingMembership(false);
      return;
    }

    let active = true;
    setCheckingMembership(true);
    setError(null);

    fetchAdminOverview({ accessToken })
      .then((data) => {
        if (!active) return;
        if (data.org) {
          router.replace("/app/dashboard");
          return;
        }
        setCheckingMembership(false);
      })
      .catch((fetchError) => {
        if (!active) return;
        console.error("Failed to verify workspace membership", fetchError);
        setError("We couldn't verify your workspace status. Please try again in a moment.");
        setCheckingMembership(false);
      });

    return () => {
      active = false;
    };
  }, [accessToken, authLoading, isConfigured, router]);

  return (
    <AdminAuthGate>
      <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-6">
        <div className="w-full max-w-xl rounded-lg border border-dashed border-zinc-300 bg-white p-10 text-center shadow-sm">
          {checkingMembership ? (
            <p className="text-sm text-zinc-500">Checking your workspace status...</p>
          ) : (
            <>
              <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                Welcome, {user?.email ?? "new admin"}
              </span>
              <h1 className="mt-4 text-2xl font-semibold text-zinc-900">Let&apos;s set up your organization</h1>
              <p className="mt-3 text-sm leading-6 text-zinc-600">
                Your admin account is active, but you don&apos;t belong to an organization yet. Ask an existing
                owner to invite you or create a new workspace to start managing assessments.
              </p>
              <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Link href="/app/onboarding/create-organization" className="w-full sm:w-auto">
                  <Button className="w-full justify-center" variant="default">
                    Create a new organization
                  </Button>
                </Link>
                <Link href="/app/dashboard" className="w-full sm:w-auto">
                  <Button className="w-full justify-center" variant="secondary">
                    I&apos;ve been invited
                  </Button>
                </Link>
              </div>
              <div className="mt-6 text-xs text-zinc-500">
                Need help? Email <a href="mailto:admin@afterquery.com" className="text-blue-600">admin@afterquery.com</a> for onboarding support.
              </div>
              {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
              <Button onClick={handleSignOut} variant="link" className="mt-6 text-sm text-zinc-500">
                Sign out
              </Button>
            </>
          )}
        </div>
      </div>
    </AdminAuthGate>
  );
}
