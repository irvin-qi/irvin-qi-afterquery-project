# Cal.com Setup Guide

This guide will walk you through setting up Cal.com integration for the scheduling feature.

## Prerequisites

- A Cal.com account (sign up at [cal.com](https://cal.com) if you don't have one)
- Admin access to your Afterquery application

## Step 1: Get Your Cal.com API Key

1. **Log in to Cal.com**
   - Go to [cal.com](https://cal.com) and sign in to your account

2. **Navigate to Settings**
   - Click on your profile picture in the top right
   - Select **Settings** from the dropdown menu

3. **Go to Developer Settings**
   - In the left sidebar, click on **Developer** (or navigate to Settings → Developer)
   - If you don't see Developer settings, you may need to enable developer mode first

4. **Create an API Key**
   - Scroll down to the **API Keys** section
   - Click **Create API Key** or **Generate New Key**
   - Give it a descriptive name (e.g., "Afterquery Integration")
   - Copy the API key immediately - you won't be able to see it again!
   - **Note**: The API key will look something like: `cal_live_xxxxxxxxxxxxx`

## Step 2: Create Event Types in Cal.com

Event types define the different types of meetings you can schedule (e.g., "30-minute Interview", "15-minute Quick Chat").

1. **Go to Event Types**
   - In Cal.com, navigate to **Event Types** in the left sidebar
   - Or go to Settings → Event Types

2. **Create Your First Event Type**
   - Click **+ New Event Type**
   - Fill in the details:
     - **Title**: e.g., "Interview" or "Follow-up Call"
     - **Duration**: Choose how long the meeting should be (e.g., 30 minutes)
     - **Description**: Optional description of what the meeting is about
   - Click **Continue** and complete the setup
   - **Note the Event Type ID**: You'll need this later (it's usually a number, visible in the URL or settings)

3. **Create Multiple Event Types (Optional)**
   - You can create multiple event types for different meeting lengths
   - Common examples:
     - "15-minute Quick Chat" (15 minutes)
     - "30-minute Interview" (30 minutes)
     - "60-minute Technical Deep Dive" (60 minutes)

## Step 3: Configure Cal.com in Your Application

### Option A: Environment Variable (Recommended for Development)

1. **Add to your `.env` file**
   ```bash
   CAL_COM_API_KEY=cal_live_xxxxxxxxxxxxx
   CAL_COM_API_URL=https://api.cal.com/v1  # Optional, defaults to v1
   ```

2. **Restart your backend server**
   - The backend will automatically pick up the environment variable

### Option B: Database Configuration (Recommended for Production)

1. **Run the migration** (if you haven't already):
   ```bash
   # Apply the Cal.com migration
   psql -d your_database -f backend/db/migrations/add_cal_com_integration.sql
   ```

2. **Insert configuration** (you can do this through your database admin tool or a script):
   ```sql
   INSERT INTO cal_com_configs (org_id, api_key, api_url)
   VALUES (
     'your-org-id-here',
     'cal_live_xxxxxxxxxxxxx',
     'https://api.cal.com/v1'
   );
   ```

   **Security Note**: In production, consider encrypting the API key before storing it in the database.

## Step 4: Set Up Cal.com Webhooks (Optional but Recommended)

To automatically receive booking status updates when candidates confirm bookings:

### For Local Development (using ngrok):

1. **Start ngrok to expose your backend:**
   ```bash
   # Make sure your backend is running on port 8000
   ngrok http 8000
   ```
   
2. **Copy your ngrok URL:**
   - You'll see something like: `https://abc123.ngrok-free.app`
   - Copy this URL (without the trailing slash)

3. **Update the webhook in Cal.com:**
   - Click **Edit** on your existing webhook (or create a new one)
   - **Webhook URL:** Enter: `https://your-ngrok-url.ngrok-free.app/api/admin/scheduling/cal-com/webhook`
     - Replace `your-ngrok-url.ngrok-free.app` with your actual ngrok URL
   - **Select Events:** Click on these events (they should have a checkmark/be highlighted):
     - ✅ **Booking Created** - When a booking is first created
     - ✅ **Booking Confirmed** - ⭐ **CRITICAL** - When a candidate confirms their booking
     - ✅ **Booking Cancelled** - When a booking is cancelled
     - ✅ **Booking Rescheduled** - When a booking time is changed
   - **Enable the webhook:** Toggle the switch to **ON** (green/enabled)
   - Click **Save** or **Update**

### For Production:

1. **Use your production domain:**
   - Webhook URL: `https://your-production-domain.com/api/admin/scheduling/cal-com/webhook`
   - Replace `your-production-domain.com` with your actual domain

2. **Select the same events** as listed above

3. **Enable the webhook**

### Important Notes:

- **The webhook must be enabled** (toggle switch ON) for it to work
- **"Booking Confirmed" is the most important event** - this is what updates your calendar when candidates confirm
- If you don't set up webhooks, you can still manually sync booking statuses using the "Sync" button (refresh icon) in the scheduling page
- The system will also automatically poll for updates every 60 seconds
- **Keep ngrok running** while testing locally - if you restart ngrok, you'll get a new URL and need to update the webhook

## Step 5: Verify the Setup

1. **Start your application**
   - Make sure both frontend and backend are running

2. **Navigate to Scheduling**
   - Go to the **Scheduling** tab in the left sidebar
   - You should see the scheduling interface

3. **Check Event Types**
   - The "Event Type" dropdown should populate with your Cal.com event types
   - If you see "No event types found", check:
     - Your API key is correct
     - Your Cal.com account has event types created
     - The backend server has restarted after adding the environment variable

## Step 6: Test the Integration

1. **Select a Candidate**
   - In the Scheduling page, select one or more candidates from the list

2. **Choose an Event Type**
   - Select an event type from the dropdown

3. **Create a Booking**
   - Click **Create Booking**
   - This will create a booking link in Cal.com
   - You should see a success message with the booking URL

4. **Send Emails**
   - After creating a booking, click **Send Emails**
   - This will send scheduling emails to the selected candidates with the booking link

## Troubleshooting

### Issue: "Cal.com API key not configured"

**Solution**: 
- Make sure you've added `CAL_COM_API_KEY` to your `.env` file
- Restart your backend server after adding the environment variable
- Check that the API key is correct (no extra spaces or quotes)

### Issue: "No event types found"

**Solutions**:
1. Verify you have created event types in Cal.com
2. Check that your API key has the correct permissions
3. Try refreshing the page or checking the browser console for errors
4. Verify the API key is valid by testing it directly:
   ```bash
   curl -H "Authorization: Bearer YOUR_API_KEY" https://api.cal.com/v1/event-types
   ```

### Issue: "Failed to create booking"

**Solutions**:
1. Verify the event type ID is correct
2. Check that the event type is not hidden or deleted
3. Ensure your Cal.com account has the necessary permissions
4. Check the backend logs for detailed error messages

### Issue: Emails not sending

**Solutions**:
1. Verify your email service (Resend/Mailtrap) is configured correctly
2. Check the backend logs for email sending errors
3. Verify candidate email addresses are valid

## API Key Security Best Practices

1. **Never commit API keys to version control**
   - Use `.env` files (which should be in `.gitignore`)
   - Use environment variables in production

2. **Rotate keys periodically**
   - Generate new API keys in Cal.com
   - Update your configuration
   - Delete old keys

3. **Use different keys for different environments**
   - Separate keys for development, staging, and production

4. **Limit key permissions**
   - Only grant the minimum permissions needed
   - Use API keys specific to this integration

## Cal.com API Documentation

For more information about the Cal.com API, refer to:
- [Cal.com API Documentation](https://cal.com/docs/api-reference/v1)
- [Cal.com Developer Docs](https://cal.com/docs/developer)

## Next Steps

After setup is complete, you can:
- Schedule meetings with candidates directly from the application
- Send booking links via email
- View all scheduled meetings in the calendar view
- Track booking status and manage cancellations

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review the backend logs for detailed error messages
3. Verify your Cal.com account settings
4. Consult the Cal.com API documentation

