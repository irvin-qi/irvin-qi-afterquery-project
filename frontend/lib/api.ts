import type {
  Assessment,
  CandidateRepo,
  CandidateStartActionResult,
  CandidateStartAssessment,
  CandidateStartInvitation,
  CandidateStartSeed,
  CandidateSubmitResult,
  EmailTemplate,
  Invitation,
  InvitationStatus,
  LLMConversationMessage,
  OrgProfile,
  ReviewLLMAnalysis,
  Seed,
  GitHubInstallation,
  DiffResponse,
} from "./types";

const RAW_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API_BASE_URL = RAW_API_BASE.endsWith("/")
  ? RAW_API_BASE.slice(0, RAW_API_BASE.length - 1)
  : RAW_API_BASE;

export type ApiRequestOptions = RequestInit & { accessToken?: string };

// Re-export LLM types for convenience
export type { ReviewLLMAnalysis, LLMConversationMessage } from "./types";

class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`Request failed: ${status} ${detail}`);
    this.status = status;
    this.detail = detail;
    this.name = "ApiError";
  }
}

async function fetchJson<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const { accessToken, headers, ...init } = options;
  const mergedHeaders = new Headers(headers ?? {});
  if (!mergedHeaders.has("Accept")) {
    mergedHeaders.set("Accept", "application/json");
  }
  if (accessToken) {
    mergedHeaders.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${normalizedPath}`, {
    ...init,
    headers: mergedHeaders,
  });

  if (!response.ok) {
    const detail = await response.text();
    const error = new ApiError(response.status, detail);
    // For 404s, we still throw but it will be caught and handled silently by callers
    // The browser will still log network requests (this is normal browser behavior)
    throw error;
  }

  return (await response.json()) as T;
}

export type AdminOverviewResponse<
  TAssessment,
  TInvitation,
  TSeed,
  TRepo,
  TComment,
  TTemplate,
  TUser,
  TOrg,
  TMembership,
  TInstallation = GitHubInstallation
> = {
  assessments: TAssessment[];
  invitations: TInvitation[];
  seeds: TSeed[];
  candidateRepos: TRepo[];
  reviewComments: TComment[];
  emailTemplates: TTemplate[];
  currentAdmin: TUser | null;
  org: TOrg | null;
  membership: TMembership | null;
  githubInstallation: TInstallation | null;
};

export async function fetchAdminOverview<
  TAssessment,
  TInvitation,
  TSeed,
  TRepo,
  TComment,
  TTemplate,
  TUser,
  TOrg,
  TMembership,
  TInstallation = GitHubInstallation
>(options: ApiRequestOptions = {}) {
  return fetchJson<
    AdminOverviewResponse<
      TAssessment,
      TInvitation,
      TSeed,
      TRepo,
      TComment,
      TTemplate,
      TUser,
      TOrg,
      TMembership,
      TInstallation
    >
  >("/api/admin/overview", { cache: "no-store", ...options });
}

export type SaveEmailTemplatePayload = {
  subject: string;
  body: string;
};

export async function saveEmailTemplate(
  templateKey: string,
  payload: SaveEmailTemplatePayload,
  options: ApiRequestOptions = {},
): Promise<EmailTemplate> {
  const { headers, ...init } = options;
  const mergedHeaders = new Headers(headers ?? {});
  if (!mergedHeaders.has("Content-Type")) {
    mergedHeaders.set("Content-Type", "application/json");
  }

  return fetchJson<EmailTemplate>(
    `/api/admin/email-templates/${encodeURIComponent(templateKey)}`,
    {
      ...init,
      method: "PUT",
      body: JSON.stringify(payload),
      headers: mergedHeaders,
    },
  );
}

export type CreateOrganizationPayload = {
  name: string;
};

export async function createOrganization(
  payload: CreateOrganizationPayload,
  options: ApiRequestOptions = {},
): Promise<OrgProfile> {
  const { headers, ...init } = options;
  const mergedHeaders = new Headers(headers ?? {});
  if (!mergedHeaders.has("Content-Type")) {
    mergedHeaders.set("Content-Type", "application/json");
  }

  return fetchJson<OrgProfile>("/api/orgs", {
    ...init,
    method: "POST",
    body: JSON.stringify(payload),
    headers: mergedHeaders,
  });
}

type CandidateStartInvitationResponse = {
  id: string;
  assessmentId: string;
  candidateEmail: string;
  candidateName?: string | null;
  status: InvitationStatus;
  startDeadline?: string | null;
  completeDeadline?: string | null;
  sentAt: string;
  startedAt?: string | null;
  submittedAt?: string | null;
};

type CandidateStartAssessmentResponse = {
  id: string;
  seedId: string;
  title: string;
  description?: string | null;
  instructions?: string | null;
  candidateEmailSubject?: string | null;
  candidateEmailBody?: string | null;
  timeToStartHours: number;
  timeToCompleteHours: number;
};

type CandidateStartSeedResponse = {
  id: string;
  seedRepo: string;
  seedRepoUrl: string;
  latestMainSha?: string | null;
  sourceRepoUrl: string;
};

type CandidateStartRepoResponse = {
  id: string;
  invitationId: string;
  repoFullName: string;
  repoHtmlUrl?: string | null;
  seedShaPinned: string;
  startedAt: string;
  lastCommitAt?: string | null;
};

type CandidateRepoReadResponse = {
  id: string;
  invitation_id: string;
  seed_sha_pinned: string;
  repo_full_name: string;
  repo_html_url?: string | null;
  github_repo_id?: number | null;
  active: boolean;
  archived: boolean;
  created_at: string;
};

type CandidateStartResponse = {
  invitation: CandidateStartInvitationResponse;
  assessment: CandidateStartAssessmentResponse;
  seed: CandidateStartSeedResponse;
  candidateRepo?: CandidateStartRepoResponse | null;
};

export type CandidateStartData = {
  invitation: CandidateStartInvitation;
  assessment: CandidateStartAssessment;
  seed: CandidateStartSeed;
  candidateRepo?: CandidateRepo;
};

type StartAssessmentResponse = {
  invitation_id: string;
  status: InvitationStatus;
  started_at: string;
  complete_deadline?: string | null;
  candidate_repo: CandidateRepoReadResponse;
  access_token: string;
  access_token_expires_at: string;
};

type SubmitAssessmentResponse = {
  invitation_id: string;
  submission_id: string;
  final_sha: string;
  submitted_at: string;
  status: InvitationStatus;
};

export async function fetchCandidateStart(
  token: string,
  options: ApiRequestOptions = {},
): Promise<CandidateStartData> {
  const response = await fetchJson<CandidateStartResponse>(
    `/api/start/${encodeURIComponent(token)}`,
    { cache: "no-store", ...options },
  );

  const invitation: CandidateStartInvitation = {
    id: response.invitation.id,
    assessmentId: response.invitation.assessmentId,
    candidateEmail: response.invitation.candidateEmail,
    candidateName:
      response.invitation.candidateName ?? response.invitation.candidateEmail,
    status: response.invitation.status,
    startDeadline: response.invitation.startDeadline ?? null,
    completeDeadline: response.invitation.completeDeadline ?? null,
    sentAt: response.invitation.sentAt,
    startedAt: response.invitation.startedAt ?? null,
    submittedAt: response.invitation.submittedAt ?? null,
  };

  const assessment: CandidateStartAssessment = {
    id: response.assessment.id,
    seedId: response.assessment.seedId,
    title: response.assessment.title,
    description: response.assessment.description ?? null,
    instructions: response.assessment.instructions ?? null,
    candidateEmailSubject: response.assessment.candidateEmailSubject ?? null,
    candidateEmailBody: response.assessment.candidateEmailBody ?? null,
    timeToStartHours: response.assessment.timeToStartHours,
    timeToCompleteHours: response.assessment.timeToCompleteHours,
  };

  const seed: CandidateStartSeed = {
    id: response.seed.id,
    seedRepo: response.seed.seedRepo,
    seedRepoUrl: response.seed.seedRepoUrl,
    latestMainSha: response.seed.latestMainSha ?? null,
    sourceRepoUrl: response.seed.sourceRepoUrl,
  };

  const candidateRepo: CandidateRepo | undefined = response.candidateRepo
    ? {
        id: response.candidateRepo.id,
        invitationId: response.candidateRepo.invitationId,
        repoFullName: response.candidateRepo.repoFullName,
        repoHtmlUrl: response.candidateRepo.repoHtmlUrl ?? null,
        seedShaPinned: response.candidateRepo.seedShaPinned,
        startedAt: response.candidateRepo.startedAt,
        lastCommitAt: response.candidateRepo.lastCommitAt ?? null,
      }
    : undefined;

  return {
    invitation,
    assessment,
    seed,
    candidateRepo,
  };
}

export async function startCandidateAssessment(
  token: string,
  options: ApiRequestOptions = {},
): Promise<CandidateStartActionResult> {
  const response = await fetchJson<StartAssessmentResponse>(
    `/api/start/${encodeURIComponent(token)}`,
    {
      method: "POST",
      ...options,
    },
  );

  const repo: CandidateRepo = {
    id: response.candidate_repo.id,
    invitationId: response.candidate_repo.invitation_id,
    repoFullName: response.candidate_repo.repo_full_name,
    repoHtmlUrl: response.candidate_repo.repo_html_url ?? null,
    seedShaPinned: response.candidate_repo.seed_sha_pinned,
    startedAt: response.candidate_repo.created_at,
    lastCommitAt: null,
  };

  return {
    invitationId: response.invitation_id,
    status: response.status,
    startedAt: response.started_at,
    completeDeadline: response.complete_deadline ?? null,
    candidateRepo: repo,
    accessToken: response.access_token,
    accessTokenExpiresAt: response.access_token_expires_at,
  };
}

export type SubmitCandidateAssessmentPayload = {
  finalSha?: string;
  repoHtmlUrl?: string;
  videoUrl?: string;
};

export async function submitCandidateAssessment(
  token: string,
  payload: SubmitCandidateAssessmentPayload = {},
  options: ApiRequestOptions = {},
): Promise<CandidateSubmitResult> {
  const response = await fetchJson<SubmitAssessmentResponse>(
    `/api/submit/${encodeURIComponent(token)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        final_sha: payload.finalSha,
        repo_html_url: payload.repoHtmlUrl,
      }),
      ...options,
    },
  );

  return {
    invitationId: response.invitation_id,
    submissionId: response.submission_id,
    finalSha: response.final_sha,
    submittedAt: response.submitted_at,
    status: response.status,
  };
}

