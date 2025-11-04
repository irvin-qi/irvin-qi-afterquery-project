"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import { useAdminData } from "@/providers/admin-data-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { formatDistanceToNow } from "date-fns";
import {
  getAssessmentInvitationScores,
  type InvitationScoreSummary,
  getManualRanking,
  saveManualRanking,
  clearManualRanking,
  type ManualRanking,
  updateAssessment,
} from "@/lib/api";
import { useSupabaseAuth } from "@/providers/supabase-provider";

type SortMode = "auto" | "manual";

function SortableRow({
  invite,
  scoreData,
  loadingScores,
  repo,
  updatedAt,
  sortMode,
}: {
  invite: any;
  scoreData: any;
  loadingScores: boolean;
  repo: any;
  updatedAt: string;
  sortMode: SortMode;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: invite.id, disabled: sortMode !== "manual" });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <TableRow
      ref={setNodeRef}
      style={style}
      className={`${isDragging ? "z-50" : ""} ${sortMode === "manual" ? "cursor-grab active:cursor-grabbing" : ""}`}
      {...(sortMode === "manual" ? attributes : {})}
      {...(sortMode === "manual" ? listeners : {})}
    >
      <TableCell className="w-12">
        {sortMode === "manual" && (
          <div className="text-zinc-400">
            <GripVertical className="h-5 w-5" />
          </div>
        )}
      </TableCell>
      <TableCell className="font-medium text-zinc-900">{invite.candidateName}</TableCell>
      <TableCell>
        <Badge className="capitalize">{invite.status}</Badge>
      </TableCell>
      <TableCell>
        {loadingScores ? (
          <span className="text-xs text-zinc-400">Loading...</span>
        ) : scoreData ? (
          <span className="font-medium text-zinc-900">
            {scoreData.percentage.toFixed(1)}%
          </span>
        ) : (
          <span className="text-xs text-zinc-400">Not scored</span>
        )}
      </TableCell>
      <TableCell className="text-xs text-zinc-500">
        {formatDistanceToNow(new Date(updatedAt), {
          addSuffix: true,
        })}
      </TableCell>
      <TableCell className="text-right">
        <Button
          asChild
          size="sm"
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <Link href={`/app/review/${invite.id}`}>Open workspace</Link>
        </Button>
      </TableCell>
    </TableRow>
  );
}

