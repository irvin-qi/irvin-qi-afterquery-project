# Scheduling Feature Plan - Cal.com Integration

## Overview
Add a "Scheduling" tab to the admin sidebar that allows admins to schedule meetings with candidates using Cal.com API and send scheduling emails.

## Goals
1. Add "Scheduling" navigation item to the left sidebar
2. Create a scheduling page where admins can:
   - Select candidates from existing invitations
   - View/create Cal.com booking links
   - Send scheduling emails to selected candidates
3. Integrate with Cal.com API for booking management
4. Store booking metadata in the database

## Architecture

### Frontend Components

#### 1. Sidebar Navigation
**File**: `frontend/components/layout/app-shell.tsx`
- Add "Scheduling" link to `NAV_LINKS` array
- Use `Calendar` icon from `lucide-react`
- Route: `/app/scheduling`

#### 2. Scheduling Page
**File**: `frontend/app/app/(admin)/scheduling/page.tsx`
- Main scheduling interface
- Candidate selection (multi-select from invitations)
- Cal.com booking link management
- Email sending interface

**Features**:
- Filter candidates by assessment
- Select multiple candidates
- Display Cal.com booking links
- Send scheduling emails with booking links
- View booking status

#### 3. API Client Functions
**File**: `frontend/lib/api.ts`
- `listCalComEventTypes()` - Get available event types
- `createCalComBooking(candidateEmail, eventTypeId, ...)` - Create booking
- `getCalComBooking(bookingId)` - Get booking details
- `sendSchedulingEmail(invitationIds, bookingLink, ...)` - Send emails

### Backend Implementation

#### 1. Database Schema
**New Migration**: `backend/db/migrations/add_cal_com_integration.sql`

```sql
-- Store Cal.com API configuration per organization
CREATE TABLE cal_com_configs (
    org_id UUID PRIMARY KEY REFERENCES orgs(id) ON DELETE CASCADE,
    api_key TEXT NOT NULL,
    api_url TEXT DEFAULT 'https://api.cal.com/v1',
    user_id TEXT, -- Cal.com user ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Store booking information
CREATE TABLE cal_com_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invitation_id UUID REFERENCES invitations(id) ON DELETE CASCADE,
    booking_id TEXT NOT NULL, -- Cal.com booking ID
    event_type_id TEXT, -- Cal.com event type ID
    booking_url TEXT, -- Public booking URL
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    status TEXT, -- 'pending', 'confirmed', 'cancelled'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(booking_id)
);

CREATE INDEX idx_cal_com_bookings_invitation_id ON cal_com_bookings(invitation_id);
CREATE INDEX idx_cal_com_bookings_booking_id ON cal_com_bookings(booking_id);
```

#### 2. Models
**File**: `backend/app/models.py`
- Add `CalComConfig` model
- Add `CalComBooking` model

#### 3. Cal.com Service
**File**: `backend/app/services/cal_com.py`
- `CalComService` class
- Methods:
  - `get_event_types()` - List available event types
  - `create_booking(...)` - Create a new booking
  - `get_booking(booking_id)` - Retrieve booking details
  - `cancel_booking(booking_id)` - Cancel a booking
  - `get_availability(...)` - Get available time slots

#### 4. API Routes
**File**: `backend/app/routes/scheduling.py`
- `GET /api/admin/scheduling/candidates` - List candidates available for scheduling
- `GET /api/admin/scheduling/cal-com/event-types` - Get Cal.com event types
- `POST /api/admin/scheduling/cal-com/bookings` - Create booking
- `GET /api/admin/scheduling/cal-com/bookings/{booking_id}` - Get booking
- `POST /api/admin/scheduling/send-emails` - Send scheduling emails

#### 5. Email Templates
**File**: `backend/app/services/email.py`
- Extend `EmailService` to support scheduling emails
- Template key: `scheduling_invitation`
- Include booking link, candidate name, meeting details

### Data Flow