export type CreateSeedPayload = {
  orgId: string;
  sourceRepoUrl: string;
  defaultBranch?: string;
};

type SeedReadResponse = {
  id: string;
  org_id: string;
  source_repo_url: string;
  seed_repo_full_name: string;
  default_branch: string;
  latest_main_sha: string | null;
  created_at: string;
  seed_repo_url: string;
};

export async function createSeed(payload: CreateSeedPayload, options: ApiRequestOptions = {}) {
  const body = {
    org_id: payload.orgId,
    source_repo_url: payload.sourceRepoUrl,
    default_branch: payload.defaultBranch ?? "main",
  };

  const seed = await fetchJson<SeedReadResponse>("/api/seeds", {
    ...options,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    body: JSON.stringify(body),
  });

  const normalized: Seed = {
    id: seed.id,
    sourceRepoUrl: seed.source_repo_url,
    seedRepo: seed.seed_repo_full_name,
    seedRepoUrl: seed.seed_repo_url ?? `https://github.com/${seed.seed_repo_full_name}`,
    defaultBranch: seed.default_branch,
    latestMainSha: seed.latest_main_sha,
    createdAt: seed.created_at,
  };

  return normalized;
}

type GitHubInstallationStartResponse = {
  installationUrl: string;
};

export type GitHubInstallationStartOptions = ApiRequestOptions & {
  redirectUrl?: string;
  returnPath?: string;
};

