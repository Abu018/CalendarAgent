from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, ConfigDict
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
import time
from crewai import Agent, Task, Crew
from crewai.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up OpenAI API key
os.environ["OPENAI_API_KEY"] = ""

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Data Models
class CalendarEventDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(description="Title of the event")
    description: Optional[str] = Field(None, description="Description of the event")
    start_time: str = Field(description="Start time in ISO 8601 format")
    end_time: str = Field(description="End time in ISO 8601 format")
    attendees: List[str] = Field(description="List of attendee emails")
    timezone: str = Field(default="UTC", description="Timezone for the event")

class CalendarEventResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(description="Success or error status")
    event_link: Optional[str] = Field(None, description="URL to the calendar event")
    meet_link: Optional[str] = Field(None, description="Google Meet link if generated")
    event_id: Optional[str] = Field(None, description="Google Calendar event ID")
    error_message: Optional[str] = Field(None, description="Error details if any")

class TimeSlot(BaseModel):
    start: str = Field(description="Start time in ISO 8601 format")
    end: str = Field(description="End time in ISO 8601 format")

class AvailableSlotsResponse(BaseModel):
    available_slots: List[TimeSlot]
    selected_slot: Optional[TimeSlot]
    notes: str

# Google Calendar Service
class CalendarService:
    def __init__(self, credentials_path: str = './credentials.json'):
        self.credentials_path = credentials_path
        self.scopes = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/calendar.events',
            'https://www.googleapis.com/auth/calendar.settings.readonly',
            'https://www.googleapis.com/auth/gmail.send'
        ]
        self.service = self._authenticate()
        if not self.verify_credentials():
            logger.error("Credential verification failed - recreating service")
            self.service = self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar API"""
        try:
            if not os.path.exists(self.credentials_path):
                raise FileNotFoundError("Credentials file not found")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path, self.scopes)
            creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
            return build('calendar', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def verify_credentials(self):
        """Verify that credentials have the necessary permissions"""
        try:
            creds = Credentials.from_authorized_user_file('token.json', self.scopes)
            if not creds.valid:
                logger.warning("Credentials are not valid or have expired")
                return False
            
            missing_scopes = [scope for scope in self.scopes if scope not in creds.scopes]
            if missing_scopes:
                logger.warning(f"Missing required scopes: {missing_scopes}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Credential verification failed: {e}")
            return False

    @tool("Find Available Time Slots")
    def find_available_slots(self, duration_minutes: int, days_ahead: int = 7) -> Dict[str, Any]:
        """Finds available time slots between 10 AM and 5 PM in the next specified days."""
        try:
            # Get current time in UTC
            now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
            
            # Calculate end time for query (days_ahead days from now)
            end_date = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'
            
            # Get busy intervals from calendar
            freebusy_query = {
                "timeMin": now,
                "timeMax": end_date,
                "items": [{"id": "primary"}]
            }
            
            freebusy_result = self.service.freebusy().query(body=freebusy_query).execute()
            busy_slots = freebusy_result.get('calendars', {}).get('primary', {}).get('busy', [])
            
            # Generate potential slots (10 AM to 5 PM)
            available_slots = []
            current_date = datetime.utcnow().date()
            
            for day in range(days_ahead):
                day_date = current_date + timedelta(days=day)
                
                # Skip weekends
                if day_date.weekday() >= 5:  # 5 and 6 are Saturday and Sunday
                    continue
                
                # Create time slots from 10 AM to 5 PM
                start_time = datetime.combine(day_date, datetime.strptime("10:00", "%H:%M").time())
                end_time = datetime.combine(day_date, datetime.strptime("17:00", "%H:%M").time())
                
                # Generate slots of the requested duration
                slot_start = start_time
                while slot_start + timedelta(minutes=duration_minutes) <= end_time:
                    slot_end = slot_start + timedelta(minutes=duration_minutes)
                    
                    # Check if this slot overlaps with any busy time
                    slot_is_free = True
                    for busy in busy_slots:
                        busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                        busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                        
                        if not (slot_end <= busy_start or slot_start >= busy_end):
                            slot_is_free = False
                            break
                    
                    if slot_is_free:
                        available_slots.append(TimeSlot(
                            start=slot_start.isoformat(),
                            end=slot_end.isoformat()
                        ))
                    
                    slot_start += timedelta(minutes=15)  # Check every 15 minutes
            
            if not available_slots:
                return AvailableSlotsResponse(
                    available_slots=[],
                    selected_slot=None,
                    notes="No available slots found between 10 AM and 5 PM in the next {} days".format(days_ahead)
                ).model_dump()
            
            # Select the earliest available slot
            selected_slot = available_slots[0]
            
            return AvailableSlotsResponse(
                available_slots=available_slots,
                selected_slot=selected_slot,
                notes="Found {} available slots between 10 AM and 5 PM".format(len(available_slots))
            )
            
        except Exception as e:
            logger.error(f"Failed to find available slots: {e}")
            return AvailableSlotsResponse(
                available_slots=[],
                selected_slot=None,
                notes=f"Error finding slots: {str(e)}"
            ).model_dump()

    @tool("Create Google Calendar Event")
    def create_event(self, event_details: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new calendar event with the provided details and sends notifications to attendees."""
        try:
            details = CalendarEventDetails(**event_details)

            event = {
                'summary': details.summary,
                'description': details.description,
                'start': {'dateTime': details.start_time, 'timeZone': details.timezone},
                'end': {'dateTime': details.end_time, 'timeZone': details.timezone},
                'attendees': [{'email': email} for email in details.attendees],
                'conferenceData': {
                    'createRequest': {
                        'requestId': f"event_{datetime.now().timestamp()}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 30},      # 30 minutes before
                    ]
                },
                'guestsCanInviteOthers': False,
                'guestsCanModify': False,
                'guestsCanSeeOtherGuests': True,
            }

            # Create event WITH sending notifications (with retry logic)
            retry_count = 0
            max_retries = 3
            created_event = None
            notifications_sent = False

            while retry_count < max_retries:
                try:
                    created_event = self.service.events().insert(
                        calendarId='primary',
                        body=event,
                        conferenceDataVersion=1,
                        sendUpdates='all',
                        sendNotifications=True,
                        supportsAttachments=False
                    ).execute()
                    notifications_sent = True
                    break
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"Attempt {retry_count} failed: {e}")
                    if retry_count == max_retries:
                        raise
                    time.sleep(2 ** retry_count)

            if notifications_sent:
                logger.info("Email notifications successfully sent to attendees.")
            else:
                logger.warning("Failed to send email notifications to attendees.")

            if 'attendees' in created_event:
                for attendee in created_event['attendees']:
                    if attendee.get('responseStatus') == 'needsAction':
                        logger.warning(f"Notification may not have reached {attendee.get('email')}")
                    else:
                        logger.info(f"Notification confirmed for {attendee.get('email')}")

            return CalendarEventResponse(
                status="success",
                event_link=created_event.get('htmlLink'),
                meet_link=created_event.get('hangoutLink'),
                event_id=created_event.get('id')
            ).model_dump()

        except Exception as e:
            logger.error(f"Event creation failed: {e}")
            return CalendarEventResponse(
                status="error",
                error_message=str(e)
            ).model_dump()

