export type Seed = {
  id: string;
  sourceRepoUrl: string;
  seedRepo: string;
  seedRepoUrl: string;
  defaultBranch?: string;
  latestMainSha: string | null;
  createdAt: string;
};

export type Assessment = {
  id: string;
  orgId: string;
  seedId: string;
  title: string;
  description: string | null;
  instructions: string | null;
  candidateEmailSubject: string | null;
  candidateEmailBody: string | null;
  timeToStartHours: number;
  timeToCompleteHours: number;
  createdBy: string | null;
  createdAt: string;
  rubricText: string | null;
  sortMode?: "auto" | "manual";
};

export type InvitationStatus =
  | "sent"
  | "accepted"
  | "started"
  | "submitted"
  | "expired"
  | "revoked";

export type Invitation = {
  id: string;
  assessmentId: string;
  candidateEmail: string;
  candidateName: string;
  status: InvitationStatus;
  startDeadline: string | null;
  completeDeadline: string | null;
  startLinkToken?: string | null;
  sentAt: string;
  startedAt?: string | null;
  submittedAt?: string | null;
  videoUrl?: string | null;
};

export type CandidateRepo = {
  id: string;
  invitationId: string;
  repoFullName: string;
  repoHtmlUrl: string | null;
  seedShaPinned: string;
  startedAt: string;
  lastCommitAt?: string | null;
};

export type CandidateStartInvitation = {
  id: string;
  assessmentId: string;
  candidateEmail: string;
  candidateName: string;
  status: InvitationStatus;
  startDeadline: string | null;
  completeDeadline: string | null;
  sentAt: string;
  startedAt: string | null;
  submittedAt: string | null;
};

export type CandidateStartAssessment = {
  id: string;
  seedId: string;
  title: string;
  description: string | null;
  instructions: string | null;
  candidateEmailSubject: string | null;
  candidateEmailBody: string | null;
  timeToStartHours: number;
  timeToCompleteHours: number;
};

export type CandidateStartSeed = {
  id: string;
  seedRepo: string;
  seedRepoUrl: string;
  latestMainSha: string | null;
  sourceRepoUrl: string;
};

export type CandidateStartActionResult = {
  invitationId: string;
  status: InvitationStatus;
  startedAt: string;
  completeDeadline: string | null;
  candidateRepo: CandidateRepo;
  accessToken: string;
  accessTokenExpiresAt: string;
};

export type CandidateSubmitResult = {
  invitationId: string;
  submissionId: string;
  finalSha: string;
  submittedAt: string;
  status: InvitationStatus;
};

export type ReviewComment = {
  id: string;
  invitationId: string;
  author: string | null;
  body: string;
  createdAt: string;
};

export type DiffCommit = {
  sha: string;
  message: string;
  author: string;
  date: string;
};

export type DiffFile = {
  filename: string;
  status: string; // "added", "removed", "modified", "renamed"
  additions: number;
  deletions: number;
  changes: number;
  patch: string | null; // Unified diff format
  blobUrl: string | null;
  previousFilename?: string | null;
};

export type DiffResponse = {
  files: DiffFile[];
  totalAdditions: number;
  totalDeletions: number;
  totalChanges: number;
  commits: DiffCommit[];
  baseSha: string;
  headSha: string;
  htmlUrl: string | null; // GitHub compare URL
};

export type AdminUser = {
  id: string;
  name: string | null;
  email: string | null;
  role: string | null;
};

export type AdminMembership = {
  orgId: string;
  supabaseUserId: string;
  role: string;
  isApproved: boolean;
};

export type OrgProfile = {
  id: string;
  name: string;
  slug: string;
};

export type GitHubInstallation = {
  connected: boolean;
  installationId: number | null;
  accountLogin: string | null;
  accountHtmlUrl: string | null;
  installationHtmlUrl: string | null;
  targetType: string | null;
  connectedAt: string | null;
};

export type EmailTemplate = {
  id: string;
  orgId: string;
  key: string | null;
  name: string;
  subject: string | null;
  body: string | null;
  description: string | null;
  updatedAt: string;
};

export type AssessmentFeature = {
  id: string;
  assessmentId: string;
  name: string;
  description: string | null;
  weight: number;
  createdAt: string;
};

export type ReviewFeatureScore = {
  id: string;
  invitationId: string;
  featureId: string;
  checked: boolean;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
};

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

export type InvitationScoreData = {
  totalScore: number;
  maxScore: number;
  percentage: number;
};

export type InvitationScoreSummary = {
  invitationId: string;
  score: InvitationScoreData | null; // null if not scored yet
};

export type ReviewLLMAnalysis = {
  id: string;
  invitationId: string;
  analysisText: string;
  modelUsed?: string | null;
  promptVersion?: string | null;
  createdAt: string;
  createdBy?: string | null;
};

export type LLMConversationMessage = {
  id: string;
  invitationId: string;
  messageType: "user" | "assistant";
  messageText: string;
  modelUsed?: string | null;
  createdAt: string;
  createdBy?: string | null;
};
