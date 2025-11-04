"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { useQueryClient } from "@tanstack/react-query";
import { useAdminData } from "@/providers/admin-data-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { markInvitationSubmitted, listAssessmentFeatures, toggleFeatureScore, getReviewScoreSummary, type AssessmentFeature, type ReviewScoreSummary } from "@/lib/api";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import { DiffViewer } from "@/components/review/diff-viewer";
import { LLMAnalysisTab } from "@/components/review/llm-analysis-tab";
import { Markdown } from "@/components/ui/markdown";

function VideoPlayer({ url }: { url: string }) {
  const embedUrl = useMemo(() => {
    try {
      if (url.includes("youtube.com/watch") || url.includes("youtu.be/")) {
        const videoId = url.includes("youtube.com/watch")
          ? new URL(url).searchParams.get("v")
          : url.split("youtu.be/")[1]?.split("?")[0];
        if (videoId) {
          return { type: "iframe", url: `https://www.youtube.com/embed/${videoId}` };
        }
      }

      if (url.includes("vimeo.com/")) {
        const videoId = url.split("vimeo.com/")[1]?.split("?")[0];
        if (videoId) {
          return { type: "iframe", url: `https://player.vimeo.com/video/${videoId}` };
        }
      }

      if (url.includes("drive.google.com/file/d/")) {
        const match = url.match(/\/file\/d\/([a-zA-Z0-9_-]+)/);
        if (match?.[1]) {
          return { type: "iframe", url: `https://drive.google.com/file/d/${match[1]}/preview` };
        }
      }

      return { type: "video", url };
    } catch {
      return { type: "video", url };
    }
  }, [url]);

  if (embedUrl.type === "iframe") {
    return (
      <div className="aspect-video w-full overflow-hidden rounded-lg">
        <iframe
          src={embedUrl.url}
          className="h-full w-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          title="Submission video"
        />
      </div>
    );
  }

  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg">
      <video controls className="h-full w-full">
        <source src={url} />
        Your browser does not support the video tag.
      </video>
    </div>
  );
}

