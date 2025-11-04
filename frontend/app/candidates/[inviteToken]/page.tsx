import { notFound } from "next/navigation";
import { CandidateStartView } from "@/components/candidate/candidate-start-view";
import { fetchCandidateStart } from "@/lib/api";

export default async function CandidateStartPage({
  params,
}: {
  params: { inviteToken: string };
}) {
  const inviteToken = params.inviteToken;

  try {
    const data = await fetchCandidateStart(inviteToken);
    return (
      <CandidateStartView
        invitation={data.invitation}
        assessment={data.assessment}
        seed={data.seed}
        repo={data.candidateRepo}
        startToken={inviteToken}
      />
    );
  } catch (error) {
    if (error instanceof Error && error.message.includes("404")) {
      notFound();
    }
    throw error;
  }
}
