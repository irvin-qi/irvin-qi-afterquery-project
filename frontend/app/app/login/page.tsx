"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import { fetchAdminOverview } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { supabase, session, loading, isConfigured, accessToken } = useSupabaseAuth();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (loading || !session || !isConfigured || redirecting) {
      return;
    }

    const token = accessToken ?? session.access_token ?? null;
    if (!token) {
      return;
    }

    let active = true;
    setRedirecting(true);

    fetchAdminOverview({ accessToken: token })
      .then((data) => {
        if (!active) return;
        if (data.org) {
          router.replace("/app/dashboard");
        } else {
          router.replace("/app/onboarding");
        }
      })
      .catch((fetchError) => {
        if (!active) return;
        console.error("Failed to verify workspace after sign-in", fetchError);
        router.replace("/app/onboarding");
      });

    return () => {
      active = false;
    };
  }, [loading, session, router, isConfigured, accessToken, redirecting]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email) {
      return;
    }
    if (!supabase || !isConfigured) {
      setError("Authentication is not configured for this environment.");
      return;
    }
    setStatus("sending");
    setError(null);

    const { error: signInError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        shouldCreateUser: true,
        emailRedirectTo: `${window.location.origin}/app/dashboard`,
      },
    });

    if (signInError) {
      setError(signInError.message);
      setStatus("idle");
      return;
    }

    setStatus("sent");
  };

  const isButtonDisabled = status === "sending" || status === "sent" || !isConfigured;
  const buttonLabel = !isConfigured
    ? "Authentication not configured"
    : status === "sending"
      ? "Sending magic link..."
      : status === "sent"
        ? "Link sent"
        : "Send magic link";

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-blue-50 to-zinc-50 px-6">
      <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-8 shadow-lg">
        <div>
          <p className="text-xs uppercase tracking-wide text-blue-600">Afterquery</p>
          <h1 className="mt-2 text-2xl font-semibold text-zinc-900">Sign in to continue</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Admin access uses passwordless email links. Enter your email to receive a login link.
          </p>
        </div>
        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700" htmlFor="email">
              Work email
            </label>
            <input
              id="email"
              type="email"
              required
              placeholder="alex@afterquery.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-200"
            />
          </div>
          <Button className="w-full" type="submit" disabled={isButtonDisabled}>
            {buttonLabel}
          </Button>
        </form>
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
        {status === "sent" && !error && (
          <div className="mt-4 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700">
            Check your inbox for a magic link to finish signing in.
          </div>
        )}
        {!isConfigured && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
            Configure the required authentication environment variables to enable email sign-in.
          </div>
        )}
        <p className="mt-6 text-center text-xs text-zinc-500">
          Need an account? <Link href="/" className="text-blue-600">Contact the platform admin.</Link>
        </p>
      </div>
    </div>
  );
}
