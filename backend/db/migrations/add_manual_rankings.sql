-- Add manual ranking support for assessments
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

CREATE INDEX IF NOT EXISTS idx_assessment_manual_rankings_assessment_id 
  ON assessment_manual_rankings(assessment_id);

CREATE INDEX IF NOT EXISTS idx_assessment_manual_rankings_display_order 
  ON assessment_manual_rankings(assessment_id, display_order);


