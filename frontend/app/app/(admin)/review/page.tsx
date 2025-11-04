"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useAdminData } from "@/providers/admin-data-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronRight } from "lucide-react";

export default function ReviewQueuePage() {
  const { state } = useAdminData();
  const reviewable = state.invitations.filter((invite) => invite.status === "submitted" || invite.status === "started");

  const groupedByAssessment = useMemo(() => {
    const grouped = new Map<string, typeof reviewable>();
    
    reviewable.forEach((invite) => {
      const assessmentId = invite.assessmentId;
      if (!grouped.has(assessmentId)) {
        grouped.set(assessmentId, []);
      }
      grouped.get(assessmentId)!.push(invite);
    });

    // Sort each group: submitted first, then by updated time (most recent first)
    grouped.forEach((invites) => {
      invites.sort((a, b) => {
        if (a.status === "submitted" && b.status !== "submitted") return -1;
        if (a.status !== "submitted" && b.status === "submitted") return 1;
        
        const aUpdated = a.submittedAt || state.candidateRepos.find((r) => r.invitationId === a.id)?.lastCommitAt || a.sentAt;
        const bUpdated = b.submittedAt || state.candidateRepos.find((r) => r.invitationId === b.id)?.lastCommitAt || b.sentAt;
        return new Date(bUpdated).getTime() - new Date(aUpdated).getTime();
      });
    });

    // Sort assessments by title
    const sortedEntries = Array.from(grouped.entries()).sort(([aId], [bId]) => {
      const aAssessment = state.assessments.find((a) => a.id === aId);
      const bAssessment = state.assessments.find((a) => a.id === bId);
      const aTitle = aAssessment?.title || "";
      const bTitle = bAssessment?.title || "";
      return aTitle.localeCompare(bTitle);
    });

    return sortedEntries;
  }, [reviewable, state.assessments, state.candidateRepos]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Review queue</h1>
          <p className="text-sm text-zinc-500">
            Jump into candidate repos, compare against seeds, and capture comments for the hiring team.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/app/dashboard/assessments">Back to assessments</Link>
        </Button>
      </div>

      {groupedByAssessment.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-zinc-500">
            No candidates ready for review.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {groupedByAssessment.map(([assessmentId, invites]) => {
            const assessment = state.assessments.find((a) => a.id === assessmentId);

            return (
              <Card key={assessmentId} className="hover:shadow-md transition-shadow">
                <Link href={`/app/review/assessment/${assessmentId}`}>
                  <CardHeader className="hover:bg-zinc-50 transition-colors cursor-pointer">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <CardTitle className="text-base">{assessment?.title || "Unknown Assessment"}</CardTitle>
                        <CardDescription>
                          {invites.length} candidate{invites.length !== 1 ? "s" : ""} ready for review
                        </CardDescription>
                      </div>
                      <ChevronRight className="h-5 w-5 text-zinc-400 flex-shrink-0 ml-4" />
                    </div>
                  </CardHeader>
                </Link>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
