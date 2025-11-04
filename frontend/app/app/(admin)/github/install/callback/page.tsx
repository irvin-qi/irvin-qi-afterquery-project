"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { completeGitHubInstallation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { useAdminData } from "@/providers/admin-data-provider";
import { useSupabaseAuth } from "@/providers/supabase-provider";

export default function GitHubInstallCallbackPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { dispatch, refreshAdminData } = useAdminData();
  const { accessToken, loading: authLoading } = useSupabaseAuth();

  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [destinationPath, setDestinationPath] = useState<string>("/app/dashboard");

  const setupAction = useMemo(() => searchParams.get("setup_action") ?? "install", [searchParams]);

  // Log full URL and all params on mount
  useEffect(() => {
    console.log("=== GitHub Callback Page Loaded ===");
    console.log("Full URL:", typeof window !== 'undefined' ? window.location.href : 'N/A');
    console.log("Pathname:", typeof window !== 'undefined' ? window.location.pathname : 'N/A');
    console.log("Search:", typeof window !== 'undefined' ? window.location.search : 'N/A');
    console.log("All URL params:", Object.fromEntries(new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')));
    console.log("SearchParams from Next.js:", {
      state: searchParams.get("state"),
      installation_id: searchParams.get("installation_id"),
      setup_action: searchParams.get("setup_action"),
    });
    console.log("Auth state:", {
      authLoading,
      hasAccessToken: !!accessToken,
    });
    
    // If no params at all, GitHub probably didn't redirect here
    if (typeof window !== 'undefined' && !window.location.search) {
      console.warn("⚠️ WARNING: No query parameters found. GitHub may not have redirected here, or the Callback URL in GitHub App settings is incorrect.");
    }
  }, [searchParams, authLoading, accessToken]);

  useEffect(() => {
    console.log("=== Callback useEffect running ===", { authLoading, hasAccessToken: !!accessToken });
    
    if (authLoading) {
      console.log("Waiting for auth to finish loading...");
      return;
    }

    const stateParam = searchParams.get("state");
    const installationIdParam = searchParams.get("installation_id");
    const setupActionParam = searchParams.get("setup_action");
    
    // Debug logging
    console.log("GitHub callback page - URL params:", {
      state: stateParam ? "present" : "missing",
      installation_id: installationIdParam,
      setup_action: setupActionParam,
      hasAccessToken: !!accessToken,
      fullUrl: typeof window !== 'undefined' ? window.location.href : 'N/A',
    });
    
    // Check if we have the required parameters
    if (!stateParam || !installationIdParam) {
      console.error("Missing required parameters:", { stateParam, installationIdParam });
      setStatus("error");
      if (setupActionParam) {
        setErrorMessage(
          "The installation was not completed. Make sure you clicked 'Install' or 'Update' on the GitHub page and selected your organization (not your personal account)."
        );
      } else {
        setErrorMessage(
          "Missing installation parameters from GitHub. This usually means the installation was not completed. Please try connecting again and make sure to complete the installation on GitHub by selecting your organization and clicking 'Install'."
        );
      }
      return;
    }

    const installationId = Number(installationIdParam);
    if (!Number.isFinite(installationId)) {
      console.error("Invalid installation ID:", installationIdParam);
      setStatus("error");
      setErrorMessage("GitHub returned an invalid installation id. Please try connecting again.");
      return;
    }

    if (!accessToken) {
      console.error("No access token available");
      setStatus("error");
      setErrorMessage("Sign in to finalize the GitHub App connection.");
      return;
    }

    let active = true;
    setStatus("pending");
    setErrorMessage(null);

    console.log("Completing GitHub installation...", { stateParam, installationId, accessToken: !!accessToken });
    console.log("API endpoint will be: POST /api/github/installations/complete");
    console.log("Request body will be:", { state: stateParam, installation_id: installationId });

    completeGitHubInstallation(stateParam, installationId, { accessToken })
      .then(({ installation, returnPath }) => {
        if (!active) return;
        console.log("GitHub installation completed successfully:", installation);
        dispatch({ type: "setGitHubInstallation", payload: installation });
        // Trigger a refresh to ensure backend data is fetched
        refreshAdminData();
        setStatus("success");
        const target =
          returnPath && returnPath.startsWith("/") ? returnPath : "/app/dashboard";
        // Add a query parameter to signal that GitHub was just installed
        const targetWithParam = target.includes("?")
          ? `${target}&github_installed=true`
          : `${target}?github_installed=true`;
        setDestinationPath(target);
        console.log("Redirecting to:", targetWithParam);
        
        // Also try to notify the parent window if it exists (in case original tab is still open)
        try {
          if (window.opener) {
            window.opener.postMessage({ type: "GITHUB_INSTALLATION_COMPLETE" }, window.location.origin);
          }
        } catch (e) {
          console.log("Could not notify parent window:", e);
        }
        
        setTimeout(() => {
          router.replace(targetWithParam);
        }, 1500);
      })
      .catch((error) => {
        if (!active) return;
        console.error("GitHub installation completion error:", error);
        let message = error instanceof Error ? error.message : "Failed to finalize the GitHub connection.";
        
        // Provide more helpful error messages
        if (message.includes("Organization")) {
          message = "The GitHub App must be installed on an organization, not a personal account. Please install it on your organization and try again.";
        } else if (message.includes("404") || message.includes("not found")) {
          message = "Could not find the GitHub installation. Make sure you completed the installation on GitHub by selecting your organization and clicking 'Install'.";
        } else if (message.includes("expired")) {
          message = "The installation link has expired. Please try connecting again.";
        } else if (message.includes("502")) {
          message = "Unable to communicate with GitHub. Please check your GitHub App configuration and try again.";
        }
        
        setErrorMessage(message);
        setStatus("error");
      });

    return () => {
      active = false;
    };
  }, [accessToken, authLoading, dispatch, router, searchParams, refreshAdminData]);

  const description = useMemo(() => {
    if (status === "success") {
      return "GitHub App connected. Redirecting you back to where you started.";
    }
    if (status === "error") {
      return errorMessage ?? "Something went wrong while connecting the GitHub App.";
    }
    return setupAction === "update"
      ? "Updating permissions for your GitHub App installation."
      : "Finishing the GitHub App installation for your project.";
  }, [errorMessage, setupAction, status]);

  // Check if this page was loaded directly (no GitHub redirect)
  const hasNoParams = typeof window !== 'undefined' && !window.location.search;
  
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>GitHub App connection</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Show warning if no params - GitHub didn't redirect here */}
          {hasNoParams && (
            <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
              <p className="font-semibold mb-2">⚠️ No GitHub redirect detected</p>
              <p className="text-xs mb-2">This page loaded without query parameters, which means GitHub didn&apos;t redirect here after installation.</p>
              <div className="bg-white p-2 rounded border border-red-200 text-xs">
                <p className="font-medium mb-1">Check your GitHub App settings:</p>
                <ol className="list-decimal list-inside space-y-1 text-xs">
                  <li>Go to: GitHub → Your Organization → Settings → Developer settings → GitHub Apps → Your App</li>
                  <li>Find &quot;User authorization callback URL&quot;</li>
                  <li>It MUST be set exactly to: <code className="bg-red-100 px-1 rounded">{typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000'}/app/github/install/callback</code></li>
                  <li>Make sure you completed the installation on GitHub (clicked &quot;Install&quot;)</li>
                </ol>
              </div>
            </div>
          )}
          
          {/* Debug info - show what params we received */}
          {typeof window !== 'undefined' && !hasNoParams && (
            <div className="rounded-md border border-gray-200 bg-gray-50 p-2 text-xs font-mono">
              <p className="font-semibold mb-1">Debug Info:</p>
              <p>URL: {window.location.href}</p>
              <p>State param: {searchParams.get("state") ? "✅ Present" : "❌ Missing"}</p>
              <p>Installation ID: {searchParams.get("installation_id") || "❌ Missing"}</p>
              <p>Setup action: {searchParams.get("setup_action") || "None"}</p>
              <p>Has access token: {accessToken ? "✅ Yes" : "❌ No"}</p>
              <p>Auth loading: {authLoading ? "⏳ Yes" : "✅ No"}</p>
            </div>
          )}
          
          {status === "pending" ? (
            <p className="text-sm text-zinc-600">We're confirming your installation with GitHub…</p>
          ) : null}
          {status === "success" ? (
            <p className="text-sm text-green-600">Success! You'll be redirected shortly.</p>
          ) : null}
          {status === "error" && errorMessage ? (
            <div className="space-y-3">
              <p className="text-sm text-red-600">{errorMessage}</p>
              {errorMessage.includes("organization") || errorMessage.includes("not completed") ? (
                <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700">
                  <p className="font-medium mb-1">Important: Install on your organization</p>
                  <ul className="list-disc list-inside space-y-1 text-xs">
                    <li>Make sure you select your organization (not your personal account) when installing</li>
                    <li>Choose "All repositories" when prompted</li>
                    <li>Complete the installation by clicking "Install" or "Update"</li>
                    <li>Verify the GitHub App's Callback URL is set correctly in the app settings</li>
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
        <CardFooter className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => router.replace(destinationPath)}>Return to workspace</Button>
          {status === "error" ? (
            <Button onClick={() => router.replace(destinationPath)}>Try again</Button>
          ) : null}
        </CardFooter>
      </Card>
    </div>
  );
}
