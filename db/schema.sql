-- Coding Interview Platform Database Schema
-- Generated based on architecture plan for MVP implementation.

-- Enable required extensions (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenancy
CREATE TABLE IF NOT EXISTS orgs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS org_members (
  org_id uuid REFERENCES orgs(id) ON DELETE CASCADE,
  supabase_user_id uuid NOT NULL,
  email text,
  display_name text,
  role text CHECK (role IN ('owner','admin','viewer')) NOT NULL,
  is_approved boolean NOT NULL DEFAULT false,
  created_at timestamptz DEFAULT now(),
  PRIMARY KEY (org_id, supabase_user_id)
);
CREATE INDEX IF NOT EXISTS idx_org_members_supabase_user ON org_members(supabase_user_id);

-- GitHub App installations scoped to projects
CREATE TABLE IF NOT EXISTS github_installations (
  org_id uuid PRIMARY KEY REFERENCES orgs(id) ON DELETE CASCADE,
  installation_id bigint NOT NULL,
  target_type text NOT NULL,
  account_login text NOT NULL,
  account_id bigint NOT NULL,
  account_avatar_url text,
  account_html_url text,
  installation_html_url text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE (installation_id)
);

CREATE TABLE IF NOT EXISTS github_installation_states (
  token text PRIMARY KEY,
  org_id uuid REFERENCES orgs(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  return_path text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_github_installation_states_org_id ON github_installation_states(org_id);

-- Seeds
CREATE TABLE IF NOT EXISTS seeds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid REFERENCES orgs(id) ON DELETE CASCADE,
  source_repo_url text NOT NULL,
  seed_repo_full_name text NOT NULL,
  default_branch text NOT NULL DEFAULT 'main',
  is_template boolean NOT NULL DEFAULT true,
  latest_main_sha text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_seeds_org_id ON seeds(org_id);

-- Assessments
CREATE TABLE IF NOT EXISTS assessments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid REFERENCES orgs(id) ON DELETE CASCADE,
  seed_id uuid REFERENCES seeds(id) ON DELETE RESTRICT,
  title text NOT NULL,
  description text,
  instructions text,
  candidate_email_subject text,
  candidate_email_body text,
  time_to_start interval NOT NULL,
  time_to_complete interval NOT NULL,
  created_by uuid,
  rubric_text text,
  sort_mode text CHECK (sort_mode IN ('auto', 'manual')) DEFAULT 'auto',
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assessments_org_id ON assessments(org_id);
CREATE INDEX IF NOT EXISTS idx_assessments_sort_mode ON assessments(sort_mode);

-- Assessment features (scoring criteria)
CREATE TABLE IF NOT EXISTS assessment_features (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES assessments(id) ON DELETE CASCADE NOT NULL,
  name text NOT NULL,
  description text,
  weight decimal(10, 2) NOT NULL DEFAULT 1.0,
  created_at timestamptz DEFAULT now(),
  UNIQUE (assessment_id, name)
);
CREATE INDEX IF NOT EXISTS idx_assessment_features_assessment_id ON assessment_features(assessment_id);

-- Invitations
CREATE TABLE IF NOT EXISTS invitations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES assessments(id) ON DELETE CASCADE,
  candidate_email text NOT NULL,
  candidate_name text,
  status text CHECK (status IN ('sent','accepted','started','submitted','expired','revoked')) DEFAULT 'sent',
  start_deadline timestamptz,
  complete_deadline timestamptz,
  start_link_token_hash text UNIQUE NOT NULL,
  sent_at timestamptz DEFAULT now(),
  started_at timestamptz,
  submitted_at timestamptz,
  expired_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_invitations_assessment_id ON invitations(assessment_id);

-- Assessment manual rankings
-- Allows admins to manually order candidates within an assessment
CREATE TABLE IF NOT EXISTS assessment_manual_rankings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES assessments(id) ON DELETE CASCADE NOT NULL,
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE NOT NULL,
  display_order integer NOT NULL,
  created_by uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE (assessment_id, invitation_id)
);
CREATE INDEX IF NOT EXISTS idx_assessment_manual_rankings_assessment_id ON assessment_manual_rankings(assessment_id);
CREATE INDEX IF NOT EXISTS idx_assessment_manual_rankings_display_order ON assessment_manual_rankings(assessment_id, display_order);

-- Candidate repositories
CREATE TABLE IF NOT EXISTS candidate_repos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE,
  seed_sha_pinned text NOT NULL,
  repo_full_name text NOT NULL,
  repo_html_url text,
  github_repo_id bigint,
  active boolean DEFAULT true,
  archived boolean DEFAULT false,
  created_at timestamptz DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_repos_repo_full_name ON candidate_repos(repo_full_name);

-- Opaque access tokens (stored hashed)
CREATE TABLE IF NOT EXISTS access_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE,
  repo_full_name text NOT NULL,
  opaque_token_hash text UNIQUE NOT NULL,
  scope text CHECK (scope IN ('clone','push','clone+push')) DEFAULT 'clone+push',
  expires_at timestamptz NOT NULL,
  revoked boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  last_used_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_access_tokens_invitation_id ON access_tokens(invitation_id);

-- Submissions
CREATE TABLE IF NOT EXISTS submissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE,
  final_sha text NOT NULL,
  repo_html_url text,
  video_url text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_submissions_invitation_id ON submissions(invitation_id);

-- Review comments
CREATE TABLE IF NOT EXISTS review_comments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE,
  path text,
  line integer,
  body text NOT NULL,
  created_by uuid,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_review_comments_invitation_id ON review_comments(invitation_id);

-- Review feedback
CREATE TABLE IF NOT EXISTS review_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE,
  summary text,
  rating int CHECK (rating BETWEEN 1 AND 5),
  calculated_score decimal(10, 2),
  max_score decimal(10, 2),
  created_by uuid,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_review_feedback_invitation_id ON review_feedback(invitation_id);

-- Review feature scores (tracking which features are checked for each invitation)
CREATE TABLE IF NOT EXISTS review_feature_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE NOT NULL,
  feature_id uuid REFERENCES assessment_features(id) ON DELETE CASCADE NOT NULL,
  checked boolean NOT NULL DEFAULT false,
  created_by uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE (invitation_id, feature_id)
);
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_invitation_id ON review_feature_scores(invitation_id);
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_feature_id ON review_feature_scores(feature_id);

-- LLM Analysis tables
CREATE TABLE IF NOT EXISTS review_llm_analyses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE NOT NULL,
  analysis_text text NOT NULL,
  raw_response jsonb,
  model_used text,
  prompt_version text,
  created_by uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE (invitation_id)
);
CREATE INDEX IF NOT EXISTS idx_review_llm_analyses_invitation_id ON review_llm_analyses(invitation_id);
CREATE INDEX IF NOT EXISTS idx_review_llm_analyses_created_at ON review_llm_analyses(created_at DESC);

