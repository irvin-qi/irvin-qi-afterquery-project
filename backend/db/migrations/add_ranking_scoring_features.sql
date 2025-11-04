-- Add rubric_text to assessments
ALTER TABLE assessments
  ADD COLUMN IF NOT EXISTS rubric_text text;

-- Create assessment_features table
CREATE TABLE IF NOT EXISTS assessment_features (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES assessments(id) ON DELETE CASCADE NOT NULL,
  name text NOT NULL,
  description text,
  weight decimal(10, 2) NOT NULL DEFAULT 1.0,
  created_at timestamptz DEFAULT now(),
  UNIQUE (assessment_id, name)
);
CREATE INDEX IF NOT EXISTS idx_assessment_features_assessment_id 
  ON assessment_features(assessment_id);

-- Create review_feature_scores table
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
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_invitation_id 
  ON review_feature_scores(invitation_id);
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_feature_id 
  ON review_feature_scores(feature_id);

-- Optional: Add score tracking to review_feedback
ALTER TABLE review_feedback
  ADD COLUMN IF NOT EXISTS calculated_score decimal(10, 2),
  ADD COLUMN IF NOT EXISTS max_score decimal(10, 2);