#### Creating a Booking
1. Admin selects candidates from the scheduling page
2. Frontend calls `GET /api/admin/scheduling/cal-com/event-types`
3. Admin selects event type (or uses default)
4. Frontend calls `POST /api/admin/scheduling/cal-com/bookings` with:
   - `invitation_ids`: List of invitation IDs
   - `event_type_id`: Cal.com event type ID
   - `email`: Candidate email
   - `name`: Candidate name
5. Backend:
   - Creates booking via Cal.com API
   - Stores booking in `cal_com_bookings` table
   - Returns booking URL
6. Frontend displays booking URL(s)

#### Sending Scheduling Emails
1. Admin confirms booking and clicks "Send Emails"
2. Frontend calls `POST /api/admin/scheduling/send-emails` with:
   - `invitation_ids`: List of invitation IDs
   - `booking_url`: Cal.com booking URL
   - `subject`: Optional custom subject
   - `message`: Optional custom message
3. Backend:
   - Loads email template (or uses default)
   - Replaces template variables:
     - `{{candidate_name}}`
     - `{{booking_link}}`
     - `{{assessment_title}}`
     - `{{meeting_date}}` (if available)
   - Sends email via existing `ResendEmailService`
   - Records email event

### Cal.com API Integration Details

#### Authentication
- API Key stored in `cal_com_configs` table (encrypted at rest recommended)
- Environment variable: `CAL_COM_API_KEY` (fallback)
- Header: `Authorization: Bearer {api_key}`

#### Key Endpoints
1. **List Event Types**
   ```
   GET https://api.cal.com/v1/event-types
   ```

2. **Create Booking**
   ```
   POST https://api.cal.com/v1/bookings
   Body: {
     "eventTypeId": "...",
     "start": "2024-01-15T10:00:00Z",
     "end": "2024-01-15T10:30:00Z",
     "responses": {
       "email": "candidate@example.com",
       "name": "John Doe"
     },
     "timeZone": "America/New_York"
   }
   ```

3. **Get Booking**
   ```
   GET https://api.cal.com/v1/bookings/{booking_id}
   ```

4. **Cancel Booking**
   ```
   DELETE https://api.cal.com/v1/bookings/{booking_id}
   ```

### UI/UX Flow

#### Scheduling Page Layout
```
┌─────────────────────────────────────────────────┐
│  Scheduling                                      │
├─────────────────────────────────────────────────┤
│  Filter: [Assessment ▼] [Status ▼]             │
│                                                   │
│  ┌───────────────────────────────────────────┐  │
│  │  Candidates                                │  │
│  │  ┌──────────────────────────────────────┐ │  │
│  │  │ ☑ John Doe (john@example.com)        │ │  │
│  │  │   Assessment: Frontend Developer      │ │  │
│  │  │   Status: submitted                   │ │  │
│  │  └──────────────────────────────────────┘ │  │
│  │  ┌──────────────────────────────────────┐ │  │
│  │  │ ☐ Jane Smith (jane@example.com)      │ │  │
│  │  │   Assessment: Backend Developer       │ │  │
│  │  │   Status: submitted                   │ │  │
│  │  └──────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────┘  │
│                                                   │
│  Selected: 1 candidate                            │
│                                                   │
│  ┌───────────────────────────────────────────┐  │
│  │  Cal.com Configuration                    │  │
│  │  Event Type: [Interview ▼]                │  │
│  │  Duration: [30 minutes ▼]                 │  │
│  │  [Generate Booking Links]                 │  │
│  └───────────────────────────────────────────┘  │
│                                                   │
│  ┌───────────────────────────────────────────┐  │
│  │  Booking Links                             │  │
│  │  John Doe: https://cal.com/.../30min      │  │
│  └───────────────────────────────────────────┘  │
│                                                   │
│  ┌───────────────────────────────────────────┐  │
│  │  Email                                      │  │
│  │  Subject: [Meeting Invitation - ...]       │  │
│  │  [Preview Template] [Send Emails]          │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Configuration

#### Environment Variables
```bash
# Cal.com API Configuration
CAL_COM_API_KEY=your_api_key_here
CAL_COM_API_URL=https://api.cal.com/v1  # Optional, defaults to v1
```

#### Initial Setup
1. Admin navigates to Settings → Cal.com (future)
2. Enter Cal.com API key
3. System fetches and stores event types
4. Ready to use scheduling feature

### Email Template

#### Default Scheduling Email Template
**Subject**: `Meeting Invitation - {{assessment_title}}`

**Body**:
```
Hi {{candidate_name}},

