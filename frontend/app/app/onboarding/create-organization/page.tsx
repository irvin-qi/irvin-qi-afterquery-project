"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AdminAuthGate } from "@/components/auth/admin-auth-gate";
import { Button } from "@/components/ui/button";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import { createOrganization, fetchAdminOverview } from "@/lib/api";

export default function CreateOrganizationPage() {
  const router = useRouter();
  const { accessToken, loading: authLoading, isConfigured } = useSupabaseAuth();
  const [name, setName] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting">("idle");
  const [error, setError] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    if (authLoading) {
      return;
    }

    if (!isConfigured) {
      setInitializing(false);
      return;
    }

    if (!accessToken) {
      setInitializing(false);
      return;
    }

    let active = true;
    fetchAdminOverview({ accessToken })
      .then((data) => {
        if (!active) return;
        if (data.org) {
          router.replace("/app/dashboard");
          return;
        }
        setInitializing(false);
      })
      .catch((fetchError) => {
        if (!active) return;
        console.error("Failed to verify workspace membership", fetchError);
        setError("We couldn't verify your workspace status. Please try again in a moment.");
        setInitializing(false);
      });

    return () => {
      active = false;
    };
  }, [accessToken, authLoading, isConfigured, router]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status === "submitting") {
      return;
    }

    const normalizedName = name.trim();
    if (!normalizedName) {
      setError("Enter an organization name.");
      return;
    }

    if (!accessToken) {
      setError("You need to be signed in to create an organization.");
      return;
    }

    setStatus("submitting");
    setError(null);

    try {
      await createOrganization({ name: normalizedName }, { accessToken });
      router.replace("/app/dashboard");
    } catch (createError) {
      console.error("Failed to create organization", createError);
      if (createError instanceof Error) {
        if (createError.message.includes("409")) {
          setError("An organization with this name already exists. Try another name.");
        } else {
          setError(createError.message);
        }
      } else {
        setError("We couldn't create the organization. Please try again.");
      }
      setStatus("idle");
    }
  };

  return (
    <AdminAuthGate>
      <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-6">
        <div className="w-full max-w-xl rounded-lg border border-dashed border-zinc-300 bg-white p-10 text-center shadow-sm">
          {initializing ? (
            <p className="text-sm text-zinc-500">Preparing your onboarding experience...</p>
          ) : (
            <>
              <h1 className="text-2xl font-semibold text-zinc-900">Create your organization</h1>
              <p className="mt-3 text-sm leading-6 text-zinc-600">
                Choose a name for your organization. You&apos;ll be set up as the owner so you can start inviting
                teammates and managing assessments.
              </p>
              <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-2 text-left">
                  <label className="text-sm font-medium text-zinc-700" htmlFor="organization-name">
                    Organization name
                  </label>
                  <input
                    id="organization-name"
                    type="text"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Afterquery Labs"
                    className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-200"
                  />
                </div>
                <Button className="w-full" type="submit" disabled={status === "submitting"}>
                  {status === "submitting" ? "Creating..." : "Create organization"}
                </Button>
              </form>
              {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
              <p className="mt-6 text-xs text-zinc-500">
                Already have an invitation? <Link href="/app/onboarding" className="text-blue-600">Return to onboarding</Link>.
              </p>
            </>
          )}
        </div>
      </div>
    </AdminAuthGate>
  );
}