export async function startGitHubInstallation(
  orgId: string,
  options: GitHubInstallationStartOptions = {},
) {
  const { redirectUrl, returnPath, headers, ...requestOptions } = options;

  const response = await fetchJson<GitHubInstallationStartResponse>(
    "/api/github/installations/start",
    {
      ...requestOptions,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(headers ?? {}),
      },
      body: JSON.stringify({
        org_id: orgId,
        ...(redirectUrl ? { redirect_url: redirectUrl } : {}),
        ...(returnPath ? { return_path: returnPath } : {}),
      }),
    },
  );

  return response.installationUrl;
}

type GitHubInstallationCompleteResponse = {
  installation: GitHubInstallation;
  returnPath?: string | null;
};

export async function completeGitHubInstallation(
  state: string,
  installationId: number,
  options: ApiRequestOptions = {},
): Promise<GitHubInstallationCompleteResponse> {
  return fetchJson<GitHubInstallationCompleteResponse>("/api/github/installations/complete", {
    ...options,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    body: JSON.stringify({ state, installation_id: installationId }),
  });
}

export type CreateAssessmentPayload = {
  orgId: string;
  seedId: string;
  title: string;
  description: string;
  instructions: string;
  candidateEmailSubject: string;
  candidateEmailBody: string;
  timeToStartHours: number;
  timeToCompleteHours: number;
  createdBy?: string | null;
};

type AssessmentReadResponse = {
  id: string;
  org_id: string;
  seed_id: string;
  title: string;
  description: string | null;
  instructions: string | null;
  candidate_email_subject: string | null;
  candidate_email_body: string | null;
  time_to_start: number | string;
  time_to_complete: number | string;
  created_by: string | null;
  created_at: string;
};

