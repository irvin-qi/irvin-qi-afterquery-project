"use client";

import Link from "next/link";
import { format } from "date-fns";
import { Plus } from "lucide-react";
import { useAdminData } from "@/providers/admin-data-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function AssessmentListPage() {
  const { state } = useAdminData();

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Assessments</h1>
          <p className="text-sm text-zinc-500">Manage seeds, instructions, and email copy for each take-home.</p>
        </div>
        <Button asChild className="gap-2">
          <Link href="/app/dashboard/assessments/new">
            <Plus className="h-4 w-4" /> New assessment
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assessment catalog</CardTitle>
          <CardDescription>Pinpoint seeds and review instructions before inviting candidates.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Seed repo</TableHead>
                <TableHead>Time windows</TableHead>
                <TableHead>Last updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {state.assessments.map((assessment) => {
                const seed = state.seeds.find((item) => item.id === assessment.seedId);
                return (
                  <TableRow key={assessment.id}>
                    <TableCell className="font-medium text-zinc-900">{assessment.title}</TableCell>
                    <TableCell>
                      {seed ? (
                        <a
                          href={seed.seedRepoUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          {seed.seedRepo}
                        </a>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      Start {assessment.timeToStartHours}h · Complete {assessment.timeToCompleteHours}h
                    </TableCell>
                    <TableCell>{format(new Date(assessment.createdAt), "MMM d, yyyy")}</TableCell>
                    <TableCell className="text-right">
                      <Button asChild size="sm" variant="outline">
                        <Link href={`/app/dashboard/assessments/${assessment.id}`}>Open</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
