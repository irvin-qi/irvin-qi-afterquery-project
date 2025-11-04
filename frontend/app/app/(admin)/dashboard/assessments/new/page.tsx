"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAdminData } from "@/providers/admin-data-provider";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import { createAssessment, createSeed, startGitHubInstallation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function NewAssessmentPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { state, dispatch, currentAdmin, org, githubInstallation, refreshAdminData } = useAdminData();
  const { accessToken, user: supabaseUser } = useSupabaseAuth();
  const [formState, setFormState] = useState({
    title: "",
    description: "",
    instructions: "",
    seedId: state.seeds[0]?.id ?? "",
    timeToStartHours: 72,
    timeToCompleteHours: 48,
    candidateEmailSubject: "You're invited to an Afterquery assessment",
    candidateEmailBody: "Hi {candidate_name}, excited to see your work!",
  });
  const [showSeedForm, setShowSeedForm] = useState(state.seeds.length === 0);
  const [seedFormState, setSeedFormState] = useState({
    repoInput: "",
    defaultBranch: "main",
  });
  const [seedError, setSeedError] = useState<string | null>(null);
  const [creatingSeed, setCreatingSeed] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [connectingGitHub, setConnectingGitHub] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const isGitHubConnected = githubInstallation?.connected ?? false;

  // Refresh data if returning from GitHub installation
  useEffect(() => {
    const githubInstalled = searchParams.get("github_installed");
    if (githubInstalled === "true") {
      refreshAdminData();
      // Clean up the URL parameter
      router.replace("/app/dashboard/assessments/new");
    }
  }, [searchParams, refreshAdminData, router]);

  // Listen for messages from the callback page (when opened in new tab)
  useEffect(() => {
    if (isGitHubConnected) {
      return; // Already connected, no need to check
    }

    const handleMessage = (event: MessageEvent) => {
      // Verify message is from same origin
      if (event.origin !== window.location.origin) {
        return;
      }
      
      if (event.data?.type === "GITHUB_INSTALLATION_COMPLETE") {
        console.log("Received GitHub installation complete message, refreshing...");
        // Refresh immediately when we get the message
        refreshAdminData();
      }
    };

    // Check for GitHub installation when window regains focus (user returns from new tab)
    const handleFocus = () => {
      console.log("Window regained focus, checking GitHub connection...");
      // Small delay to ensure any pending requests complete
      setTimeout(() => {
        refreshAdminData();
      }, 500);
    };

    window.addEventListener("message", handleMessage);
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("message", handleMessage);
      window.removeEventListener("focus", handleFocus);
    };
  }, [isGitHubConnected, refreshAdminData]);

  // Also periodically check if not connected (every 5 seconds for 2 minutes)
  useEffect(() => {
    if (isGitHubConnected) {
      return; // Already connected, no need to poll
    }

    let attempts = 0;
    const maxAttempts = 24; // 24 * 5 seconds = 2 minutes

    const interval = setInterval(() => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(interval);
        return;
      }
      refreshAdminData();
    }, 5000); // Check every 5 seconds

    return () => {
      clearInterval(interval);
    };
  }, [isGitHubConnected, refreshAdminData]);

  useEffect(() => {
    if (isGitHubConnected) {
      setConnectError(null);
    }
  }, [isGitHubConnected]);

  useEffect(() => {
    setFormState((prev) => {
      const hasExistingSeed = prev.seedId && state.seeds.some((seed) => seed.id === prev.seedId);
      const fallbackSeedId = state.seeds[0]?.id ?? "";
      if (hasExistingSeed || fallbackSeedId === prev.seedId) {
        return prev;
      }
      return { ...prev, seedId: fallbackSeedId };
    });
  }, [state.seeds]);

  useEffect(() => {
    if (state.seeds.length === 0) {
      setShowSeedForm(true);
    }
  }, [state.seeds.length]);

  if (!org) {
    return null;
  }

  const hasSeeds = state.seeds.length > 0;

  async function handleConnectGitHub() {
    if (connectingGitHub) return;
    setConnectError(null);

    if (!org) {
      setConnectError("Create or join an organization before connecting GitHub");
      return;
    }

    if (!accessToken) {
      setConnectError("Sign in to connect the GitHub App");
      return;
    }

    try {
      setConnectingGitHub(true);
      // Use NEXT_PUBLIC_FRONTEND_APP_URL if available (for Docker/production), 
      // otherwise fall back to window.location.origin
      const frontendOrigin = typeof process !== 'undefined' && process.env.NEXT_PUBLIC_FRONTEND_APP_URL
        ? new URL(process.env.NEXT_PUBLIC_FRONTEND_APP_URL).origin
        : window.location.origin;
      const callbackUrl = `${frontendOrigin}/app/github/install/callback`;
      const returnPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      
      // Log for debugging (can be removed in production)
      console.log('GitHub installation callback URL:', callbackUrl);
      
      const installationUrl = await startGitHubInstallation(org.id, {
        accessToken,
        redirectUrl: callbackUrl,
        returnPath,
      });
      console.log('Opening GitHub installation URL:', installationUrl);
      console.log('⚠️ IMPORTANT: GitHub will redirect to the Callback URL set in your GitHub App settings, NOT the redirect_url parameter.');
      console.log('Make sure your GitHub App Callback URL is set to:', callbackUrl);
      window.open(installationUrl, "_blank");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start GitHub installation";
      console.error('GitHub installation error:', error);
      setConnectError(message);
    } finally {
      setConnectingGitHub(false);
    }
  }

  async function handleCreateSeed() {
    if (creatingSeed) return;
    setSeedError(null);

    if (!org) {
      setSeedError("Create or join an organization before adding repositories");
      return;
    }

    if (!isGitHubConnected) {
      setSeedError("Connect the GitHub App before adding repositories");
      return;
    }

    const trimmedInput = seedFormState.repoInput.trim();
    if (!trimmedInput) {
      setSeedError("Enter a template repository link");
      return;
    }

    if (!accessToken) {
      setSeedError("Sign in to add repositories");
      return;
    }

    let repoUrl: string;
    let repoFullName: string;
    try {
      const parsed = new URL(
        trimmedInput.startsWith("http://") || trimmedInput.startsWith("https://")
          ? trimmedInput
          : `https://github.com/${trimmedInput}`,
      );
      const pathSegments = parsed.pathname.split("/").filter(Boolean);
      if (pathSegments.length < 2) {
        throw new Error("Invalid repository path");
      }
      repoFullName = `${pathSegments[0]}/${pathSegments[1]}`;
      repoUrl = `https://github.com/${repoFullName}`;
    } catch (error) {
      setSeedError("Enter a valid GitHub repository URL or owner/name");
      return;
    }

    const defaultBranch = seedFormState.defaultBranch.trim() || "main";

    try {
      setCreatingSeed(true);
      const newSeed = await createSeed(
        {
          orgId: org.id,
          sourceRepoUrl: repoUrl,
          defaultBranch,
        },
        { accessToken },
      );
      dispatch({ type: "createSeed", payload: newSeed });
      setFormState((prev) => ({ ...prev, seedId: newSeed.id }));
      setSeedFormState({ repoInput: "", defaultBranch: "main" });
      setShowSeedForm(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to add repository";
      if (message.includes('409')) {
        setSeedError('Connect the GitHub App before adding repositories.');
      } else {
        setSeedError(message);
      }
    } finally {
      setCreatingSeed(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!formState.title || !formState.seedId) {
      setFormError("Title and seed are required");
      return;
    }

    if (!accessToken) {
      setFormError("Sign in to create assessments");
      return;
    }

    if (!org) {
      setFormError("Create or join an organization before creating assessments");
      return;
    }

    setFormError(null);
    setIsSubmitting(true);
    try {
      const newAssessment = await createAssessment(
        {
          orgId: org.id,
          seedId: formState.seedId,
          title: formState.title,
          description: formState.description,
          instructions: formState.instructions,
          candidateEmailSubject: formState.candidateEmailSubject,
          candidateEmailBody: formState.candidateEmailBody,
          timeToStartHours: Number(formState.timeToStartHours),
          timeToCompleteHours: Number(formState.timeToCompleteHours),
          createdBy: currentAdmin?.id ?? supabaseUser?.id ?? null,
        },
        { accessToken },
      );

      dispatch({ type: "createAssessment", payload: newAssessment });
      router.push(`/app/dashboard/assessments/${newAssessment.id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create assessment";
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Create assessment</h1>
        <p className="text-sm text-zinc-500">
          Define instructions, pick a seed repo, and customize the candidate email template.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assessment details</CardTitle>
          <CardDescription>Seeds pin to main at start time. Keep instructions Markdown-friendly.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={formState.title}
                onChange={(event) => setFormState((prev) => ({ ...prev, title: event.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="seed">Seed repository</Label>
                <Button
                  type="button"
                  variant="ghost"
                  className="h-auto px-2 py-1 text-xs text-blue-600 hover:text-blue-700"
                  onClick={() => setShowSeedForm((prev) => !prev)}
                >
                  {showSeedForm ? "Hide" : "Add repository"}
                </Button>
              </div>
              <select
                id="seed"
                value={formState.seedId}
                onChange={(event) => setFormState((prev) => ({ ...prev, seedId: event.target.value }))}
                className="h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-200 disabled:cursor-not-allowed disabled:bg-zinc-50"
                disabled={!hasSeeds}
                required={hasSeeds}
              >
                {hasSeeds ? (
                  state.seeds.map((seed) => (
                    <option key={seed.id} value={seed.id}>
                      {seed.seedRepo}
                    </option>
                  ))
                ) : (
                  <option value="">No repositories yet</option>
                )}
              </select>
              {!hasSeeds ? (
                <p className="text-xs text-zinc-500">
                  Add a GitHub repository to use as the starter template for this assessment.
                </p>
              ) : null}
            </div>
          </div>
          {showSeedForm ? (
            <div className="space-y-4 rounded-lg border border-dashed border-zinc-300 p-4">
              {!isGitHubConnected ? (
                <div className="space-y-3 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700">
                  <p>Connect the GitHub App to mirror repositories into this project.</p>
                  <div className="rounded border border-blue-300 bg-blue-100 p-2 text-xs">
                    <p className="font-medium mb-1">Important instructions:</p>
                    <ul className="list-disc list-inside space-y-0.5">
                      <li>Select your <strong>organization</strong> (not your personal account) when installing</li>
                      <li>Choose &quot;All repositories&quot; when prompted for access</li>
                      <li>Complete the installation by clicking &quot;Install&quot; or &quot;Update&quot;</li>
                      <li>After installing, return to this tab - it will automatically detect the connection</li>
                    </ul>
                    <div className="mt-2 pt-2 border-t border-blue-300 space-y-2">
                      <p className="text-[10px] font-medium text-red-700">
                        <strong>⚠️ CRITICAL - Must Enable OAuth:</strong>
                      </p>
                      <div className="text-[10px] bg-red-50 p-2 rounded border border-red-300">
                        <p className="font-medium mb-1 text-red-800">⚠️ CRITICAL: Configure GitHub App Settings:</p>
                        <ol className="list-decimal list-inside space-y-1 text-[9px] ml-1 text-red-700 mb-2">
                          <li className="font-semibold">Go to GitHub App Settings:</li>
                          <li className="ml-4 mb-1">GitHub → Your Org → Settings → Developer settings → GitHub Apps → <code className="bg-red-100 px-1 rounded">irvin-afterquery-takehome</code></li>
                          <li className="font-semibold mt-1">Enable OAuth:</li>
                          <li className="ml-4 mb-1">Scroll to &quot;Identifying and authorizing users&quot;</li>
                          <li className="ml-4 mb-1"><strong>CHECK ✅</strong> &quot;Request user authorization (OAuth) during installation&quot;</li>
                          <li className="font-semibold mt-1 text-orange-700">⚠️ MOST IMPORTANT - Callback URL Order:</li>
                          <li className="ml-4 mb-1 text-orange-800">GitHub ALWAYS redirects to the <strong>FIRST</strong> Callback URL in the list!</li>
                          <li className="ml-4 mb-1">Find &quot;User authorization callback URL&quot; section</li>
                          <li className="ml-4 mb-1"><strong>DELETE ALL other callback URLs</strong> if any exist</li>
                          <li className="ml-4 mb-1">Add/keep ONLY: <code className="bg-red-100 px-1 rounded font-mono">{typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000'}/app/github/install/callback</code></li>
                          <li className="ml-4 mb-1">Make sure this is the <strong>FIRST</strong> (only) URL in the list</li>
                          <li className="font-semibold mt-1">Also Set Setup URL (optional but recommended):</li>
                          <li className="ml-4 mb-1"><strong>Setup URL:</strong> <code className="bg-red-100 px-1 rounded font-mono">{typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000'}/app/github/install/callback</code></li>
                          <li className="ml-4 mb-1 font-semibold">Click &quot;Update&quot; to save ALL changes</li>
                        </ol>
                        <div className="text-[9px] text-orange-800 bg-orange-50 p-2 rounded border border-orange-200 mt-2">
                          <strong>⚠️ Common Issue:</strong> If you have multiple callback URLs, GitHub uses the FIRST one only. Delete any other callback URLs and ensure your callback URL is the only one (or first in the list).
                        </div>
                        <p className="text-[9px] text-red-600 border-t border-red-200 pt-1 mt-2">
                          <strong>Installation Flow:</strong> After enabling OAuth, you&apos;ll see TWO screens on GitHub:
                          <br />1. &quot;Install&quot; button → Install the app
                          <br />2. &quot;Authorize&quot; button → Authorize the app (THIS triggers the redirect)
                          <br />You MUST complete BOTH steps!
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleConnectGitHub}
                      disabled={connectingGitHub}
                    >
                      {connectingGitHub ? "Redirecting..." : "Connect GitHub App"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => refreshAdminData()}
                      className="text-xs"
                    >
                      Refresh Connection Status
                    </Button>
                    {connectError ? <p className="text-xs text-red-600">{connectError}</p> : null}
                  </div>
                  <p className="text-xs text-blue-600">
                    💡 This page will automatically check for your GitHub connection when you return from installing the app.
                  </p>
                </div>
              ) : (
                <div className="space-y-3 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-green-600">✅</span>
                      <p>GitHub App is connected</p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleConnectGitHub}
                      disabled={connectingGitHub}
                      className="h-8 text-xs"
                    >
                      {connectingGitHub ? "Redirecting..." : "Reconnect"}
                    </Button>
                  </div>
                  {githubInstallation?.accountLogin && (
                    <p className="text-xs text-green-600">
                      Connected to: <strong>{githubInstallation.accountLogin}</strong>
                    </p>
                  )}
                  <p className="text-xs text-green-600">
                    If you uninstalled the app, click &quot;Reconnect&quot; to install it again.
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="repoInput">Template repository link</Label>
                <Input
                  id="repoInput"
                  placeholder="https://github.com/owner/repo"
                  value={seedFormState.repoInput}
                  onChange={(event) =>
                    setSeedFormState((prev) => ({ ...prev, repoInput: event.target.value }))
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      handleCreateSeed();
                    }
                  }}
                />
                <p className="text-xs text-zinc-500">
                  Provide a public or template repository. We recommend adding the GitHub App before
                  inviting candidates.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="defaultBranch">Default branch</Label>
                <Input
                  id="defaultBranch"
                  value={seedFormState.defaultBranch}
                  onChange={(event) =>
                    setSeedFormState((prev) => ({ ...prev, defaultBranch: event.target.value }))
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      handleCreateSeed();
                    }
                  }}
                />
                <p className="text-xs text-zinc-500">
                  We’ll rename the source default branch to match what you enter here (defaults to main).
                </p>
              </div>
              {seedError ? <p className="text-xs text-red-600">{seedError}</p> : null}
              <div className="flex items-center justify-end gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setSeedFormState({ repoInput: "", defaultBranch: "main" });
                    setSeedError(null);
                    setShowSeedForm(false);
                  }}
                >
                  Cancel
                </Button>
                <Button type="button" onClick={handleCreateSeed} disabled={creatingSeed || !isGitHubConnected}>
                  {creatingSeed ? "Saving..." : "Save repository"}
                </Button>
              </div>
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="description">Summary</Label>
            <Textarea
              id="description"
              value={formState.description}
              onChange={(event) => setFormState((prev) => ({ ...prev, description: event.target.value }))}
              placeholder="High-level overview of the take-home"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="instructions">Detailed instructions</Label>
            <Textarea
              id="instructions"
              value={formState.instructions}
              onChange={(event) => setFormState((prev) => ({ ...prev, instructions: event.target.value }))}
              placeholder="Markdown supported guidance for candidates"
              className="min-h-[160px]"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="start">Time to start (hours)</Label>
              <Input
                id="start"
                type="number"
                min={1}
                value={formState.timeToStartHours}
                onChange={(event) => setFormState((prev) => ({ ...prev, timeToStartHours: Number(event.target.value) }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="complete">Time to complete (hours)</Label>
              <Input
                id="complete"
                type="number"
                min={1}
                value={formState.timeToCompleteHours}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, timeToCompleteHours: Number(event.target.value) }))
                }
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Candidate email</CardTitle>
          <CardDescription>
            Tokens are merged when sending. Variables:
            <span className="ml-2 space-x-2 text-xs">
              <code>{"{candidate_name}"}</code>
              <code>{"{assessment_title}"}</code>
              <code>{"{start_deadline}"}</code>
              <code>{"{complete_deadline}"}</code>
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="subject">Subject</Label>
            <Input
              id="subject"
              value={formState.candidateEmailSubject}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, candidateEmailSubject: event.target.value }))
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="body">Body</Label>
            <Textarea
              id="body"
              value={formState.candidateEmailBody}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, candidateEmailBody: event.target.value }))
              }
              className="min-h-[160px]"
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <Button variant="outline" type="button" onClick={() => router.back()}>
          Cancel
        </Button>
        {formError ? <p className="flex-1 text-sm text-red-600">{formError}</p> : <span className="flex-1" />}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : "Save and continue"}
        </Button>
      </div>
    </form>
  );
}
