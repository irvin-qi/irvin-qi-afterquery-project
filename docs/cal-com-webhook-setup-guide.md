# Cal.com Webhook Setup - Quick Guide

This guide will help you configure the Cal.com webhook to automatically update booking statuses when candidates confirm their bookings.

## Prerequisites

- Backend running on port 8000 (or your configured port)
- Cal.com account with API key configured
- ngrok installed (for local development)

## Step 1: Expose Your Backend (Local Development Only)

If you're testing locally, you need to expose your backend to the internet so Cal.com can send webhooks to it.

### Using ngrok:

1. **Start ngrok:**
   ```bash
   ngrok http 8000
   ```

2. **Copy your public URL:**
   - Look for a line like: `Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000`
   - Copy the HTTPS URL: `https://abc123.ngrok-free.app` (yours will be different)

3. **Keep ngrok running** - Don't close this terminal window while testing

## Step 2: Configure Webhook in Cal.com

1. **Go to Cal.com Settings → Webhooks**
   - Navigate to your Cal.com account
   - Click on your profile → Settings → Webhooks

2. **Edit your existing webhook** (or create a new one):
   - Click the **Edit** button on your webhook

3. **Update the Webhook URL:**
   - **For local development:** `https://your-ngrok-url.ngrok-free.app/api/admin/scheduling/cal-com/webhook`
     - Replace `your-ngrok-url.ngrok-free.app` with your actual ngrok URL
   - **For production:** `https://your-domain.com/api/admin/scheduling/cal-com/webhook`
     - Replace `your-domain.com` with your production domain

4. **Select Required Events:**
   Click on these events to select them (they should be highlighted/checked):
   - ✅ **Booking Created** - Triggers when a booking link is created
   - ✅ **Booking Confirmed** - ⭐ **MOST IMPORTANT** - Triggers when candidate confirms booking
   - ✅ **Booking Cancelled** - Triggers when a booking is cancelled
   - ✅ **Booking Rescheduled** - Triggers when booking time changes

5. **Enable the Webhook:**
   - Toggle the switch to **ON** (it should be green/enabled)
   - If it's off (gray), Cal.com won't send any webhooks

6. **Save:**
   - Click **Save** or **Update** button

## Step 3: Test the Integration

1. **Create a test booking:**
   - Go to your scheduling page
   - Select a candidate
   - Create a booking link
   - Send the booking link to yourself (or use a test email)

2. **Confirm the booking:**
   - Open the booking link in Cal.com
   - Complete the booking (select a time and confirm)

3. **Check your backend logs:**
   ```bash
   docker-compose -f docker-compose.dev.yml logs backend | grep -i webhook
   ```
   You should see:
   ```
   Received Cal.com webhook: {'trigger': 'BOOKING_CONFIRMED', 'data': {...}}
   Updated booking ... status to confirmed
   ```

4. **Check your frontend:**
   - Go to the scheduling page
   - The booking should now show as "Confirmed" (green badge)
   - Calendar dots should turn green

## Troubleshooting

### Webhook not receiving events:

1. **Check if webhook is enabled:**
   - In Cal.com, make sure the toggle switch is ON (green)

2. **Verify webhook URL:**
   - Test the URL manually: `curl https://your-url.ngrok-free.app/api/admin/scheduling/cal-com/webhook`
   - Should return a response (even if it's an error about missing data)

3. **Check ngrok is running:**
   - If using ngrok, make sure it's still running
   - If you restarted ngrok, you got a new URL - update the webhook

4. **Check backend logs:**
   ```bash
   docker-compose -f docker-compose.dev.yml logs backend --tail=50
   ```

### Webhook receives events but status doesn't update:

1. **Check webhook payload format:**
   - Look at the backend logs for the webhook payload
   - The code expects either:
     - `booking_data.id` or `booking_data.bookingId` (Cal.com booking ID)
     - `booking_data.attendees[0].email` (candidate email)

2. **Verify booking exists in database:**
   - The webhook tries to match bookings by:
     1. Cal.com booking ID
     2. Candidate email (matches to invitation)

3. **Check if booking link was created:**
   - Make sure you created a booking link in your app first
   - The webhook needs to match to an existing booking record

### Status shows as "Pending" even after confirmation:

1. **Use manual sync:**
   - Click the refresh/sync button in the calendar header
   - This will fetch latest statuses from Cal.com API

2. **Check webhook is configured correctly:**
   - Make sure "Booking Confirmed" event is selected
   - Make sure webhook is enabled

3. **Wait for polling:**
   - The frontend polls every 60 seconds automatically
   - Status will update on next poll

## Webhook Payload Format

The webhook endpoint expects Cal.com webhooks in this format:

```json
{
  "trigger": "BOOKING_CONFIRMED",
  "data": {
    "id": "123456",
    "bookingId": "123456",
    "startTime": "2024-01-15T10:00:00Z",
    "endTime": "2024-01-15T10:30:00Z",
    "attendees": [
      {
        "email": "candidate@example.com"
      }
    ],
    "responses": {
      "email": "candidate@example.com"
    }
  }
}
```

## Next Steps

Once the webhook is configured:
- ✅ Bookings will automatically update to "Confirmed" when candidates book
- ✅ Calendar will show green indicators for confirmed bookings
- ✅ Status badges will update in real-time (within 60 seconds)
- ✅ You can still manually sync using the sync button if needed

## Support

If you encounter issues:
1. Check the backend logs for webhook errors
2. Verify the webhook URL is accessible
3. Test with a simple booking confirmation
4. Check that the webhook is enabled in Cal.com

