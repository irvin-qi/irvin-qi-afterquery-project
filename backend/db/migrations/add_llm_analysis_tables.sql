-- Create review_llm_analyses table
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
CREATE INDEX IF NOT EXISTS idx_review_llm_analyses_invitation_id 
  ON review_llm_analyses(invitation_id);
CREATE INDEX IF NOT EXISTS idx_review_llm_analyses_created_at 
  ON review_llm_analyses(created_at DESC);

-- Create review_llm_conversations table
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
CREATE INDEX IF NOT EXISTS idx_review_llm_conversations_invitation_id 
  ON review_llm_conversations(invitation_id, created_at);