export default function ReviewWorkspacePage() {
  const params = useParams<{ invitationId: string }>();
  const { state, dispatch } = useAdminData();
  const { accessToken } = useSupabaseAuth();
  const router = useRouter();
  const queryClient = useQueryClient();

  // All state hooks at the top
  const [draftComment, setDraftComment] = useState("");
  const [markingSubmitted, setMarkingSubmitted] = useState(false);
  const [markError, setMarkError] = useState<string | null>(null);
  const [features, setFeatures] = useState<AssessmentFeature[]>([]);
  const [scoreSummary, setScoreSummary] = useState<ReviewScoreSummary | null>(null);
  const [loadingScoring, setLoadingScoring] = useState(true);
  const [togglingFeature, setTogglingFeature] = useState<string | null>(null);
  // Local checkbox states for instant visual feedback
  const [localCheckedStates, setLocalCheckedStates] = useState<Record<string, boolean>>({});

  // Get invitation and related data
  const invitation = state.invitations.find((item) => item.id === params.invitationId);

  useEffect(() => {
    if (!invitation) {
      router.back();
    }
  }, [invitation, router]);

  // Load features and score summary
  useEffect(() => {
    async function loadScoringData() {
      if (!invitation || !accessToken) {
        return;
      }

      setLoadingScoring(true);
      try {
        const [loadedFeatures, summary] = await Promise.all([
          listAssessmentFeatures(invitation.assessmentId, { accessToken }),
          getReviewScoreSummary(invitation.id, { accessToken }),
        ]);

        setFeatures(loadedFeatures);
        // Ensure summary is valid - if API returns data, it should have the required fields
        if (summary && typeof summary.totalScore === 'number' && typeof summary.maxScore === 'number') {
          setScoreSummary(summary);
          // Sync local checkbox states with server state
          const checkedStates: Record<string, boolean> = {};
          summary.features?.forEach((f) => {
            checkedStates[f.featureId] = f.checked ?? false;
          });
          setLocalCheckedStates(checkedStates);
        } else {
          console.error("Invalid score summary response:", summary);
          console.error("totalScore type:", typeof summary?.totalScore, "value:", summary?.totalScore);
          console.error("maxScore type:", typeof summary?.maxScore, "value:", summary?.maxScore);
          setScoreSummary(null);
        }
      } catch (error) {
        console.error("Failed to load scoring data:", error);
        setScoreSummary(null);
      } finally {
        setLoadingScoring(false);
      }
    }

    loadScoringData();
  }, [invitation?.id, accessToken]);

  async function handleToggleFeature(featureId: string) {
    if (!invitation || !accessToken || !featureId || togglingFeature) {
      return;
    }

    // Get current checked state (prioritize local state if available, otherwise use scoreSummary)
    const currentChecked = localCheckedStates[featureId] ?? 
      scoreSummary?.features.find(f => f.featureId === featureId)?.checked ?? false;
    const newChecked = !currentChecked;

    // Update local checkbox state immediately for instant visual feedback
    setLocalCheckedStates((prev) => ({
      ...prev,
      [featureId]: newChecked,
    }));

    // Optimistic update: toggle the score summary state immediately
    setScoreSummary((prev) => {
      if (!prev) return prev;
      
      const updatedFeatures = prev.features.map((f) =>
        f.featureId === featureId
          ? { ...f, checked: newChecked, score: newChecked ? f.weight : 0 }
          : f
      );
      
      const newTotalScore = updatedFeatures.reduce((sum, f) => sum + f.score, 0);
      const newMaxScore = prev.maxScore;
      const newPercentage = newMaxScore > 0 ? (newTotalScore / newMaxScore) * 100 : 0;
      
      return {
        ...prev,
        totalScore: Math.round(newTotalScore * 100) / 100, // Round to 2 decimal places to match backend
        percentage: Math.round(newPercentage * 100) / 100, // Round to 2 decimal places to match backend
        features: updatedFeatures.map((f) => ({
          ...f,
          score: Math.round(f.score * 100) / 100, // Round to 2 decimal places
        })),
      };
    });

    setTogglingFeature(featureId);
    try {
      // Toggle feature and get updated summary in one call
      const summary = await toggleFeatureScore(invitation.id, featureId, { accessToken });
      // Validate and update with server response
      if (summary && typeof summary.totalScore === 'number' && typeof summary.maxScore === 'number') {
        setScoreSummary(summary);
        // Update local checkbox states to match server response
        const checkedStates: Record<string, boolean> = {};
        summary.features?.forEach((f) => {
          checkedStates[f.featureId] = f.checked ?? false;
        });
        setLocalCheckedStates(checkedStates);
        // Invalidate the assessment scores cache so the list page shows updated scores
        queryClient.invalidateQueries({ queryKey: ["assessment-scores", invitation.assessmentId] });
      } else {
        console.error("Invalid toggle response:", summary);
        // Fallback: reload the summary
        const reloadedSummary = await getReviewScoreSummary(invitation.id, { accessToken });
        if (reloadedSummary && typeof reloadedSummary.totalScore === 'number' && typeof reloadedSummary.maxScore === 'number') {
          setScoreSummary(reloadedSummary);
          const checkedStates: Record<string, boolean> = {};
          reloadedSummary.features?.forEach((f) => {
            checkedStates[f.featureId] = f.checked ?? false;
          });
          setLocalCheckedStates(checkedStates);
        }
      }
    } catch (error) {
      console.error("Failed to toggle feature score:", error);
      // Revert optimistic update on error by reloading the summary
      if (invitation) {
        try {
          const summary = await getReviewScoreSummary(invitation.id, { accessToken });
          if (summary && typeof summary.totalScore === 'number' && typeof summary.maxScore === 'number') {
            setScoreSummary(summary);
            // Revert local checkbox states to match server
            const checkedStates: Record<string, boolean> = {};
            summary.features?.forEach((f) => {
              checkedStates[f.featureId] = f.checked ?? false;
            });
            setLocalCheckedStates(checkedStates);
          }
        } catch (reloadError) {
          console.error("Failed to reload score summary:", reloadError);
        }
      }
      alert("Failed to update feature score. Please try again.");
    } finally {
      setTogglingFeature(null);
    }
  }

  // Early return check
  if (!invitation) {
    return null;
  }

  // Computed values after early return
  const activeInvitation = invitation;
  const assessment = state.assessments.find((item) => item.id === activeInvitation.assessmentId);
  const repo = state.candidateRepos.find((item) => item.invitationId === invitation.id) ?? null;
  const comments = state.reviewComments.filter((comment) => comment.invitationId === invitation.id);
  const lastActivity = invitation.submittedAt ?? repo?.lastCommitAt ?? invitation.sentAt;
  const resolvedLastActivity = lastActivity ?? activeInvitation.sentAt;

  async function handleMarkSubmitted() {
    if (activeInvitation.status === "submitted") {
      return;
    }

    if (!accessToken) {
      setMarkError("Sign in to update the submission status.");
      return;
    }

    setMarkError(null);
    setMarkingSubmitted(true);
    try {
      const updated = await markInvitationSubmitted(activeInvitation.id, { accessToken });
      dispatch({
        type: "updateInvitationStatus",
        payload: {
          invitationId: updated.id,
          status: updated.status,
          submittedAt: updated.submittedAt ?? undefined,
        },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update submission status.";
      setMarkError(message);
    } finally {
      setMarkingSubmitted(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm text-zinc-500">{assessment?.title}</p>
          <h1 className="text-2xl font-semibold text-zinc-900">{activeInvitation.candidateName}</h1>
          <p className="text-xs uppercase tracking-wide text-zinc-400">
            Status <Badge className="ml-2 capitalize">{activeInvitation.status}</Badge>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {activeInvitation.status !== "submitted" && (
            <Button variant="outline" onClick={handleMarkSubmitted} disabled={markingSubmitted}>
              {markingSubmitted ? "Marking..." : "Mark submitted"}
            </Button>
          )}
          {repo?.repoHtmlUrl && (
            <Button asChild>
              <Link href={repo.repoHtmlUrl} target="_blank">
                View repo
              </Link>
            </Button>
          )}
        </div>
      </div>

      {markError && <p className="text-sm text-red-600">{markError}</p>}

      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="scoring">Scoring</TabsTrigger>
          <TabsTrigger value="diff">Diff guidance</TabsTrigger>
          <TabsTrigger value="feedback">Feedback</TabsTrigger>
          <TabsTrigger value="llm-analysis">LLM Analysis</TabsTrigger>
        </TabsList>
        <TabsContent value="summary">
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <div className="space-y-6">
              {invitation.videoUrl && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Submission Video</CardTitle>
                    <CardDescription>Candidate's video walkthrough of their solution.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <VideoPlayer url={invitation.videoUrl} />
                  </CardContent>
                </Card>
              )}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Repository</CardTitle>
                  <CardDescription>Token broker locks default branch once submitted.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 text-sm text-zinc-600">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-400">GitHub repo</p>
                    <p className="font-medium text-zinc-900">{repo?.repoFullName ?? "Not provisioned"}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-400">Seed SHA</p>
                    <p className="font-mono text-xs">{repo?.seedShaPinned}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-400">Last activity</p>
                    <p>{formatDistanceToNow(new Date(resolvedLastActivity), { addSuffix: true })}</p>
                  </div>
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Timeline</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-xs text-zinc-500">
                <p>Invite sent {formatDistanceToNow(new Date(activeInvitation.sentAt), { addSuffix: true })}</p>
                {activeInvitation.startedAt && (
                  <p>Started {formatDistanceToNow(new Date(activeInvitation.startedAt), { addSuffix: true })}</p>
                )}
                {activeInvitation.submittedAt && (
                  <p>Submitted {formatDistanceToNow(new Date(activeInvitation.submittedAt), { addSuffix: true })}</p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
        <TabsContent value="scoring">
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Feature Checklist</CardTitle>
                  <CardDescription>Check off features that are implemented. Scores are calculated automatically.</CardDescription>
                </CardHeader>
                <CardContent>
                  {loadingScoring ? (
                    <p className="py-4 text-sm text-zinc-500">Loading scoring data...</p>
                  ) : features.length === 0 ? (
                    <p className="py-4 text-sm text-zinc-500">
                      No scoring features defined for this assessment. Add features in the assessment settings.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {features.map((feature) => {
                        const featureScore = scoreSummary?.features.find(f => f.featureId === feature.id);
                        // Use local state if available (for instant feedback), otherwise fall back to server state
                        const isChecked = localCheckedStates[feature.id] ?? featureScore?.checked ?? false;
                        const isToggling = togglingFeature === feature.id;
                        return (
                          <div
                            key={feature.id}
                            className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white p-4"
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => handleToggleFeature(feature.id)}
                              disabled={!accessToken || loadingScoring}
                              className={`mt-1 h-4 w-4 cursor-pointer rounded border-zinc-300 text-blue-600 focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:opacity-50 ${isToggling ? 'opacity-70' : ''}`}
                            />
                            <div className="flex-1">
                              <label className="cursor-pointer font-medium text-zinc-900">{feature.name}</label>
                              {feature.description && (
                                <p className="mt-1 text-sm text-zinc-600">{feature.description}</p>
                              )}
                            </div>
                            <Badge variant="outline">Weight: {feature.weight}</Badge>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Score Summary</CardTitle>
                <CardDescription>Calculated score based on checked features.</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingScoring ? (
                  <p className="py-4 text-sm text-zinc-500">Loading...</p>
                ) : scoreSummary && typeof scoreSummary.totalScore === 'number' && typeof scoreSummary.maxScore === 'number' ? (
                  <div className="space-y-4">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-zinc-400">Score</p>
                      <p className="mt-1 text-3xl font-bold text-zinc-900">
                        {scoreSummary.totalScore.toFixed(2)} / {scoreSummary.maxScore.toFixed(2)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-zinc-400">Percentage</p>
                      <p className="mt-1 text-2xl font-semibold text-zinc-900">
                        {typeof scoreSummary.percentage === 'number' ? scoreSummary.percentage.toFixed(1) : '0.0'}%
                      </p>
                    </div>
                    {scoreSummary.features && scoreSummary.features.length > 0 && (
                      <div className="mt-6 border-t pt-4">
                        <p className="mb-2 text-xs uppercase tracking-wide text-zinc-400">Breakdown</p>
                        <div className="space-y-2">
                          {scoreSummary.features.map((f) => (
                            <div key={f.featureId} className="flex justify-between text-sm">
                              <span className={f.checked ? "text-zinc-900" : "text-zinc-400"}>
                                {f.checked ? "✓" : "○"} {f.name}
                              </span>
                              <span className={f.checked ? "font-medium text-zinc-900" : "text-zinc-400"}>
                                {typeof f.score === 'number' ? f.score.toFixed(2) : '0.00'} / {typeof f.weight === 'number' ? f.weight.toFixed(2) : '0.00'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="py-4 text-sm text-zinc-500">No scoring data available.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
        <TabsContent value="diff">
          {repo ? (
            <DiffViewer
              repoId={repo.id}
              seedSha={repo.seedShaPinned}
              headBranch="main"
              accessToken={accessToken || undefined}
              onError={(error) => {
                console.error("Diff viewer error:", error);
              }}
            />
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-sm text-zinc-500">
                No repository yet. Candidate must start the assessment to generate a private repo.
              </CardContent>
            </Card>
          )}
        </TabsContent>
        <TabsContent value="feedback">
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Reviewer comments</CardTitle>
                <CardDescription>Share async feedback and follow-up talking points.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {comments.map((comment) => (
                  <div key={comment.id} className="rounded-lg border border-zinc-200 bg-white p-4">
                    <p className="text-sm font-semibold text-zinc-800">{comment.author}</p>
                    <p className="mt-1 text-sm text-zinc-600">{comment.body}</p>
                    <p className="mt-2 text-xs text-zinc-400">
                      {formatDistanceToNow(new Date(comment.createdAt), { addSuffix: true })}
                    </p>
                  </div>
                ))}
                {comments.length === 0 && <p className="text-sm text-zinc-500">No feedback captured yet.</p>}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Record new note</CardTitle>
                <CardDescription>Future backend will persist notes via FastAPI webhook.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Textarea
                  value={draftComment}
                  onChange={(event) => setDraftComment(event.target.value)}
                  placeholder="Summarize strengths, gaps, and follow-up recommendations"
                />
                <Button type="button" disabled={!draftComment.trim()}>
                  Save draft (coming soon)
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
        <TabsContent value="llm-analysis">
          {invitation && accessToken && (
            <LLMAnalysisTab invitationId={invitation.id} accessToken={accessToken} rubricText={assessment?.rubricText ?? null} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
