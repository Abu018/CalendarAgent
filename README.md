# 🗓️ Google Calendar Scheduling Workflow 🚀

## 1. 🏗️ Initialization and Setup
- **🔧 Environment Setup**:
  - 📁 Load `.env` file
  - 🔑 Set OpenAI API key
  - 📝 Configure logging system

## 2. 📝 Data Model Definitions
- 🏷️ Pydantic models for:
  - 📅 `CalendarEventDetails`: Title, description, time, attendees
  - 📩 `CalendarEventResponse`: API response structure
  - ⏱️ `TimeSlot`: Time interval container
  - 📊 `AvailableSlotsResponse`: Available slots + selection info

## 3. 🔐 Google Calendar Service
### 🔑 Authentication:
  - 🔄 OAuth2 flow with `credentials.json`
  - 💾 Store token in `token.json`
  - ✅ Verify credential scopes

### ⚙️ Core Functionality:
1. **🔍 Find Available Slots**:
   - 📆 Query busy periods
   - 🕙 Generate 10 AM-5 PM weekday slots
   - ⏭️ Return earliest slot by default

2. **➕ Create Event**:
   - 🎯 Create event with Google Meet link
   - 🔔 Set reminders (24h email + 30m popup)
   - 🔄 Retry logic for notifications
   - 📧 Verify attendee notifications

## 4. 🤖 CrewAI Agent System
### 👥 Agent Roles:
1. **👔 Senior Calendar Scheduler**:
   - 🛠️ Primary scheduling agent
   - 🔍 Finds slots + creates events

2. **📋 Meeting Coordinator**:
   - 📢 Handles communication
   - 📝 Manages preparation

3. **🔍 Quality Assurance**:
   - ✅ Verifies all details
   - 🕵️‍♂️ Double-checks everything

### 📋 Task Flow:
1. `find_slots_task`: 🔍 Find 10 AM-5 PM slots
2. `process_slots_task`: ✨ Prepare slot data
3. `create_event_task`: ➕ Create calendar event
4. `verify_details_task`: ✅ Validate meeting details
5. `summarize_task`: 📄 Generate human-readable summary

## 5. 🚀 Main Execution Flow
1. 📥 Receive meeting parameters:
   - 👥 Attendees
   - 🏷️ Title
   - ⏳ Duration
   - 📝 Description (optional)
   - 🌐 Timezone

2. 🤖 CrewAI orchestration:
   - 🔄 Sequential task execution
   - 📤 Context passing between tasks

3. 📤 Final output:
   - ✅ Success/error status
   - 📊 Detailed result object
   - 💬 Confirmation message

## 🛡️ Error Handling
- 🚨 Comprehensive error handling:
  - 🔐 Authentication failures
  - 🔄 API call retries
  - ✍️ Input validation
  - 📧 Notification verification

## 🔑 Key Constraints
- ⏰ Only 10 AM-5 PM scheduling
- 🚫 Skips weekends (🗓️ Saturday/Sunday)
- 🔐 Requires Google OAuth credentials
- 🧠 Uses GPT-4-turbo LLM

## 🏃 Example Workflow Execution
1. 👤 User provides meeting details
2. 🤖 System finds earliest slot (10 AM-5 PM, weekdays)
3. ➕ Creates event with Meet link
4. 📧 Sends attendee notifications
5. ✅ Verifies all details
6. 📄 Returns meeting summary

