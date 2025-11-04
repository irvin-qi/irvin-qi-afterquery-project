"use client";

import { formatDistanceToNow } from "date-fns";
import { useAdminData } from "@/providers/admin-data-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";

export default function DashboardPage() {
  const { state } = useAdminData();
  const activeInvites = state.invitations.filter(
    (invite) => invite.status !== "submitted" && invite.status !== "revoked",
  );
  const submitted = state.invitations.filter((invite) => invite.status === "submitted");
  const nextActiveDeadline = activeInvites.find((invite) => Boolean(invite.startDeadline))?.startDeadline ?? null;

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900">Welcome back</h1>
          <p className="text-sm text-zinc-500">
            Track assessment health, candidate progress, and follow-ups across your org.
          </p>
        </div>
        <Button asChild>
          <Link href="/app/dashboard/assessments/new">Create assessment</Link>
        </Button>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Assessments</CardDescription>
            <CardTitle className="text-3xl font-bold">{state.assessments.length}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-500">
            Latest seed: {state.seeds[0]?.seedRepo}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Active invitations</CardDescription>
            <CardTitle className="text-3xl font-bold">{activeInvites.length}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-500">
            {nextActiveDeadline
              ? `Next deadline ${formatDistanceToNow(new Date(nextActiveDeadline), { addSuffix: true })}`
              : "No pending deadlines"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Submitted reviews</CardDescription>
            <CardTitle className="text-3xl font-bold">{submitted.length}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-500">Ready for review workflows.</CardContent>
        </Card>
      </div>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">In-flight candidates</h2>
          <Button variant="outline" size="sm" asChild>
            <Link href="/app/review">Open review queue</Link>
          </Button>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {activeInvites.slice(0, 4).map((invite) => {
            const repo = state.candidateRepos.find((candidate) => candidate.invitationId === invite.id);
            const assessment = state.assessments.find((item) => item.id === invite.assessmentId);
            return (
              <Card key={invite.id}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0">
                  <div>
                    <CardTitle className="text-base font-semibold">{invite.candidateName}</CardTitle>
                    <CardDescription>{assessment?.title}</CardDescription>
                  </div>
                  <Badge className="capitalize">{invite.status}</Badge>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-zinc-500">
                  <p>Repo: {repo?.repoFullName ?? "Provisioning"}</p>
                  <p>
                    Start deadline:
                    {invite.startDeadline
                      ? ` ${formatDistanceToNow(new Date(invite.startDeadline), { addSuffix: true })}`
                      : " Not scheduled"}
                  </p>
                  {invite.completeDeadline && (
                    <p>
                      Submit by: {formatDistanceToNow(new Date(invite.completeDeadline), { addSuffix: true })}
                    </p>
                  )}
                  <Button size="sm" asChild>
                    <Link href={`/app/review/${invite.id}`}>Open review workspace</Link>
                  </Button>
                </CardContent>
              </Card>
            );
          })}
          {activeInvites.length === 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">No active candidates</CardTitle>
                <CardDescription>Invite a candidate to start tracking progress here.</CardDescription>
              </CardHeader>
            </Card>
          )}
        </div>
      </section>
    </div>
  );
}
