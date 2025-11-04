"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Markdown } from "@/components/ui/markdown";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  startCandidateAssessment,
  submitCandidateAssessment,
} from "@/lib/api";
import type {
  CandidateRepo,
  CandidateStartAssessment,
  CandidateStartInvitation,
  CandidateStartSeed,
} from "@/lib/types";

type CandidateStartViewProps = {
  invitation: CandidateStartInvitation;
  assessment: CandidateStartAssessment;
  seed: CandidateStartSeed;
  repo?: CandidateRepo;
  startToken: string;
};

export function CandidateStartView({ invitation, assessment, seed, repo, startToken }: CandidateStartViewProps) {
  const router = useRouter();
  const [currentInvitation, setCurrentInvitation] = useState(invitation);
  const [videoUrl, setVideoUrl] = useState("");
  const [currentRepo, setCurrentRepo] = useState<CandidateRepo | undefined>(repo);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<"start" | "finish" | null>(null);
  const [isRefreshing, startRefresh] = useTransition();
  const [accessTokenInfo, setAccessTokenInfo] = useState<
    { token: string; expiresAt: string } | null
  >(null);

  const formatDate = (value: string | null) => {
    if (!value) {
      return null;
    }
    // Use consistent UTC formatting to avoid hydration mismatches
    // Server and client will both render the same string
    const date = new Date(value);
    return date.toLocaleString(undefined, {
      timeZone: 'UTC',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }) + ' UTC';
  };

  const statusMeta = useMemo(() => {
    const base = {
      label: "",
      description: "",
      container: "border-zinc-200 bg-white",
      badge: "bg-zinc-900 text-white",
    };

    switch (currentInvitation.status) {
      case "submitted":
        return {
          ...base,
          label: "Submitted",
          description: "We&apos;ll review your project and follow up soon.",
          container: "border-emerald-200 bg-emerald-50",
          badge: "border-transparent bg-emerald-600 text-white",
        };
      case "started":
        return {
          ...base,
          label: "In progress",
          description: "Your private repository is ready and pushes are accepted until the deadline.",
          container: "border-blue-200 bg-blue-50",
          badge: "border-transparent bg-blue-600 text-white",
        };
      case "accepted":
        return {
          ...base,
          label: "Accepted",
          description: "You&apos;re cleared to begin whenever you&apos;re ready.",
          container: "border-sky-200 bg-sky-50",
          badge: "border-transparent bg-sky-600 text-white",
        };
      case "expired":
        return {
          ...base,
          label: "Expired",
          description: "The start window has closed. Reach out to your coordinator if this is unexpected.",
          container: "border-zinc-200 bg-zinc-100",
          badge: "border-transparent bg-zinc-500 text-white",
        };
      case "revoked":
        return {
          ...base,
          label: "Revoked",
          description: "Access to this assessment has been revoked.",
          container: "border-red-200 bg-red-50",
          badge: "border-transparent bg-red-600 text-white",
        };
      default:
        return {
          ...base,
          label: "Not started",
          description: "Start the assessment to mint your private repository and token.",
          container: "border-amber-200 bg-amber-50",
          badge: "border-transparent bg-amber-600 text-white",
        };
    }
  }, [currentInvitation.status]);

  const startBy = formatDate(currentInvitation.startDeadline);
  const startedAt = formatDate(currentInvitation.startedAt ?? null);
  const completeBy = formatDate(currentInvitation.completeDeadline);

  const completionWindowLabel =
    completeBy ??
    (assessment.timeToCompleteHours
      ? `${assessment.timeToCompleteHours}h once started`
      : "Defined by your coordinator");

  const refreshPage = () => {
    startRefresh(() => {
      router.refresh();
    });
  };

  const handleStart = async () => {
    setActiveAction("start");
    setActionError(null);
    setActionMessage(null);
    try {
      const result = await startCandidateAssessment(startToken);
      setCurrentInvitation((prev) => ({
        ...prev,
        status: result.status,
        startedAt: result.startedAt,
        completeDeadline: result.completeDeadline,
      }));
      setCurrentRepo(result.candidateRepo);
      setAccessTokenInfo({
        token: result.accessToken,
        expiresAt: result.accessTokenExpiresAt,
      });
      setActionMessage(
        `Assessment started! Your private repo is ${result.candidateRepo.repoFullName}.`,
      );
      refreshPage();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to start the assessment.");
    } finally {
      setActiveAction(null);
    }
  };

  const handleFinish = async () => {
    setActiveAction("finish");
    setActionError(null);
    setActionMessage(null);
    try {
      const result = await submitCandidateAssessment(startToken, {
        videoUrl: videoUrl.trim() || undefined,
      });
      setCurrentInvitation((prev) => ({
        ...prev,
        status: result.status,
        submittedAt: result.submittedAt,
      }));
      setAccessTokenInfo(null);
      setActionMessage("Thanks! We've marked your assessment as submitted.");
      refreshPage();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to submit the assessment.");
    } finally {
      setActiveAction(null);
    }
  };

  const hasStarted =
    currentInvitation.status === "started" || currentInvitation.status === "submitted";
  const canFinish = currentInvitation.status === "started";
  const isSubmitted = currentInvitation.status === "submitted";

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-zinc-50 px-6 py-10">
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="space-y-2 text-center">
          <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-blue-700">
            Afterquery Assessment
          </span>
          <h1 className="text-3xl font-semibold text-zinc-900">{assessment.title}</h1>
          <p className="text-sm text-zinc-600">Invited for {currentInvitation.candidateName}</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Start your private repo</CardTitle>
            <CardDescription>
              Repos are generated from the
              {" "}
              <a
                href={seed.seedRepoUrl}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-blue-600 hover:underline"
              >
                {seed.seedRepo}
              </a>
              {seed.latestMainSha ? ` at SHA ${seed.latestMainSha}.` : "."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5 text-sm text-zinc-600">
            <div
              className={`rounded-lg border p-4 shadow-sm transition-all sm:p-5 ${statusMeta.container}`}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Status</p>
                  <p className="mt-1 text-base font-semibold text-zinc-900">{statusMeta.label}</p>
                  <p className="mt-2 text-xs text-zinc-600 sm:max-w-xs">{statusMeta.description}</p>
                </div>
                <Badge className={`self-start ${statusMeta.badge}`}>{statusMeta.label}</Badge>
              </div>
              <dl className="mt-4 grid gap-4 text-xs text-zinc-600 sm:grid-cols-3">
                <div>
                  <dt className="font-medium text-zinc-700">Start by</dt>
                  <dd className="mt-1 text-sm text-zinc-900" suppressHydrationWarning>
                    {startBy ?? "No start deadline"}
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-zinc-700">Started</dt>
                  <dd className="mt-1 text-sm text-zinc-900" suppressHydrationWarning>
                    {startedAt ?? "Not yet started"}
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-zinc-700">Complete by</dt>
                  <dd className="mt-1 text-sm text-zinc-900" suppressHydrationWarning>
                    {completionWindowLabel}
                  </dd>
                </div>
              </dl>
            </div>
            <div>
              <p className="font-semibold text-zinc-800">1. Authenticate Git</p>
              {accessTokenInfo ? (
                <>
                  <code className="mt-2 block rounded-md bg-zinc-900 p-4 font-mono text-xs text-zinc-100">
                    export GITHUB_TOKEN={accessTokenInfo.token}
                  </code>
                  <p className="mt-2 text-xs text-zinc-500">
                    Token expires {formatDate(accessTokenInfo.expiresAt) ?? 'unknown'}. Run commands in the same shell so Git uses the token as your HTTPS password.
                  </p>
                </>
              ) : hasStarted ? (
                <p className="mt-2 text-xs text-zinc-500">
                  You generated a GitHub token when you started this assessment. Use that saved token (for example by setting
                  {" "}
                  <code className="rounded bg-zinc-200 px-1 py-0.5 text-[11px]">export GITHUB_TOKEN=your-token</code>) to authenticate. Tokens can’t be re-displayed for security—reach out to your coordinator if you need a new one.
                </p>
              ) : (
                <p className="mt-2 text-xs text-zinc-500">
                  Select <strong>Start assessment</strong> to mint your private repository and GitHub App token.
                </p>
              )}
            </div>
            <div>
              <p className="font-semibold text-zinc-800">2. Clone the repo</p>
              {currentRepo ? (
                <code className="mt-2 block rounded-md bg-zinc-900 p-4 font-mono text-xs text-zinc-100">
                  {accessTokenInfo
                    ? `git clone https://x-access-token:${accessTokenInfo.token}@github.com/${currentRepo.repoFullName}.git`
                    : `git clone https://github.com/${currentRepo.repoFullName}.git`}
                </code>
              ) : (
                <div className="mt-2 rounded-md border border-dashed border-zinc-300 bg-white p-4 text-xs text-zinc-500">
                  Start the assessment to generate your private repository and cloning instructions.
                </div>
              )}
              <p className="mt-2 text-xs text-zinc-500">
                Use your GitHub token as the HTTPS password when prompted. You can also store it in a credential helper for convenience.
              </p>
            </div>
            <div>
              <p className="font-semibold text-zinc-800">3. Submit</p>
              <p className="mt-1 text-xs text-zinc-500">
                Push your final commits to <span className="font-mono">main</span> before the completion window expires. We’ll email confirmation immediately.
              </p>
            </div>
            {currentRepo && (
              <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50 p-4 text-xs text-blue-700">
                Private repo <strong>{currentRepo.repoFullName}</strong> is active for you. Keep your token safe—contact your
                coordinator if you need help accessing the repository.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Instructions</CardTitle>
            <CardDescription>
              Follow these steps carefully. We’ll discuss trade-offs during your review conversation.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Markdown className="prose prose-zinc max-w-none">
              {assessment.instructions ?? ""}
            </Markdown>
          </CardContent>
        </Card>

        {canFinish && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Submit Assessment</CardTitle>
              <CardDescription>
                Optionally include a video walkthrough link.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="video-url">Video URL (optional)</Label>
                <Input
                  id="video-url"
                  type="url"
                  placeholder="YouTube, Vimeo, Google Drive, or direct video URL"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        )}

        <div className="space-y-2">
          {actionError && <p className="text-sm text-red-600">{actionError}</p>}
          {actionMessage && <p className="text-sm text-green-700">{actionMessage}</p>}
            {isSubmitted && currentInvitation.submittedAt && (
              <p className="text-sm text-green-700">
                Assessment submitted on {formatDate(currentInvitation.submittedAt)}. We&apos;ll be in touch soon.
              </p>
            )}
          <div className="flex flex-wrap items-center justify-end gap-3">
            {!hasStarted && (
              <Button
                size="lg"
                onClick={handleStart}
                disabled={activeAction !== null || isRefreshing}
              >
                {activeAction === "start" ? "Starting..." : "Start assessment"}
              </Button>
            )}
            {canFinish && (
              <Button
                size="lg"
                variant="outline"
                onClick={handleFinish}
                disabled={activeAction !== null || isRefreshing}
              >
                {activeAction === "finish" ? "Submitting..." : "Submit assessment"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