export async function createAssessment(
  payload: CreateAssessmentPayload,
  options: ApiRequestOptions = {},
) {
  const body = {
    org_id: payload.orgId,
    seed_id: payload.seedId,
    title: payload.title,
    description: payload.description || null,
    instructions: payload.instructions || null,
    candidate_email_subject: payload.candidateEmailSubject || null,
    candidate_email_body: payload.candidateEmailBody || null,
    time_to_start: payload.timeToStartHours * 3600,
    time_to_complete: payload.timeToCompleteHours * 3600,
    created_by: payload.createdBy ?? null,
  };

  const assessment = await fetchJson<AssessmentReadResponse>("/api/assessments", {
    ...options,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    body: JSON.stringify(body),
  });

  const toHours = (value: number | string | null | undefined) => {
    if (typeof value === "number") {
      return Math.round(value / 3600);
    }
    if (typeof value === "string") {
      const numeric = Number(value);
      if (!Number.isNaN(numeric)) {
        return Math.round(numeric / 3600);
      }
    }
    return 0;
  };

  const normalized: Assessment = {
    id: assessment.id,
    orgId: assessment.org_id,
    seedId: assessment.seed_id,
    title: assessment.title,
    description: assessment.description,
    instructions: assessment.instructions,
    candidateEmailSubject: assessment.candidate_email_subject,
    candidateEmailBody: assessment.candidate_email_body,
    timeToStartHours: toHours(assessment.time_to_start),
    timeToCompleteHours: toHours(assessment.time_to_complete),
    createdBy: assessment.created_by,
    createdAt: assessment.created_at,
  };

  return normalized;
}

type InvitationReadResponse = {
  id: string;
  assessment_id: string;
  candidate_email: string;
  candidate_name: string | null;
  status: string;
  start_deadline: string | null;
  complete_deadline: string | null;
  start_link_token: string;
  sent_at: string;
  started_at?: string | null;
  submitted_at?: string | null;
};

type AdminInvitationResponse = {
  id: string;
  assessment_id: string;
  candidate_email: string;
  candidate_name: string | null;
  status: string;
  start_deadline: string | null;
  complete_deadline: string | null;
  start_link_token?: string | null;
  sent_at: string;
  started_at?: string | null;
  submitted_at?: string | null;
};

export type CreateInvitationPayload = {
  candidateEmail: string;
  candidateName?: string;
};

export async function createInvitations(
  assessmentId: string,
  invitations: CreateInvitationPayload[],
  options: ApiRequestOptions = {},
) {
  const body = {
    assessment_id: assessmentId,
    invitations: invitations.map((invite) => ({
      candidate_email: invite.candidateEmail,
      candidate_name: invite.candidateName ?? invite.candidateEmail,
    })),
  };

  const created = await fetchJson<InvitationReadResponse[]>("/api/invitations", {
    ...options,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    body: JSON.stringify(body),
  });

  return created.map<Invitation>((invite) => ({
    id: invite.id,
    assessmentId: invite.assessment_id,
    candidateEmail: invite.candidate_email,
    candidateName: invite.candidate_name ?? invite.candidate_email,
    status: invite.status as Invitation["status"],
    startDeadline: invite.start_deadline ?? null,
    completeDeadline: invite.complete_deadline ?? null,
    startLinkToken: invite.start_link_token,
    sentAt: invite.sent_at,
    startedAt: invite.started_at ?? null,
    submittedAt: invite.submitted_at ?? null,
  }));
}

