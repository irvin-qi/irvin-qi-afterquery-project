-- Create cal_com_configs table for storing Cal.com API configuration per organization
CREATE TABLE IF NOT EXISTS cal_com_configs (
    org_id UUID PRIMARY KEY REFERENCES orgs(id) ON DELETE CASCADE,
    api_key TEXT NOT NULL,
    api_url TEXT DEFAULT 'https://api.cal.com/v1',
    user_id TEXT, -- Cal.com user ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create cal_com_bookings table for storing booking information
CREATE TABLE IF NOT EXISTS cal_com_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invitation_id UUID REFERENCES invitations(id) ON DELETE CASCADE,
    booking_id TEXT NOT NULL, -- Cal.com booking ID
    event_type_id TEXT, -- Cal.com event type ID
    booking_url TEXT, -- Public booking URL
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    status TEXT, -- 'pending', 'confirmed', 'cancelled'
    title TEXT, -- Meeting title
    description TEXT, -- Meeting description
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(booking_id)
);

CREATE INDEX IF NOT EXISTS idx_cal_com_bookings_invitation_id ON cal_com_bookings(invitation_id);
CREATE INDEX IF NOT EXISTS idx_cal_com_bookings_booking_id ON cal_com_bookings(booking_id);
CREATE INDEX IF NOT EXISTS idx_cal_com_bookings_start_time ON cal_com_bookings(start_time);

