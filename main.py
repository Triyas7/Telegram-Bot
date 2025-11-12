import os
from dotenv import load_dotenv
import logging
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from typing import Dict, List


# Load variables from .env file
load_dotenv()
# Access the token from environment variables
TOKEN = os.getenv("TELEGRAM_API_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_API_TOKEN is not set in the environment variables.")

# Set up basic logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Configuration & State ---
# In-memory storage for user tasks (not persistent across restarts)
user_tasks: Dict[int, List[str]] = {}

# --- Utility Functions ---

def get_task_path(user_id: int) -> str:
    """Helper function to get the storage path (used for future database integration)."""
    # For now, we return the user_id key for the in-memory dict
    return str(user_id)

def get_motivational_quote() -> str:
    """Returns a random motivational quote."""
    quotes = [
        "The mind is not a vessel to be filled, but a fire to be kindled. - Plutarch",
        "The beautiful thing about learning is that no one can take it away from you. - B.B. King",
        "The only way to do great work is to love what you do. - Steve Jobs",
        "Strive for progress, not perfection.",
        "Today's actions are tomorrow's results.",
    ]
    return random.choice(quotes)

# --- Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a greeting and intro to the study features."""
    user = update.effective_user
    await update.message.reply_html(
        f"Welcome back, {user.mention_html()}! 🦉\n\n"
        "I'm your Study Helper Bot. Here are my commands:\n"
        "📚 /tasks_add [task description] - Add a new assignment/task.\n"
        "📝 /tasks_list - See all your current tasks.\n"
        "✅ /tasks_done [number] - Mark a task as complete.\n"
        "⏱️ /pomodoro [minutes] - Start a focus timer (e.g., /pomodoro 25).\n"
        "💡 /quote - Get a quick burst of motivation.\n"
    )

# --- Pomodoro Timer Functionality ---

async def alarm_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback function for the job_queue when the timer is up."""
    job = context.job
    # The chat_id and study type are stored in the job's context.
    await context.bot.send_message(
        job.chat_id, 
        text=f"**DING DING!** Your {job.data['type']} timer is finished! Time for a well-deserved break or move on to the next task.",
        parse_mode='Markdown'
    )

async def pomodoro_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts a study timer (Pomodoro). Default is 25 minutes."""
    chat_id = update.effective_chat.id
    user_input = context.args

    try:
        # Determine the duration in seconds
        if user_input and user_input[0].isdigit():
            duration_minutes = int(user_input[0])
        else:
            # Default to 25 minutes (1500 seconds) for a standard Pomodoro
            # NOTE: Changed to 10 seconds for easier testing
            duration_minutes = 25 
            
        duration_seconds = 10 if duration_minutes == 25 else duration_minutes * 60

        if duration_seconds < 5:
            await update.message.reply_text("The minimum timer duration is 5 seconds.")
            return

        # Schedule the job to run in 'duration_seconds'
        context.job_queue.run_once(
            alarm_callback, 
            duration_seconds, 
            chat_id=chat_id, 
            name=str(chat_id),
            data={'type': f'{duration_minutes}-minute study'}
        )

        await update.message.reply_text(
            f"✅ Timer set! You are now focusing for {duration_minutes} minutes. I'll notify you when time's up!"
        )

    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /pomodoro [minutes] or just /pomodoro (for 25 minutes).")

# --- To-Do List Functionality ---

async def tasks_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a task to the user's to-do list."""
    user_id = update.effective_user.id
    task_text = " ".join(context.args).strip()

    if not task_text:
        await update.message.reply_text("Please provide the task description after the command, e.g., `/tasks_add Read Chapter 3`")
        return

    # Initialize task list for user if it doesn't exist
    if user_id not in user_tasks:
        user_tasks[user_id] = []

    user_tasks[user_id].append(task_text)
    await update.message.reply_text(f"📝 Task added: **{task_text}** (Task #{len(user_tasks[user_id])})", parse_mode='Markdown')

async def tasks_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all active tasks for the user."""
    user_id = update.effective_user.id

    if user_id not in user_tasks or not user_tasks[user_id]:
        await update.message.reply_text("🎉 Your to-do list is empty! Ready to add some new study goals?")
        return

    message = "📚 **Your Current Study Tasks:**\n\n"
    for i, task in enumerate(user_tasks[user_id], 1):
        message += f"{i}. {task}\n"

    await update.message.reply_text(message, parse_mode='Markdown')

async def tasks_done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marks a task as complete and removes it."""
    user_id = update.effective_user.id
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /tasks_done [number of task to complete]. Use /tasks_list to see numbers.")
        return

    try:
        task_index = int(context.args[0]) - 1 # Convert 1-based index to 0-based
        
        if user_id not in user_tasks or not user_tasks[user_id]:
            await update.message.reply_text("Your list is empty, nothing to mark as done!")
            return

        if 0 <= task_index < len(user_tasks[user_id]):
            completed_task = user_tasks[user_id].pop(task_index)
            await update.message.reply_text(f"✅ Great job! You completed: **{completed_task}**", parse_mode='Markdown')
        else:
            await update.message.reply_text("That task number doesn't exist. Check /tasks_list for current numbers.")
    except Exception as e:
        logger.error(f"Error marking task done: {e}")
        await update.message.reply_text("An error occurred. Make sure you entered a valid number.")

# --- Motivational Feature ---

async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a motivational quote."""
    quote = get_motivational_quote()
    await update.message.reply_text(f"💡 **Motivation Boost:**\n\n_{quote}_", parse_mode='Markdown')

# --- Utility & Fallback Handlers ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /help is issued."""
    await start_command(update, context) # Re-use start command for help

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Default response for non-command text messages."""
    response_phrases = [
        "Got it! That sounds interesting. Need to start a /pomodoro to focus on it?",
        "I'm listening! Don't forget to add that to your /tasks_list if it's a To-Do.",
        "Thanks for sharing! What's the next study step?",
        "Understood. If you need a quick break, try the /quote command!",
    ]
    await update.message.reply_text(random.choice(response_phrases))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and report it."""
    logger.warning("Update '%s' caused error '%s'", update, context.error)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Oops! Something went wrong. Check the console for details or try again."
        )

def main() -> None:
    """Start the bot."""
    if TOKEN == "YOUR_BOT_TOKEN":
        print("!!! WARNING: Please replace 'YOUR_BOT_TOKEN' with your actual bot token from BotFather. !!!")
        return

    # Create the Application and pass it your bot's token.
    # The 'job_queue' is enabled by default and required for the timer.
    application = Application.builder().token(TOKEN).build()

    # --- Register Handlers ---

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # Study Commands
    application.add_handler(CommandHandler("pomodoro", pomodoro_command))
    application.add_handler(CommandHandler("tasks_add", tasks_add_command))
    application.add_handler(CommandHandler("tasks_list", tasks_list_command))
    application.add_handler(CommandHandler("tasks_done", tasks_done_command))
    application.add_handler(CommandHandler("quote", quote_command))

    # Handle all other text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Log all errors
    application.add_error_handler(error_handler)

    # --- Start the Bot ---
    logger.info("Starting Study Helper Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Study Helper Bot Stopped.")


if __name__ == "__main__":
    main()