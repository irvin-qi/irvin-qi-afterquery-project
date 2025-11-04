-- Migration: Add video_url column to submissions table
-- Run this migration to add support for video submissions

ALTER TABLE submissions
ADD COLUMN IF NOT EXISTS video_url TEXT;

-- Add comment for documentation
COMMENT ON COLUMN submissions.video_url IS 'URL to candidate submission video (YouTube, Vimeo, or direct video link)';