export default function AssessmentReviewPage() {
  const params = useParams<{ assessmentId: string }>();
  const router = useRouter();
  const { state, dispatch } = useAdminData();
  const { accessToken } = useSupabaseAuth();
  const queryClient = useQueryClient();
  const assessmentId = params.assessmentId;

  const assessment = state.assessments.find((a) => a.id === assessmentId);
  const reviewable = state.invitations.filter(
    (invite) =>
      invite.assessmentId === assessmentId &&
      (invite.status === "submitted" || invite.status === "started")
  );

  // Initialize sort mode from assessment or default to auto
  const [sortMode, setSortMode] = useState<SortMode>("auto");
  const [localManualOrder, setLocalManualOrder] = useState<string[]>([]);

  // Fetch scores with React Query caching
  const {
    data: scores = [],
    isLoading: loadingScores,
  } = useQuery<InvitationScoreSummary[]>({
    queryKey: ["assessment-scores", assessmentId],
    queryFn: async () => {
      if (!assessment || !accessToken) {
        return [];
      }
      const result = await getAssessmentInvitationScores(assessment.id, { accessToken });
      console.log("[ASSESSMENT REVIEW] Fetched scores:", result);
      console.log("[ASSESSMENT REVIEW] Scores array length:", result.length);
      return result;
    },
    enabled: !!assessment && !!accessToken,
    staleTime: 2 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });

  // Fetch manual ranking
  const {
    data: manualRanking,
    isLoading: loadingRanking,
  } = useQuery<ManualRanking | null>({
    queryKey: ["manual-ranking", assessmentId],
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

  // Sync sort mode from assessment when it loads or changes
  useEffect(() => {
    if (assessment) {
      // Handle both camelCase (from API) and snake_case (from admin overview)
      const mode = (assessment as any).sortMode || (assessment as any).sort_mode || "auto";
      setSortMode(mode as SortMode);
    }
  }, [assessment]);

  // Sync local manual order with fetched ranking
  useEffect(() => {
    if (manualRanking?.invitationIds) {
      setLocalManualOrder(manualRanking.invitationIds);
    }
  }, [manualRanking]);

  // Save manual ranking mutation
  const saveRankingMutation = useMutation({
    mutationFn: async (invitationIds: string[]) => {
      if (!assessment || !accessToken) {
        throw new Error("Assessment or access token missing");
      }
      return saveManualRanking(assessment.id, invitationIds, { accessToken });
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["manual-ranking", assessmentId], data);
    },
  });

  // Clear manual ranking mutation
  const clearRankingMutation = useMutation({
    mutationFn: async () => {
      if (!assessment || !accessToken) {
        throw new Error("Assessment or access token missing");
      }
      return clearManualRanking(assessment.id, { accessToken });
    },
    onSuccess: () => {
      queryClient.setQueryData(["manual-ranking", assessmentId], null);
      setLocalManualOrder([]);
    },
  });

  // Auto-sorted list (by score)
  const autoSortedInvites = useMemo(() => {
    return [...reviewable].sort((a, b) => {
      const aScore = scores.find((s) => s.invitationId === a.id)?.score;
      const bScore = scores.find((s) => s.invitationId === b.id)?.score;

      if (aScore && bScore) {
        const scoreDiff = bScore.percentage - aScore.percentage;
        if (scoreDiff !== 0) return scoreDiff;
      } else if (aScore && !bScore) {
        return -1;
      } else if (!aScore && bScore) {
        return 1;
      }

      if (a.status === "submitted" && b.status !== "submitted") return -1;
      if (a.status !== "submitted" && b.status === "submitted") return 1;

      const aUpdated =
        a.submittedAt ||
        state.candidateRepos.find((r) => r.invitationId === a.id)?.lastCommitAt ||
        a.sentAt;
      const bUpdated =
        b.submittedAt ||
        state.candidateRepos.find((r) => r.invitationId === b.id)?.lastCommitAt ||
        b.sentAt;
      return new Date(bUpdated).getTime() - new Date(aUpdated).getTime();
    });
  }, [reviewable, state.candidateRepos, scores]);

  // Final sorted list based on mode
  const sortedInvites = useMemo(() => {
    if (sortMode === "auto") {
      return autoSortedInvites;
    }

    // Manual mode: use localManualOrder, then append any missing candidates
    const manualOrderSet = new Set(localManualOrder);
    const inManualOrder = localManualOrder
      .map((id) => reviewable.find((inv) => inv.id === id))
      .filter((inv): inv is typeof reviewable[0] => inv !== undefined);

    const notInManualOrder = autoSortedInvites.filter(
      (inv) => !manualOrderSet.has(inv.id)
    );

    return [...inManualOrder, ...notInManualOrder];
  }, [sortMode, localManualOrder, autoSortedInvites, reviewable]);

  // Handle drag end
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (!over || active.id === over.id || sortMode !== "manual") {
      return;
    }

    // Use the current sorted invites order as the base
    const currentOrder = sortedInvites.map((inv) => inv.id);
    const oldIndex = currentOrder.indexOf(active.id as string);
    const newIndex = currentOrder.indexOf(over.id as string);

    if (oldIndex === -1 || newIndex === -1) {
      // Should not happen, but handle gracefully
      return;
    }

    // Reorder the items
    const newOrder = arrayMove(currentOrder, oldIndex, newIndex);
    setLocalManualOrder(newOrder);
    saveRankingMutation.mutate(newOrder);
  };

  // Save sort mode mutation
  const saveSortModeMutation = useMutation({
    mutationFn: async (mode: SortMode) => {
      if (!assessment || !accessToken) {
        throw new Error("Assessment or access token missing");
      }
      return updateAssessment(assessment.id, { sortMode: mode }, { accessToken });
    },
    onSuccess: (updatedAssessment) => {
      // Update the assessment in admin data state
      dispatch({
        type: "updateAssessment",
        payload: updatedAssessment,
      });
    },
  });

  // Handle mode toggle
  const handleModeToggle = (checked: boolean) => {
    const newMode: SortMode = checked ? "manual" : "auto";
    setSortMode(newMode);
    
    // Save to database
    if (assessment) {
      saveSortModeMutation.mutate(newMode);
    }

    if (checked) {
      // Switching to manual mode
      if (localManualOrder.length === 0) {
        // If no manual order exists, check if we have one from the database
        if (manualRanking?.invitationIds && manualRanking.invitationIds.length > 0) {
          // Restore from database
          setLocalManualOrder(manualRanking.invitationIds);
        } else {
          // Initialize with current auto-sorted order
          const initialOrder = autoSortedInvites.map((inv) => inv.id);
          setLocalManualOrder(initialOrder);
          saveRankingMutation.mutate(initialOrder);
        }
      }
    }
    // Switching to auto mode - keep manual ranking in database, just don't use it
  };

  // Drag sensors - add activation distance to prevent accidental drags
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px of movement before starting drag
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  if (!assessment) {
    return (
      <div className="space-y-6">
        <Card>
          <CardContent className="py-8 text-center text-sm text-zinc-500">
            Assessment not found.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{assessment.title}</h1>
          <p className="text-sm text-zinc-500">
            {reviewable.length} candidate{reviewable.length !== 1 ? "s" : ""} ready for review
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/app/review">Back to review queue</Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Candidates</CardTitle>
              <CardDescription>
                {sortMode === "auto"
                  ? "Ranked by score (highest first), then by submission status."
                  : "Drag candidates to reorder manually."}
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <Label htmlFor="sort-mode" className="text-sm font-normal cursor-pointer">
                <span className={sortMode === "auto" ? "font-medium" : "text-zinc-500"}>
                  Auto
                </span>
                {" / "}
                <span className={sortMode === "manual" ? "font-medium" : "text-zinc-500"}>
                  Manual
                </span>
              </Label>
              <Switch
                id="sort-mode"
                checked={sortMode === "manual"}
                onCheckedChange={handleModeToggle}
                disabled={loadingRanking || saveRankingMutation.isPending || clearRankingMutation.isPending}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {sortedInvites.length === 0 ? (
            <div className="py-8 text-center text-sm text-zinc-500">
              No candidates ready for review in this assessment.
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12"></TableHead>
                    <TableHead>Candidate</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <SortableContext
                    items={sortedInvites.map((inv) => inv.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    {sortedInvites.map((invite) => {
                      const repo = state.candidateRepos.find(
                        (candidate) => candidate.invitationId === invite.id
                      );
                      const updatedAt =
                        invite.submittedAt || repo?.lastCommitAt || invite.sentAt;
                      const scoreData = scores.find((s) => s.invitationId === invite.id)?.score;
                      console.log("[ASSESSMENT REVIEW] Score lookup for", invite.id, ":", {
                        allScores: scores,
                        foundItem: scores.find((s) => s.invitationId === invite.id),
                        scoreData,
                      });

                      return (
                        <SortableRow
                          key={invite.id}
                          invite={invite}
                          scoreData={scoreData}
                          loadingScores={loadingScores}
                          repo={repo}
                          updatedAt={updatedAt}
                          sortMode={sortMode}
                        />
                      );
                    })}
                  </SortableContext>
                </TableBody>
              </Table>
            </DndContext>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