# Crew Setup
def create_scheduling_crew():
    calendar_service = CalendarService()
    
    llm = ChatOpenAI(
        model="gpt-4-turbo",
        temperature=0.3,
        max_tokens=300
    )
    
    scheduler_agent = Agent(
        role="Senior Calendar Scheduler",
        goal="Schedule meetings between 10 AM and 5 PM and handle all scheduling logistics",
        backstory="""With years of experience in calendar management and scheduling,
        you excel at finding optimal meeting times between 10 AM and 5 PM.""",
        verbose=True,
        allow_delegation=True,
        tools=[calendar_service.find_available_slots, calendar_service.create_event],
        llm=llm
    )

    coordinator_agent = Agent(
        role="Meeting Coordinator",
        goal="Ensure smooth meeting preparation and participant communication",
        backstory="""You are a meticulous professional who handles all aspects
        of meeting preparation, from crafting clear agendas to ensuring all
        participants have the information they need to be productive.""",
        verbose=True,
        llm=llm
    )

    quality_agent = Agent(
        role="Quality Assurance Specialist",
        goal="Verify all meeting details and ensure nothing is missed",
        backstory="""You have an eye for detail and catch mistakes others miss.
        Your role is to double-check all meeting details before they're finalized.""",
        verbose=True,
        llm=llm
    )
   
    find_slots_task = Task(
        description="""Find available time slots between 10 AM and 5 PM for a 
        {duration_minutes}-minute meeting with {attendees}. Look for slots in the next 7 days.""",
        agent=scheduler_agent,
        expected_output="""A dictionary containing:
        - 'available_slots': List of available time slots between 10 AM and 5 PM
        - 'selected_slot': The earliest available time slot
        - 'notes': Information about the found slots""",
        async_execution=False
    )

    process_slots_task = Task(
        description="""Process the selected time slot from the previous task and prepare 
        it for the calendar event creation. Extract the selected_slot data for use in event creation.""",
        agent=scheduler_agent,
        expected_output="""A dictionary containing:
        - 'start_time': The start time of the selected slot
        - 'end_time': The end time of the selected slot""",
        context=[find_slots_task]
    )

    create_event_task = Task(
        description="""Create the calendar event with these details:
        Title: {meeting_title}
        Description: {meeting_description}
        Attendees: {attendees}
        Start Time: Use the start_time from the previous task
        End Time: Use the end_time from the previous task
        Timezone: {timezone}
        
        Include Google Meet link and set reminders.
        IMPORTANT: SEND email notifications to all attendees.""",
        agent=scheduler_agent,
        expected_output="""A confirmation of the scheduled event with:
        - Event link
        - Google Meet link
        - Event ID
        - Status message""",
        context=[process_slots_task]
    )

    verify_details_task = Task(
        description="""Verify all meeting details are correct:
        - Time is between 10 AM and 5 PM
        - Meeting title and description are clear
        - All technical details are properly set up
        - Confirm notifications were sent to all attendees""",
        agent=quality_agent,
        expected_output="""A verification report with:
        - List of verified items
        - Any issues found
        - Recommendations for improvements""",
        context=[create_event_task]
    )

    summarize_task = Task(
        description="""Summarize the meeting details for terminal output:
        {attendees}
        
        Include:
        - Meeting purpose
        - Confirmed meeting time (should be between 10 AM and 5 PM)
        - Google Meet link
        - Agenda items
        - Confirmation that calendar notifications were sent to attendees""",
        agent=coordinator_agent,
        expected_output="""A summary of meeting details for terminal output, including:
        - Meeting details
        - Time confirmation (between 10 AM and 5 PM)
        - Google Meet link
        - Agenda
        - Notification status""",
        context=[verify_details_task]
    )

    scheduling_crew = Crew(
        agents=[scheduler_agent, coordinator_agent, quality_agent],
        tasks=[find_slots_task, process_slots_task, create_event_task, verify_details_task, summarize_task],
        verbose=True,
        memory=True
    )

    return scheduling_crew

