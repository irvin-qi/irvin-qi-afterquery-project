"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { useAdminData } from "@/providers/admin-data-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/ui/markdown";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import Link from "next/link";
import { format } from "date-fns";
import { useEffect, useRef, useState } from "react";
import { buildCandidateStartLink, candidateBaseFromEnv } from "@/lib/invite-links";
import {
  createAssessmentFeature,
  deleteAssessmentFeature,
  getAssessmentInvitationScores,
  listAssessmentFeatures,
  updateAssessment,
  updateAssessmentFeature,
  getManualRanking,
  type CreateAssessmentFeaturePayload,
  type AssessmentFeature,
  type InvitationScoreSummary,
  type ManualRankingRead,
} from "@/lib/api";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQuery } from "@tanstack/react-query";

type SortMode = "auto" | "manual";

export default function AssessmentDetailPage() {
  const params = useParams<{ assessmentId: string }>();
  const pathname = usePathname();
  const { state, dispatch } = useAdminData();
  const { accessToken } = useSupabaseAuth();
  const router = useRouter();

  const assessment = state.assessments.find((item) => item.id === params.assessmentId);
  const [runtimeOrigin, setRuntimeOrigin] = useState<string | null>(candidateBaseFromEnv);
  const [copyStates, setCopyStates] = useState<Record<string, "copied" | "error">>({});
  
  // Sort mode state
  const [sortMode, setSortMode] = useState<SortMode>("auto");

  // Rubric editor state
  const [rubricText, setRubricText] = useState<string>(assessment?.rubricText ?? "");
  const [savingRubric, setSavingRubric] = useState(false);
  const [rubricError, setRubricError] = useState<string | null>(null);

  // Features manager state
  const [features, setFeatures] = useState<AssessmentFeature[]>([]);
  const [loadingFeatures, setLoadingFeatures] = useState(true);
  const [editingFeature, setEditingFeature] = useState<AssessmentFeature | null>(null);
  const [featureForm, setFeatureForm] = useState<{
    name: string;
    description: string;
    weight: string;
  }>({ name: "", description: "", weight: "1.0" });
  const [savingFeature, setSavingFeature] = useState(false);
  const [featureError, setFeatureError] = useState<string | null>(null);
  const [showFeatureForm, setShowFeatureForm] = useState(false);

  // Invitation scores state
  const [invitationScores, setInvitationScores] = useState<Record<string, InvitationScoreSummary>>({});
  const [loadingScores, setLoadingScores] = useState(false);
  const loadedAssessmentIdRef = useRef<string | null>(null);
  const isLoadingScoresRef = useRef(false);

  useEffect(() => {
    if (!assessment) {
      router.back();
    }
  }, [assessment, router]);

  useEffect(() => {
    if (!candidateBaseFromEnv && typeof window !== "undefined") {
      setRuntimeOrigin(window.location.origin);
    }
  }, []);

  useEffect(() => {
    if (assessment?.rubricText !== undefined) {
      setRubricText(assessment.rubricText ?? "");
    }
  }, [assessment?.rubricText]);

  // Sync sort mode from assessment when it loads or changes
  useEffect(() => {
    if (assessment) {
      // Handle both camelCase (from API) and snake_case (from admin overview)
      const mode = (assessment as any).sortMode || (assessment as any).sort_mode || "auto";
      setSortMode(mode as SortMode);
    }
  }, [assessment]);

  // Fetch manual ranking
  const {
    data: manualRanking,
    isLoading: loadingRanking,
  } = useQuery<ManualRankingRead | null>({
    queryKey: ["manual-ranking", assessment?.id],
    queryFn: async () => {
      if (!assessment || !accessToken) {
        return null;
      }
      return getManualRanking(assessment.id, { accessToken });
    },
    enabled: !!assessment && !!accessToken,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });


  // Load features
  useEffect(() => {
    async function loadFeatures() {
      if (!assessment || !accessToken) return;
      setLoadingFeatures(true);
      try {
        const loadedFeatures = await listAssessmentFeatures(assessment.id, { accessToken });
        setFeatures(loadedFeatures);
      } catch (error) {
        console.error("Failed to load features:", error);
      } finally {
        setLoadingFeatures(false);
      }
    }
    loadFeatures();
  }, [assessment?.id, accessToken]);

  // Load invitation scores - only reload when assessment ID changes or explicitly requested
  useEffect(() => {
    console.log("[ASSESSMENT] useEffect triggered", {
      assessmentId: assessment?.id,
      accessToken: !!accessToken,
      pathname,
      loadedAssessmentId: loadedAssessmentIdRef.current,
      isLoading: isLoadingScoresRef.current,
      scoresCount: Object.keys(invitationScores).length,
    });

    async function loadScores(forceReload = false) {
      if (!assessment || !accessToken) {
        console.log("[ASSESSMENT] Early return: missing assessment or accessToken");
        return;
      }
      if (isLoadingScoresRef.current) {
        console.log("[ASSESSMENT] Early return: already loading");
        return;
      }
      
      // Only reload if assessment ID changed or forced
      const assessmentChanged = loadedAssessmentIdRef.current !== assessment.id;
      console.log("[ASSESSMENT] Checking if reload needed", {
        forceReload,
        assessmentChanged,
        currentAssessmentId: assessment.id,
        loadedAssessmentId: loadedAssessmentIdRef.current,
        scoresCount: Object.keys(invitationScores).length,
      });

      if (!forceReload && !assessmentChanged) {
        // Already loaded and assessment hasn't changed, skip reload
        console.log("[ASSESSMENT] Skipping reload - assessment unchanged and not forced");
        return;
      }

      console.log("[ASSESSMENT] Loading invitation scores for assessment:", assessment.id, { forceReload });
      loadedAssessmentIdRef.current = assessment.id;
      isLoadingScoresRef.current = true;
      setLoadingScores(true);
      try {
        const scores = await getAssessmentInvitationScores(assessment.id, { accessToken });
        console.log("[ASSESSMENT] Loaded scores from API", { scoresCount: scores.length, scores });
        const scoresMap: Record<string, InvitationScoreSummary> = {};
        scores.forEach((score) => {
          scoresMap[score.invitationId] = score;
        });
        console.log("[ASSESSMENT] Setting invitation scores", scoresMap);
        setInvitationScores(scoresMap);
      } catch (error) {
        console.error("[ASSESSMENT] Failed to load invitation scores:", error);
      } finally {
        setLoadingScores(false);
        isLoadingScoresRef.current = false;
        console.log("[ASSESSMENT] Finished loading invitation scores");
      }
    }
    
    loadScores();

    // Reload scores when page becomes visible or window regains focus (user navigates back)
    // Force reload when visibility/focus changes to get latest scores
    const handleVisibilityChange = () => {
      console.log("[ASSESSMENT] Visibility changed", {
        visibilityState: document.visibilityState,
        isLoading: isLoadingScoresRef.current,
      });
      if (document.visibilityState === "visible" && !isLoadingScoresRef.current) {
        console.log("[ASSESSMENT] Triggering reload due to visibility change");
        loadScores(true);
      }
    };
    const handleFocus = () => {
      console.log("[ASSESSMENT] Window focus", { isLoading: isLoadingScoresRef.current });
      if (!isLoadingScoresRef.current) {
        console.log("[ASSESSMENT] Triggering reload due to window focus");
        loadScores(true);
      }
    };
    
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleFocus);

    return () => {
      console.log("[ASSESSMENT] Cleaning up event listeners");
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleFocus);
    };
  }, [assessment?.id, accessToken, pathname]);

  async function handleSaveRubric() {
    if (!assessment || !accessToken) return;
    setSavingRubric(true);
    setRubricError(null);
    try {
      const updated = await updateAssessment(assessment.id, { rubricText: rubricText || null }, { accessToken });
      dispatch({ type: "updateAssessment", payload: updated });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save rubric";
      setRubricError(message);
    } finally {
      setSavingRubric(false);
    }
  }

  function handleStartEditFeature(feature?: AssessmentFeature) {
    if (feature) {
      setEditingFeature(feature);
      setFeatureForm({
        name: feature.name,
        description: feature.description ?? "",
        weight: feature.weight.toString(),
      });
    } else {
      setEditingFeature(null);
      setFeatureForm({ name: "", description: "", weight: "1.0" });
    }
    setShowFeatureForm(true);
    setFeatureError(null);
  }

  function handleCancelFeatureForm() {
    setShowFeatureForm(false);
    setEditingFeature(null);
    setFeatureForm({ name: "", description: "", weight: "1.0" });
    setFeatureError(null);
  }

  async function handleSaveFeature() {
    if (!assessment || !accessToken || !featureForm.name.trim()) return;
    setSavingFeature(true);
    setFeatureError(null);
    try {
      const payload: CreateAssessmentFeaturePayload = {
        name: featureForm.name.trim(),
        description: featureForm.description.trim() || undefined,
        weight: parseFloat(featureForm.weight) || 1.0,
      };

      if (editingFeature) {
        const updated = await updateAssessmentFeature(
          assessment.id,
          editingFeature.id,
          payload,
          { accessToken },
        );
        setFeatures((prev) =>
          prev
            .map((f) => (f.id === updated.id ? updated : f))
            .sort((a, b) => b.weight - a.weight || a.name.localeCompare(b.name)),
        );
      } else {
        const created = await createAssessmentFeature(assessment.id, payload, { accessToken });
        setFeatures((prev) =>
          [...prev, created].sort((a, b) => b.weight - a.weight || a.name.localeCompare(b.name)),
        );
      }
      handleCancelFeatureForm();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save feature";
      setFeatureError(message);
    } finally {
      setSavingFeature(false);
    }
  }

  async function handleDeleteFeature(featureId: string) {
    if (!assessment || !accessToken || !confirm("Are you sure you want to delete this feature?")) return;
    try {
      await deleteAssessmentFeature(assessment.id, featureId, { accessToken });
      setFeatures((prev) => prev.filter((f) => f.id !== featureId));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete feature";
      alert(message);
    }
  }

  if (!assessment) {
    return null;
  }

  const seed = state.seeds.find((item) => item.id === assessment.seedId);
  const invites = state.invitations.filter((invite) => invite.assessmentId === assessment.id);

  function scheduleReset(inviteId: string) {
    setTimeout(() => {
      setCopyStates((prev) => {
        if (!(inviteId in prev)) {
          return prev;
        }
        const { [inviteId]: _, ...rest } = prev;
        return rest;
      });
    }, 2000);
  }

  async function handleCopyInvite(inviteId: string, startLinkToken?: string | null) {
    const inviteLink = buildCandidateStartLink(startLinkToken, runtimeOrigin);
    if (!inviteLink) {
      setCopyStates((prev) => ({ ...prev, [inviteId]: "error" }));
      scheduleReset(inviteId);
      return;
    }

    try {
      if (!navigator.clipboard) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(inviteLink);
      setCopyStates((prev) => ({ ...prev, [inviteId]: "copied" }));
      scheduleReset(inviteId);
    } catch (copyError) {
      console.error("Failed to copy invite link", copyError);
      setCopyStates((prev) => ({ ...prev, [inviteId]: "error" }));
      scheduleReset(inviteId);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-zinc-500">Seed: {seed?.seedRepo}</p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-900">{assessment.title}</h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-500">
            {assessment.description ?? "No description provided yet."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild>
            <Link href={`/app/dashboard/assessments/${assessment.id}/invites`}>Manage invites</Link>
          </Button>
        </div>
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="rubric">Rubric</TabsTrigger>
          <TabsTrigger value="features">Scoring Features</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Candidate instructions</CardTitle>
                <CardDescription>Rendered Markdown shown on the candidate start page.</CardDescription>
              </CardHeader>
              <CardContent>
                <Markdown className="prose prose-zinc max-w-none">
                  {assessment.instructions ?? ""}
                </Markdown>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Time windows</CardTitle>
                <CardDescription>Deadlines are calculated when invites are sent and started.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm text-zinc-600">
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-400">Time to start</p>
                  <p className="text-lg font-semibold text-zinc-900">{assessment.timeToStartHours} hours</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-400">Time to complete</p>
                  <p className="text-lg font-semibold text-zinc-900">{assessment.timeToCompleteHours} hours</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-400">Created</p>
                  <p>{format(new Date(assessment.createdAt), "MMM d, yyyy")}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-400">Seed SHA</p>
                  <p className="font-mono text-sm">{seed?.latestMainSha}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="rubric">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Review Rubric</CardTitle>
              <CardDescription>
                Markdown text that will be displayed to reviewers when evaluating submissions. This helps standardize
                the review process.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="rubric-text">Rubric Text (Markdown)</Label>
                <Textarea
                  id="rubric-text"
                  value={rubricText}
                  onChange={(e) => setRubricText(e.target.value)}
                  placeholder="Enter rubric text in Markdown format..."
                  className="mt-2 min-h-[300px] font-mono text-sm"
                />
              </div>
              {rubricError && <p className="text-sm text-red-600">{rubricError}</p>}
              <div className="flex gap-2">
                <Button onClick={handleSaveRubric} disabled={savingRubric || !accessToken}>
                  {savingRubric ? "Saving..." : "Save Rubric"}
                </Button>
              </div>
              {rubricText && (
                <div className="mt-6 border-t pt-6">
                  <Label>Preview</Label>
                  <div className="mt-2 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
                    <Markdown className="prose prose-zinc max-w-none">{rubricText}</Markdown>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="features">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">Scoring Features</CardTitle>
                  <CardDescription>
                    Define checklist items that reviewers can check off. Each feature has a weight for score
                    calculation.
                  </CardDescription>
                </div>
                <Button onClick={() => handleStartEditFeature()} disabled={!accessToken || showFeatureForm}>
                  Add Feature
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {showFeatureForm && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                  <h3 className="mb-4 font-semibold text-zinc-900">
                    {editingFeature ? "Edit Feature" : "New Feature"}
                  </h3>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="feature-name">
                        Feature Name <span className="text-red-500">*</span>
                      </Label>
                      <Input
                        id="feature-name"
                        value={featureForm.name}
                        onChange={(e) => setFeatureForm({ ...featureForm, name: e.target.value })}
                        placeholder="e.g., Authentication implemented"
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label htmlFor="feature-description">Description (optional)</Label>
                      <Textarea
                        id="feature-description"
                        value={featureForm.description}
                        onChange={(e) => setFeatureForm({ ...featureForm, description: e.target.value })}
                        placeholder="Additional details about this feature..."
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label htmlFor="feature-weight">Weight</Label>
                      <Input
                        id="feature-weight"
                        type="number"
                        step="0.1"
                        min="0"
                        value={featureForm.weight}
                        onChange={(e) => setFeatureForm({ ...featureForm, weight: e.target.value })}
                        className="mt-1"
                      />
                      <p className="mt-1 text-xs text-zinc-500">Points awarded when checked. Features are sorted by highest weight first.</p>
                    </div>
                    {featureError && <p className="text-sm text-red-600">{featureError}</p>}
                    <div className="flex gap-2">
                      <Button onClick={handleSaveFeature} disabled={savingFeature || !featureForm.name.trim()}>
                        {savingFeature ? "Saving..." : editingFeature ? "Update Feature" : "Create Feature"}
                      </Button>
                      <Button variant="outline" onClick={handleCancelFeatureForm} disabled={savingFeature}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {loadingFeatures ? (
                <p className="py-4 text-sm text-zinc-500">Loading features...</p>
              ) : features.length === 0 ? (
                <p className="py-8 text-center text-sm text-zinc-500">
                  No features defined yet. Click "Add Feature" to get started.
                </p>
              ) : (
                <div className="space-y-3">
                  {features.map((feature) => (
                    <div key={feature.id} className="flex items-start justify-between rounded-lg border border-zinc-200 bg-white p-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-3">
                          <h4 className="font-medium text-zinc-900">{feature.name}</h4>
                          <Badge variant="outline">Weight: {feature.weight}</Badge>
                        </div>
                        {feature.description && (
                          <p className="mt-1 text-sm text-zinc-600">{feature.description}</p>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleStartEditFeature(feature)}
                          disabled={!accessToken || showFeatureForm}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDeleteFeature(feature.id)}
                          disabled={!accessToken || showFeatureForm}
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                  <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-600">
                    <p className="font-medium text-zinc-900">Total Max Score: {features.reduce((sum, f) => sum + f.weight, 0).toFixed(2)}</p>
                    <p className="mt-1">This is the maximum possible score if all features are checked.</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Candidates & Rankings</CardTitle>
              <CardDescription>
                {sortMode === "auto" 
                  ? "Candidates are ranked by score (highest first)."
                  : "Candidates are ranked in manual order."}
              </CardDescription>
            </div>
            <Badge variant="outline" className="capitalize">
              {sortMode === "auto" ? "Auto Ranking" : "Manual Ranking"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {loadingScores ? (
            <p className="py-4 text-sm text-zinc-500">Loading scores...</p>
          ) : invites.length === 0 ? (
            <p className="py-6 text-sm text-zinc-500">No invites yet.</p>
          ) : (
            <div className="space-y-3">
              {(() => {
                // Map invites with scores
                const invitesWithScores = invites.map((invite) => {
                  const scoreData = invitationScores[invite.id];
                  const score = scoreData?.score || { totalScore: 0, maxScore: features.reduce((sum, f) => sum + f.weight, 0), percentage: 0 };
                  return { invite, score };
                });

                // Sort based on mode
                let sortedInvites;
                if (sortMode === "manual" && manualRanking?.invitationIds && manualRanking.invitationIds.length > 0) {
                  // Manual mode: sort by manual ranking order
                  const orderMap = new Map(manualRanking.invitationIds.map((id, index) => [id, index]));
                  sortedInvites = [...invitesWithScores].sort((a, b) => {
                    const aIndex = orderMap.get(a.invite.id) ?? Infinity;
                    const bIndex = orderMap.get(b.invite.id) ?? Infinity;
                    return aIndex - bIndex;
                  });
                } else {
                  // Auto mode: sort by score
                  sortedInvites = [...invitesWithScores].sort((a, b) => {
                    // Sort by percentage (highest first), then by total score, then by name
                    if (b.score.percentage !== a.score.percentage) {
                      return b.score.percentage - a.score.percentage;
                    }
                    // If same percentage, sort by total score
                    if (b.score.totalScore !== a.score.totalScore) {
                      return b.score.totalScore - a.score.totalScore;
                    }
                    // Tie-breaker: sort by name
                    return a.invite.candidateName.localeCompare(b.invite.candidateName);
                  });
                }

                return sortedInvites.map(({ invite, score }, index) => {
                  // Always assign rank (everyone starts at 0)
                  const rank = index + 1;
                  return (
                    <div
                      key={invite.id}
                      className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex items-start gap-4">
                        <div className="flex min-w-[3rem] items-center justify-center">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 font-semibold text-blue-700">
                            #{rank}
                          </div>
                        </div>
                        <div className="flex-1">
                          <p className="font-medium text-zinc-900">{invite.candidateName}</p>
                          <p className="text-sm text-zinc-500">{invite.candidateEmail}</p>
                        </div>
                      </div>
                      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
                        <div className="flex items-center gap-4">
                          <div className="w-24">
                            <Badge className="capitalize">{invite.status}</Badge>
                          </div>
                          <div className="flex items-center gap-2 text-sm min-w-[140px]">
                            <span className="font-semibold text-zinc-900">
                              {score.totalScore.toFixed(2)} / {score.maxScore.toFixed(2)}
                            </span>
                            <span className="text-zinc-500 w-14 text-left">({score.percentage.toFixed(1)}%)</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button asChild size="sm" variant="outline">
                            <Link href={`/app/review/${invite.id}`}>Review</Link>
                          </Button>
                          {invite.startLinkToken ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleCopyInvite(invite.id, invite.startLinkToken)}
                            >
                              {copyStates[invite.id] === "copied"
                                ? "Copied!"
                                : copyStates[invite.id] === "error"
                                  ? "Copy failed"
                                  : "Copy invite link"}
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