Thank you for completing the {{assessment_title}} assessment. We'd like to schedule a follow-up meeting to discuss your submission.

Please book a time that works for you using the link below:

{{booking_link}}

We look forward to speaking with you!

Best regards,
{{org_name}}
```

### Error Handling

#### Common Scenarios
1. **Cal.com API Key Missing**
   - Show configuration prompt
   - Link to settings page

2. **Cal.com API Error**
   - Display error message
   - Allow retry
   - Log error for debugging

3. **Email Send Failure**
   - Show which emails failed
   - Allow individual retry
   - Log errors

4. **Booking Already Exists**
   - Check for existing booking
   - Offer to reuse or cancel/recreate

### Security Considerations

1. **API Key Storage**
   - Store encrypted in database
   - Never expose in frontend
   - Use environment variables as fallback

2. **Authorization**
   - Only admins can access scheduling
   - Validate org membership
   - Check invitation ownership

3. **Rate Limiting**
   - Respect Cal.com API rate limits
   - Implement request queuing if needed

### Testing Strategy

1. **Unit Tests**
   - Cal.com service methods
   - Email template rendering
   - Booking creation logic

2. **Integration Tests**
   - Cal.com API calls (use mock)
   - Email sending
   - Database operations

3. **E2E Tests**
   - Full booking flow
   - Email delivery
   - Error scenarios

### Future Enhancements

1. **Bulk Operations**
   - Select all candidates
   - Batch booking creation
   - Batch email sending

2. **Booking Management**
   - View all bookings
   - Cancel bookings
   - Reschedule bookings

3. **Calendar Integration**
   - Sync with Google Calendar
   - Show availability
   - Auto-suggest times

4. **Webhooks**
   - Listen to Cal.com webhooks
   - Update booking status
   - Send confirmation emails

5. **Settings Page**
   - Manage Cal.com configuration
   - Customize email templates
   - Set default event types

## Implementation Steps

### Phase 1: Foundation
1. ✅ Add sidebar navigation item
2. ✅ Create scheduling page route
3. ✅ Add database migration for Cal.com tables
4. ✅ Create models for CalComConfig and CalComBooking

### Phase 2: Backend Integration
5. ✅ Create Cal.com service
6. ✅ Create API routes
7. ✅ Add email template support
8. ✅ Test Cal.com API integration

### Phase 3: Frontend UI
9. ✅ Build candidate selection interface
10. ✅ Add Cal.com event type selector
11. ✅ Implement booking link generation
12. ✅ Create email sending interface

### Phase 4: Polish & Testing
13. ✅ Error handling
14. ✅ Loading states
15. ✅ Success feedback
16. ✅ Testing and bug fixes

## Files to Create/Modify

### New Files
- `frontend/app/app/(admin)/scheduling/page.tsx`
- `backend/app/services/cal_com.py`
- `backend/app/routes/scheduling.py`
- `backend/db/migrations/add_cal_com_integration.sql`

### Modified Files
- `frontend/components/layout/app-shell.tsx` (add navigation)
- `frontend/lib/api.ts` (add scheduling API functions)
- `backend/app/models.py` (add CalCom models)
- `backend/app/services/email.py` (add scheduling email support)
- `backend/app/schemas.py` (add scheduling schemas)