export async function markInvitationSubmitted(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<Invitation> {
  const response = await fetchJson<AdminInvitationResponse>(
    `/api/invitations/${encodeURIComponent(invitationId)}/mark-submitted`,
    {
      ...options,
      method: "POST",
    },
  );

  return {
    id: response.id,
    assessmentId: response.assessment_id,
    candidateEmail: response.candidate_email,
    candidateName: response.candidate_name ?? response.candidate_email,
    status: response.status as Invitation["status"],
    startDeadline: response.start_deadline ?? null,
    completeDeadline: response.complete_deadline ?? null,
    startLinkToken: response.start_link_token ?? null,
    sentAt: response.sent_at,
    startedAt: response.started_at ?? null,
    submittedAt: response.submitted_at ?? null,
  };
}

export async function revokeInvitation(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<Invitation> {
  const response = await fetchJson<AdminInvitationResponse>(
    `/api/invitations/${encodeURIComponent(invitationId)}/revoke`,
    {
      ...options,
      method: "PATCH",
    },
  );

  return {
    id: response.id,
    assessmentId: response.assessment_id,
    candidateEmail: response.candidate_email,
    candidateName: response.candidate_name ?? response.candidate_email,
    status: response.status as Invitation["status"],
    startDeadline: response.start_deadline ?? null,
    completeDeadline: response.complete_deadline ?? null,
    startLinkToken: response.start_link_token ?? null,
    sentAt: response.sent_at,
    startedAt: response.started_at ?? null,
    submittedAt: response.submitted_at ?? null,
  };
}

export async function deleteInvitation(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<void> {
  await fetchJson<void>(
    `/api/invitations/${encodeURIComponent(invitationId)}`,
    {
      ...options,
      method: "DELETE",
    },
  );
}

export async function clearManualRanking(
  assessmentId: string,
  options: ApiRequestOptions = {},
): Promise<void> {
  await fetchJson<void>(
    `/api/assessments/${encodeURIComponent(assessmentId)}/manual-ranking`,
    {
      ...options,
      method: "DELETE",
    },
  );
}

// Assessment Features API

export type AssessmentFeature = {
  id: string;
  assessmentId: string;
  name: string;
  description: string | null;
  weight: number;
  createdAt: string;
};

export async function listAssessmentFeatures(
  assessmentId: string,
  options: ApiRequestOptions = {},
): Promise<AssessmentFeature[]> {
  const response = await fetchJson<Array<{
    id: string;
    assessment_id: string;
    name: string;
    description: string | null;
    weight: number;
    created_at: string;
  }>>(
    `/api/assessments/${encodeURIComponent(assessmentId)}/features`,
    { ...options, cache: "no-store" },
  );

  return response.map((f) => ({
    id: f.id,
    assessmentId: f.assessment_id,
    name: f.name,
    description: f.description,
    weight: f.weight,
    createdAt: f.created_at,
  })).sort((a, b) => b.weight - a.weight || a.name.localeCompare(b.name));
}

// Review Scoring API

export type ReviewScoreSummary = {
  invitationId: string;
  totalScore: number;
  maxScore: number;
  percentage: number;
  features: Array<{
    featureId: string;
    name: string;
    weight: number;
    checked: boolean;
    score: number;
  }>;
};

export async function getReviewScoreSummary(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<ReviewScoreSummary> {
  const response = await fetchJson<{
    invitation_id?: string;
    invitationId?: string;
    total_score?: number;
    totalScore?: number;
    max_score?: number;
    maxScore?: number;
    percentage?: number;
    features?: Array<{
      feature_id?: string;
      featureId?: string;
      name: string;
      weight: number;
      checked: boolean;
      score: number;
    }>;
  }>(
    `/api/candidate-repos/invitations/${encodeURIComponent(invitationId)}/score-summary`,
    { ...options, cache: "no-store" },
  );

  const totalScore = Number(response.totalScore ?? response.total_score ?? 0);
  const maxScore = Number(response.maxScore ?? response.max_score ?? 0);
  const percentage = Number(response.percentage ?? 0);

  return {
    invitationId: response.invitationId || response.invitation_id || invitationId,
    totalScore: isNaN(totalScore) ? 0 : totalScore,
    maxScore: isNaN(maxScore) ? 0 : maxScore,
    percentage: isNaN(percentage) ? 0 : percentage,
    features: (response.features || []).map((f: any) => ({
      featureId: f.featureId || f.feature_id || "",
      name: f.name || "",
      weight: Number(f.weight) || 0,
      checked: f.checked ?? false,
      score: Number(f.score) || 0,
    })),
  };
}

export async function toggleFeatureScore(
  invitationId: string,
  featureId: string,
  options: ApiRequestOptions = {},
): Promise<ReviewScoreSummary> {
  const response = await fetchJson<{
    invitation_id?: string;
    invitationId?: string;
    total_score?: number;
    totalScore?: number;
    max_score?: number;
    maxScore?: number;
    percentage?: number;
    features?: Array<{
      feature_id?: string;
      featureId?: string;
      name: string;
      weight: number;
      checked: boolean;
      score: number;
    }>;
  }>(
    `/api/candidate-repos/invitations/${encodeURIComponent(invitationId)}/features/${encodeURIComponent(featureId)}/toggle`,
    {
      ...options,
      method: "POST",
      cache: "no-store",
    },
  );

  const totalScore = Number(response.totalScore ?? response.total_score ?? 0);
  const maxScore = Number(response.maxScore ?? response.max_score ?? 0);
  const percentage = Number(response.percentage ?? 0);

  return {
    invitationId: response.invitationId || response.invitation_id || invitationId,
    totalScore: isNaN(totalScore) ? 0 : totalScore,
    maxScore: isNaN(maxScore) ? 0 : maxScore,
    percentage: isNaN(percentage) ? 0 : percentage,
    features: (response.features || []).map((f: any) => ({
      featureId: f.featureId || f.feature_id || "",
      name: f.name || "",
      weight: Number(f.weight) || 0,
      checked: f.checked ?? false,
      score: Number(f.score) || 0,
    })),
  };
}

// Diff API

export async function fetchRepoDiff(
  repoId: string,
  headBranch: string = "main",
  options: ApiRequestOptions = {},
): Promise<DiffResponse> {
  return fetchJson<DiffResponse>(
    `/api/candidate-repos/${encodeURIComponent(repoId)}/diff?head_branch=${encodeURIComponent(headBranch)}`,
    { ...options, cache: "no-store" },
  );
}


// Assessment management API functions

export type UpdateAssessmentPayload = {
  rubricText?: string | null;
  sortMode?: "auto" | "manual";
};

export async function updateAssessment(
  assessmentId: string,
  payload: UpdateAssessmentPayload,
  options: ApiRequestOptions = {},
): Promise<Assessment> {
  const response = await fetchJson<AssessmentReadResponse>(
    `/api/assessments/${encodeURIComponent(assessmentId)}`,
    {
      ...options,
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      body: JSON.stringify({
        rubric_text: payload.rubricText,
        sort_mode: payload.sortMode,
      }),
    },
  );

  const toHours = (value: string | undefined): number => {
    if (value) {
      const match = value.match(/(\d+)/);
      if (match) {
        return parseInt(match[1], 10);
      }
    }
    return 0;
  };

  return {
    id: response.id,
    orgId: response.org_id,
    seedId: response.seed_id,
    title: response.title,
    description: response.description,
    instructions: response.instructions,
    candidateEmailSubject: response.candidate_email_subject,
    candidateEmailBody: response.candidate_email_body,
    timeToStartHours: toHours(response.time_to_start),
    timeToCompleteHours: toHours(response.time_to_complete),
    createdBy: response.created_by,
    createdAt: response.created_at,
    rubricText: response.rubric_text,
    sortMode: response.sort_mode as "auto" | "manual" | undefined,
  };
}

export type InvitationScoreSummary = {
  invitationId: string;
  score: {
    totalScore: number;
    maxScore: number;
    percentage: number;
  } | null;
};

export async function getAssessmentInvitationScores(
  assessmentId: string,
  options: ApiRequestOptions = {},
): Promise<InvitationScoreSummary[]> {
  const response = await fetchJson<
    Array<{
      invitationId?: string; // CamelModel converts to camelCase
      invitation_id?: string; // Fallback
      score: {
        totalScore?: number;
        total_score?: number;
        maxScore?: number;
        max_score?: number;
        percentage: number;
      } | null;
    }>
  >(`/api/assessments/${encodeURIComponent(assessmentId)}/invitation-scores`, options);

  console.log("[API] Raw response from getAssessmentInvitationScores:", response);

  return response.map((item) => {
    // CamelModel converts snake_case to camelCase, so try both
    const invitationId = item.invitationId || item.invitation_id;
    if (!invitationId) {
      console.error("[API] Missing invitationId in score response:", item);
    }
    return {
      invitationId: invitationId || "",
      score: item.score
        ? {
            totalScore: item.score.totalScore ?? item.score.total_score ?? 0,
            maxScore: item.score.maxScore ?? item.score.max_score ?? 0,
            percentage: item.score.percentage,
          }
        : null,
    };
  });
}

export type ManualRanking = {
  assessmentId: string;
  invitationIds: string[];
  createdAt: string;
  updatedAt: string;
};

export async function getManualRanking(
  assessmentId: string,
  options: ApiRequestOptions = {},
): Promise<ManualRanking | null> {
  const response = await fetchJson<{
    assessmentId?: string; // CamelModel converts to camelCase
    assessment_id?: string; // Fallback
    invitationIds?: string[]; // CamelModel converts to camelCase
    invitation_ids?: string[]; // Fallback
    createdAt?: string;
    created_at?: string;
    updatedAt?: string;
    updated_at?: string;
  } | null>(`/api/assessments/${encodeURIComponent(assessmentId)}/manual-ranking`, options);

  if (!response) {
    return null;
  }

  return {
    assessmentId: response.assessmentId || response.assessment_id || assessmentId,
    invitationIds: response.invitationIds || response.invitation_ids || [],
    createdAt: response.createdAt || response.created_at || new Date().toISOString(),
    updatedAt: response.updatedAt || response.updated_at || new Date().toISOString(),
  };
}

export async function saveManualRanking(
  assessmentId: string,
  invitationIds: string[],
  options: ApiRequestOptions = {},
): Promise<ManualRanking> {
  const response = await fetchJson<{
    assessmentId?: string; // CamelModel converts to camelCase
    assessment_id?: string; // Fallback
    invitationIds?: string[]; // CamelModel converts to camelCase
    invitation_ids?: string[]; // Fallback
    createdAt?: string;
    created_at?: string;
    updatedAt?: string;
    updated_at?: string;
  }>(
    `/api/assessments/${encodeURIComponent(assessmentId)}/manual-ranking`,
    {
      ...options,
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      body: JSON.stringify({
        invitation_ids: invitationIds,
      }),
    },
  );

  return {
    assessmentId: response.assessmentId || response.assessment_id || assessmentId,
    invitationIds: response.invitationIds || response.invitation_ids || [],
    createdAt: response.createdAt || response.created_at || new Date().toISOString(),
    updatedAt: response.updatedAt || response.updated_at || new Date().toISOString(),
  };
}

export type CreateAssessmentFeaturePayload = {
  name: string;
  description?: string | null;
  weight?: number;
};

export type UpdateAssessmentFeaturePayload = {
  name?: string;
  description?: string | null;
  weight?: number;
};

export async function createAssessmentFeature(
  assessmentId: string,
  payload: CreateAssessmentFeaturePayload,
  options: ApiRequestOptions = {},
): Promise<AssessmentFeature> {
  const response = await fetchJson<{
    id: string;
    assessment_id: string;
    name: string;
    description: string | null;
    weight: number;
    created_at: string;
  }>(
    `/api/assessments/${encodeURIComponent(assessmentId)}/features`,
    {
      ...options,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      body: JSON.stringify({
        name: payload.name,
        description: payload.description,
        weight: payload.weight ?? 1.0,
      }),
    },
  );

  return {
    id: response.id,
    assessmentId: response.assessment_id,
    name: response.name,
    description: response.description,
    weight: response.weight,
    createdAt: response.created_at,
  };
}

export async function updateAssessmentFeature(
  assessmentId: string,
  featureId: string,
  payload: UpdateAssessmentFeaturePayload,
  options: ApiRequestOptions = {},
): Promise<AssessmentFeature> {
  const response = await fetchJson<{
    id: string;
    assessment_id: string;
    name: string;
    description: string | null;
    weight: number;
    created_at: string;
  }>(
    `/api/assessments/${encodeURIComponent(assessmentId)}/features/${encodeURIComponent(featureId)}`,
    {
      ...options,
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      body: JSON.stringify({
        name: payload.name,
        description: payload.description,
        weight: payload.weight,
      }),
    },
  );

  return {
    id: response.id,
    assessmentId: response.assessment_id,
    name: response.name,
    description: response.description,
    weight: response.weight,
    createdAt: response.created_at,
  };
}

export async function deleteAssessmentFeature(
  assessmentId: string,
  featureId: string,
  options: ApiRequestOptions = {},
): Promise<void> {
  await fetchJson<void>(
    `/api/assessments/${encodeURIComponent(assessmentId)}/features/${encodeURIComponent(featureId)}`,
    {
      ...options,
      method: "DELETE",
    },
  );
}

// LLM Analysis API functions

export async function getLLMAnalysis(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<ReviewLLMAnalysis | null> {
  // Handle 404 silently - it's expected when no analysis exists yet
  try {
    const response = await fetchJson<ReviewLLMAnalysis>(
      `/api/candidate-repos/invitations/${encodeURIComponent(invitationId)}/llm-analysis`,
      options,
    );
    return response;
  } catch (error: any) {
    // If 404, return null (no analysis exists yet) - don't throw or log
    if (error?.status === 404 || error?.statusCode === 404) {
      return null;
    }
    // Re-throw other errors
    throw error;
  }
}

export async function generateLLMAnalysis(
  invitationId: string,
  regenerate: boolean = false,
  options: ApiRequestOptions = {},
): Promise<ReviewLLMAnalysis> {
  const url = `/api/candidate-repos/invitations/${encodeURIComponent(invitationId)}/llm-analysis/generate`;
  const payload = {
    invitation_id: invitationId,
    regenerate,
  };
  
  console.log(`🌐 [API] POST ${url}`);
  console.log(`📤 [API] Request payload:`, payload);
  
  const response = await fetchJson<ReviewLLMAnalysis>(
    url,
    {
      ...options,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      body: JSON.stringify(payload),
    },
  );
  
  console.log(`✅ [API] Response received:`, {
    id: response?.id,
    analysisLength: response?.analysisText?.length,
    model: response?.modelUsed,
  });
  
  return response;
}

export async function getLLMConversationHistory(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<LLMConversationMessage[]> {
  const response = await fetchJson<LLMConversationMessage[]>(
    `/api/candidate-repos/invitations/${encodeURIComponent(invitationId)}/llm-conversation`,
    options,
  );
  return response;
}

export async function askLLMQuestion(
  invitationId: string,
  question: string,
  options: ApiRequestOptions = {},
): Promise<LLMConversationMessage> {
  const response = await fetchJson<LLMConversationMessage>(
    `/api/candidate-repos/invitations/${encodeURIComponent(invitationId)}/llm-conversation/ask`,
    {
      ...options,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      body: JSON.stringify({
        question,
      }),
    },
  );
  return response;
}

// Scheduling API functions

export type CalComEventType = {
  id: string;
  title: string;
  slug?: string | null;
  description?: string | null;
  length?: number | null;
  hidden?: boolean | null;
};

export type CalComBookingResponse = {
  id: string;
  invitationId?: string | null;
  bookingId: string;
  eventTypeId?: string | null;
  bookingUrl?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  status?: string | null;
  title?: string | null;
  description?: string | null;
  createdAt: string;
};

export type SchedulingCandidate = {
  invitationId: string;
  candidateEmail: string;
  candidateName: string;
  assessmentId: string;
  assessmentTitle: string;
  status: string;
  submittedAt?: string | null;
  booking?: CalComBookingResponse | null;
};

export type SchedulingAssessment = {
  assessmentId: string;
  assessmentTitle: string;
  candidates: SchedulingCandidate[];
};

export async function getSchedulingCandidates(
  options: ApiRequestOptions = {},
): Promise<SchedulingAssessment[]> {
  return fetchJson<SchedulingAssessment[]>("/api/admin/scheduling/candidates", {
    ...options,
    cache: "no-store",
  });
}

export async function getCalComEventTypes(
  options: ApiRequestOptions = {},
): Promise<CalComEventType[]> {
  return fetchJson<CalComEventType[]>("/api/admin/scheduling/cal-com/event-types", {
    ...options,
    cache: "no-store",
  });
}

export type CreateCalComBookingPayload = {
  invitationId: string;
  eventTypeId: string;
  startTime?: string | null;
  timezone?: string;
};

export async function createCalComBooking(
  payload: CreateCalComBookingPayload,
  options: ApiRequestOptions = {},
): Promise<CalComBookingResponse> {
  const { headers, ...init } = options;
  const mergedHeaders = new Headers(headers ?? {});
  if (!mergedHeaders.has("Content-Type")) {
    mergedHeaders.set("Content-Type", "application/json");
  }

  return fetchJson<CalComBookingResponse>("/api/admin/scheduling/cal-com/bookings", {
    ...init,
    method: "POST",
    body: JSON.stringify({
      invitation_id: payload.invitationId,
      event_type_id: payload.eventTypeId,
      start_time: payload.startTime,
      timezone: payload.timezone || "UTC",
    }),
    headers: mergedHeaders,
  });
}

export async function getCalComBookings(
  options: ApiRequestOptions = {},
): Promise<CalComBookingResponse[]> {
  return fetchJson<CalComBookingResponse[]>("/api/admin/scheduling/cal-com/bookings", {
    ...options,
    cache: "no-store",
  });
}

export async function syncCalComBookings(
  options: ApiRequestOptions = {},
): Promise<{ updated: number; errors: number; total: number }> {
  return fetchJson<{ updated: number; errors: number; total: number }>(
    "/api/admin/scheduling/cal-com/sync-bookings",
    {
      ...options,
      method: "POST",
      cache: "no-store",
    },
  );
}

export async function deleteCalComBooking(
  bookingId: string,
  options: ApiRequestOptions = {},
): Promise<{ success: boolean; message: string }> {
  return fetchJson<{ success: boolean; message: string }>(
    `/api/admin/scheduling/cal-com/bookings/${encodeURIComponent(bookingId)}`,
    {
      ...options,
      method: "DELETE",
      cache: "no-store",
    },
  );
}

export type SendSchedulingEmailPayload = {
  invitationIds: string[];
  bookingUrl: string;
  subject?: string | null;
  message?: string | null;
};

export async function sendSchedulingEmails(
  payload: SendSchedulingEmailPayload,
  options: ApiRequestOptions = {},
): Promise<{ sent: number; failed: number; errors: string[] }> {
  const { headers, ...init } = options;
  const mergedHeaders = new Headers(headers ?? {});
  if (!mergedHeaders.has("Content-Type")) {
    mergedHeaders.set("Content-Type", "application/json");
  }

  return fetchJson<{ sent: number; failed: number; errors: string[] }>(
    "/api/admin/scheduling/send-emails",
    {
      ...init,
      method: "POST",
      body: JSON.stringify({
        invitation_ids: payload.invitationIds,
        booking_url: payload.bookingUrl,
        subject: payload.subject,
        message: payload.message,
      }),
      headers: mergedHeaders,
    },
  );
}
