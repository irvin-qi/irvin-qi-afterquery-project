-- Remove display_order column from assessment_features table
-- Features will be ordered by weight (descending) instead
ALTER TABLE assessment_features
  DROP COLUMN IF EXISTS display_order;