CREATE TABLE IF NOT EXISTS review_llm_conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE NOT NULL,
  message_type text CHECK (message_type IN ('user', 'assistant')) NOT NULL,
  message_text text NOT NULL,
  context_snapshot jsonb,
  model_used text,
  created_by uuid,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_review_llm_conversations_invitation_id ON review_llm_conversations(invitation_id, created_at);

-- Email templates
CREATE TABLE IF NOT EXISTS email_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid REFERENCES orgs(id) ON DELETE CASCADE,
  key text,
  subject text,
  body text,
  created_at timestamptz DEFAULT now(),
  UNIQUE (org_id, key)
);

-- Email events
CREATE TABLE IF NOT EXISTS email_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE,
  type text CHECK (type IN ('invite','reminder','follow_up','assessment_started','submission_received')),
  provider_id text,
  to_email text,
  status text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_events_invitation_id ON email_events(invitation_id);

-- Cal.com integration
CREATE TABLE IF NOT EXISTS cal_com_configs (
  org_id uuid PRIMARY KEY REFERENCES orgs(id) ON DELETE CASCADE,
  api_key text NOT NULL,
  api_url text DEFAULT 'https://api.cal.com/v1',
  user_id text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cal_com_bookings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE,
  booking_id text NOT NULL,
  event_type_id text,
  booking_url text,
  start_time timestamptz,
  end_time timestamptz,
  status text,
  title text,
  description text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE (booking_id)
);
CREATE INDEX IF NOT EXISTS idx_cal_com_bookings_invitation_id ON cal_com_bookings(invitation_id);
CREATE INDEX IF NOT EXISTS idx_cal_com_bookings_booking_id ON cal_com_bookings(booking_id);
CREATE INDEX IF NOT EXISTS idx_cal_com_bookings_start_time ON cal_com_bookings(start_time);

-- Audit events
CREATE TABLE IF NOT EXISTS audit_events (
  id bigserial PRIMARY KEY,
  kind text,
  actor text,
  meta jsonb,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_events_kind ON audit_events(kind);
CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at);

