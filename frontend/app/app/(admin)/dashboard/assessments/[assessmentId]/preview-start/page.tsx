"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAdminData } from "@/providers/admin-data-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { buildCandidateStartLink, candidateBaseFromEnv } from "@/lib/invite-links";
import { Markdown } from "@/components/ui/markdown";

export default function PreviewStartPage() {
  const params = useParams<{ assessmentId: string }>();
  const { state } = useAdminData();

  const assessment = state.assessments.find((item) => item.id === params.assessmentId);
  const seed = state.seeds.find((item) => item.id === assessment?.seedId);
  const [runtimeOrigin, setRuntimeOrigin] = useState<string | null>(candidateBaseFromEnv);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");

  useEffect(() => {
    if (!candidateBaseFromEnv && typeof window !== "undefined") {
      setRuntimeOrigin(window.location.origin);
    }
  }, []);

  const assessmentId = assessment?.id ?? null;

  const latestInvitation = useMemo(() => {
    if (!assessmentId) {
      return null;
    }

    return (
      state.invitations
        .filter((invitation) => invitation.assessmentId === assessmentId && invitation.startLinkToken)
        .sort((a, b) => new Date(b.sentAt).getTime() - new Date(a.sentAt).getTime())[0] ?? null
    );
  }, [assessmentId, state.invitations]);

  const inviteLink = useMemo(
    () => buildCandidateStartLink(latestInvitation?.startLinkToken, runtimeOrigin),
    [latestInvitation?.startLinkToken, runtimeOrigin],
  );

  const handleCopy = useCallback(async () => {
    if (!inviteLink) {
      setCopyState("error");
      return;
    }

    try {
      if (!navigator.clipboard) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(inviteLink);
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 2000);
    } catch (error) {
      console.error("Failed to copy invite link", error);
      setCopyState("error");
      setTimeout(() => setCopyState("idle"), 2000);
    }
  }, [inviteLink]);

  if (!assessment || !seed) {
    return <p className="text-sm text-zinc-500">Assessment not found.</p>;
  }

  const seedOwner = seed.seedRepo.split("/")[0] ?? seed.seedRepo;

  const content = (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Candidate start preview</CardTitle>
          <CardDescription>This mirrors what candidates see when opening their secure token link.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <p className="text-sm text-zinc-500">Assessment</p>
            <h2 className="text-xl font-semibold text-zinc-900">{assessment.title}</h2>
          </div>
          <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50/80 p-4 text-sm text-blue-700">
            <p className="font-medium">Git commands shown to candidates</p>
            <code className="mt-2 block font-mono text-xs text-blue-800">
              export GITHUB_TOKEN=&lt;token minted after clicking Start&gt;
            </code>
            <code className="mt-2 block font-mono text-xs text-blue-800">
              {`git clone https://github.com/${seedOwner}/candidate-<invite>.git`}
            </code>
            <p className="mt-2 text-xs text-blue-700">
              Tokens are issued by the GitHub App for {seed.seedRepo} and expire hourly. Candidates can re-click Start to refresh their token at any time.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-400">Deadline</p>
                <p className="font-medium text-zinc-900">Start within {assessment.timeToStartHours}h</p>
              </div>
              <Badge>Complete in {assessment.timeToCompleteHours}h</Badge>
            </div>
            <Markdown className="prose prose-sm prose-zinc mt-4 max-w-none">
              {assessment.instructions}
            </Markdown>
          </div>
          <div className="flex justify-end gap-3">
            <Button variant="outline">Send test email</Button>
            {inviteLink ? (
              <Button onClick={handleCopy}>
                {copyState === "copied" ? "Copied!" : copyState === "error" ? "Copy failed" : "Copy invite link"}
              </Button>
            ) : null}
          </div>
          {!inviteLink && (
            <p className="text-right text-xs text-zinc-500">
              Create an invitation to generate a candidate start link you can share.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );

  return content;
}
