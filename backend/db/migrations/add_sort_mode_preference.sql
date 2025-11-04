-- Add sort mode preference to assessments
-- Tracks whether each assessment should use auto (score-based) or manual (drag-and-drop) sorting by default

ALTER TABLE assessments
  ADD COLUMN IF NOT EXISTS sort_mode text CHECK (sort_mode IN ('auto', 'manual')) DEFAULT 'auto';

CREATE INDEX IF NOT EXISTS idx_assessments_sort_mode ON assessments(sort_mode);