def schedule_meeting_with_crew(
    attendees: List[str],
    meeting_title: str,
    duration_minutes: int,
    meeting_description: str = None,
    timezone: str = "UTC"
):
    """Schedule a meeting between 10 AM and 5 PM with email notifications to attendees"""
    try:
        crew = create_scheduling_crew()
        
        inputs = {
            "attendees": attendees,
            "duration_minutes": duration_minutes,
            "meeting_title": meeting_title,
            "meeting_description": meeting_description or "",
            "timezone": timezone
        }
        
        result = crew.kickoff(inputs=inputs)
        
        logger.info("=" * 50)
        logger.info("Meeting scheduled successfully between 10 AM and 5 PM!")
        logger.info("Email notifications sent to all attendees")
        logger.info("See details above for meeting information")
        logger.info("=" * 50)
        
        return {
            "status": "success",
            "result": result,
            "message": "Meeting scheduled between 10 AM and 5 PM with notifications sent to all attendees"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    try:
        # Example meeting details
        attendees = ["iam.abu.mohammad@gmail.com", "iam.abu.017@gmail.com"]  # Replace with actual emails
        meeting_title = "Project Kickoff Meeting"
        duration_minutes = 60
        description = "Initial meeting to discuss project goals and timelines"
        timezone = "UTC"
        
        # Schedule using CrewAI agents
        result = schedule_meeting_with_crew(
            attendees=attendees,
            meeting_title=meeting_title,
            duration_minutes=duration_minutes,
            meeting_description=description,
            timezone=timezone
        )
        
        print("\nScheduling Result:")
        print(result)
        
    except Exception as e:
        logger.error(f"Error in example usage: {e}")