import sys
import datetime
from mcp.server.fastmcp import FastMCP

# Create a FastMCP server named "StudyBuddy MCP Server"
mcp = FastMCP("StudyBuddy MCP Server")

# Mock database for calendar events and added study blocks
CALENDAR_EVENTS = [
    {"title": "CS 101 Midterm Exam", "date": "2026-07-15", "type": "Exam"},
    {"title": "Math 201 Homework 3 Due", "date": "2026-07-08", "type": "Deadline"},
    {"title": "CS 101 Programming Project 1 Due", "date": "2026-07-12", "type": "Deadline"},
    {"title": "Physics 102 Lab Report Due", "date": "2026-07-10", "type": "Deadline"},
    {"title": "Math 201 Final Exam", "date": "2026-07-28", "type": "Exam"},
]

ADDED_STUDY_BLOCKS = []

@mcp.tool()
def get_calendar_events() -> str:
    """Retrieve existing academic calendar events, deadlines, and exam dates."""
    events_str = "Current Academic Calendar Events:\n"
    for event in CALENDAR_EVENTS:
        events_str += f"- [{event['type']}] {event['title']} on {event['date']}\n"
    return events_str

@mcp.tool()
def add_study_block(subject: str, date: str, duration_hours: float) -> str:
    """Schedule and add a new study block for a specific subject on a given date.
    
    Args:
        subject: The academic subject or topic to study.
        date: The date for the study block (YYYY-MM-DD).
        duration_hours: Number of hours to study.
    """
    block = {
        "subject": subject,
        "date": date,
        "duration_hours": duration_hours,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    ADDED_STUDY_BLOCKS.append(block)
    print(f"Added study block: {block}", file=sys.stderr)
    return f"Successfully scheduled {duration_hours} hours study block for '{subject}' on {date}."

@mcp.tool()
def get_study_tips(subject: str) -> str:
    """Retrieve optimal study and prep tips tailored to a specific subject.
    
    Args:
        subject: The subject name (e.g. math, computer science, physics, history, biology, chemistry).
    """
    subj = subject.lower()
    if "computer" in subj or "cs" in subj or "programming" in subj:
        return (
            "Study tips for Computer Science:\n"
            "1. Practice active coding. Write small programs to test concepts instead of just reading code.\n"
            "2. Trace code by hand on paper to understand flow and trace logic errors.\n"
            "3. Use spacing (Pomodoro technique) to avoid debug fatigue. 25m focus, 5m break."
        )
    elif "math" in subj or "algebra" in subj or "calculus" in subj:
        return (
            "Study tips for Mathematics:\n"
            "1. Solve problems without looking at the solutions first. Active recall is critical.\n"
            "2. Focus on understanding the derivation of formulas, not just memorizing them.\n"
            "3. Do practice exams under timed conditions to improve speed and manage anxiety."
        )
    elif "physics" in subj or "chem" in subj or "science" in subj:
        return (
            "Study tips for Natural Sciences:\n"
            "1. Draw free-body diagrams and visualize systems before writing equations.\n"
            "2. Map physical concepts to mathematical models; focus on units and dimensional analysis.\n"
            "3. Review laboratory experiments; they often illustrate the core theory."
        )
    else:
        return (
            f"General study tips for {subject}:\n"
            "1. Use active recall (flashcards, summarizing without notes).\n"
            "2. Use spaced repetition (review material at increasing intervals).\n"
            "3. Teach the concepts to someone else (Feynman technique)."
        )

@mcp.tool()
def calculate_countdown(exam_date: str) -> str:
    """Calculate the remaining time (days and weeks) until a specific exam date.
    
    Args:
        exam_date: The date of the exam (YYYY-MM-DD).
    """
    try:
        target = datetime.datetime.strptime(exam_date, "%Y-%m-%d").date()
        today = datetime.date.today()
        delta = target - today
        if delta.days < 0:
            return f"The date {exam_date} has already passed by {-delta.days} days."
        elif delta.days == 0:
            return f"The exam is TODAY!"
        else:
            weeks = delta.days // 7
            days = delta.days % 7
            return f"There are {delta.days} days remaining until {exam_date} (approx. {weeks} weeks and {days} days)."
    except Exception as e:
        return f"Error parsing date '{exam_date}': {str(e)}. Use format YYYY-MM-DD."

if __name__ == "__main__":
    mcp.run()
