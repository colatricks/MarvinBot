"""
Group Entertainment Bot written for Python 3

Marvin is your groups resident Paranoid Android with personality! 
Lovingly inspired by https://en.wikipedia.org/wiki/Marvin_the_Paranoid_Android 

REQUIREMENTS:
- Python 3.6+
- SQLite3
- Python-Telegram-Bot (https://github.com/python-telegram-bot/python-telegram-bot)

USAGE:
- pip install -r requirements.txt
- Rename .env.example to .env - update with your Telegram Bot Token
- Rename rollSass.json.example to rollSass.json and Sass.json.example to Sass.json - feel free to add your own snark/personality.

FEATURES: 
- Dice Roll (/roll or /roll XdY e.g /roll 2d8)
- Triggers (/add trigger -> triggerResponse ... /del trigger)
- Activity tracker, check the last time users interacted with the group. (Passive feature, /activity to check the log)
- 'Personality' - Marvin can be configured to 'talk' at the group occassionally. How sassy he is, is up to you!

"""

import logging
import sqlite3
import random
import re
import json
from datetime import timedelta
from datetime import datetime
from telegram import Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from decouple import config

# USER CONFIGURATION

# .env Variables
# Place a .env file in the directory with 'TOKEN=<YOURTOKENHERE>' - alternatively replace TOKEN in the line below with your Bots token
TOKEN = config('TOKEN')

# Separator character. Used for commands with a to/from type response
separator = '->'

# Used for random element to Marvins Personality
# Marvin has some personality stored in rollSass.json and Sass.json 
# rollSass is used every time /roll is invoked, Sass is used based on the frequency below
frequency_count = 0
frequency_total = 400 # how many messages are sent before Marvin 'speaks'


# END USER CONFIGURATION 

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# Open connection to the Database and define table names
dbname = "marvin"
db = sqlite3.connect(dbname+".db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS 'triggers' ('trigger_word' TEXT NOT NULL, 'trigger_response' TEXT NOT NULL, 'chat_id' INTEGER NOT NULL)")
cursor.execute("CREATE TABLE IF NOT EXISTS 'users' ('user_id' INTEGER NOT NULL, 'chat_id' INTEGER NOT NULL, 'timestamp' TEXT NOT NULL, 'status' TEXT NOT NULL)")

# Make timestamps pretty again
def pretty_date(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    now = datetime.now()
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(second_diff // 60) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(second_diff // 3600) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff // 7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff // 30) + " months ago"
    return str(day_diff // 365) + " years ago"

# Define a few command handlers. These usually take the two arguments update and
# context.
def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    update.message.reply_markdown_v2(
        fr'Hi {user.mention_markdown_v2()}\!',
        reply_markup=ForceReply(selective=True),
    )


def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('Help!')


# /add functionality 
# Creates a new trigger, invoked with /add trigger_word <separator> trigger_response
# 
def add_trigger_command(update: Update, context: CallbackContext) -> None:
    """Adds a new trigger when the /add command is used"""
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text

    # Validations.
    if(len(chat_text.split()) < 2):
        update.message.reply_text("Bad Arguments, create a trigger with: \n\n /add trigger " + separator + " trigger_response")
        return
    if(chat_text.find(separator, 1) == -1):
        update.message.reply_text("Separator not found, create a trigger with: \n\n /add trigger " + separator + " trigger_response")
        return

    rest_text = chat_text.split(' ', 1)[1]
    trigger_word = u'' + rest_text.split(separator)[0].strip().lower()
    trigger_word.encode('utf-8')
    trigger_response = u'' + rest_text.split(separator, 1)[1].strip()

    if(len(trigger_response) < 1):
        update.message.reply_text("Bad Arguments, create a trigger with: \n\n /add trigger " + separator + " trigger_response")
        return
    if(len(trigger_response) > 3000):
        update.message.reply_text('Response too long. [chars > 3000]')
        return

    # Save trigger for the group
    lookup = trigger_lookup(trigger_word, chat_id)
    if lookup[0] == 1: 
        cursor.execute("UPDATE triggers SET trigger_response = ? WHERE trigger_word = ? AND chat_id = ?",(trigger_response, trigger_word, chat_id))
        db.commit()
        context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] updated.")
    elif lookup[0] == 0:
        cursor.execute("INSERT INTO triggers (trigger_word,trigger_response,chat_id) VALUES(?,?,?)",(trigger_word,trigger_response,chat_id))
        db.commit()
        context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] created.")

# /del functionality 
# Removes any given trigger from a group. 
# Invoked with /del <trigger_word>
def del_trigger_command(update: Update, context: CallbackContext) -> None:
    """Removes a trigger when the /del command is used"""
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text

    if(len(chat_text.split()) < 2):
        context.bot.send_message(chat_id, text="Bad Arguments")
        return
    trigger_word = chat_text.split(' ', 1)[1].strip().lower()

    lookup = trigger_lookup(trigger_word, chat_id)
    if lookup[0] == 1: 
        cursor.execute("DELETE FROM triggers WHERE trigger_word = ? AND chat_id = ?",(trigger_word,chat_id))
        db.commit()
        context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] deleted.")
    elif lookup[0] == 0:
        context.bot.send_message(chat_id, text="Trigger not found.")

# Checks if a trigger exists, if yes, returns the value
# 
# 
def trigger_lookup(trigger_word, chat_id) -> None:
    select = cursor.execute("SELECT * from triggers WHERE trigger_word = ? AND chat_id = ?",(trigger_word,chat_id))
    rows = select.fetchall()
    
    if rows:
        for row in rows:
            if str(row[0]) == trigger_word and str(row[2]) == chat_id:
                return 1,row[1]
            else: 
                return 0
    else: 
        error = 'Something went wrong or trigger wasnt found'
        return 0, error

# /list functionality 
# Returns a simple list of all available triggers for a given group.
# 
def list_trigger_command(update: Update, context: CallbackContext) -> None:
    """Removes a trigger when the /list command is used"""
    chat_id = str(update.message.chat_id)
    select = cursor.execute("SELECT * from triggers WHERE chat_id = ?",(chat_id,))
    rows = select.fetchall()
    triggerList = []
    if rows:
        for row in rows:
            triggerList.append(row[0])
        
        sentenceList = ", ".join(triggerList)
        context.bot.send_message(chat_id, text="Trigger list:\n\n" + sentenceList)
    else: 
        error = 'Something went wrong or trigger wasnt found'
        context.bot.send_message(chat_id, text="Hmm, doesn't look like this group has any triggers yet!")
        return 0, error

# /listDetail functionality 
# Works similar to /list, however will also pull the trigger responses at the same time.
# As this can be quite spammy, it sends the detail directly to the requestor rather than publishing in the group.
def list_trigger_detail_command(update: Update, context: CallbackContext) -> None:
    """Sends a message to the requester with the full detail of all triggers"""
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    select = cursor.execute("SELECT * from triggers WHERE chat_id = ?",(chat_id,))
    rows = select.fetchall()
    triggerList = []
    if rows:
        for row in rows:
            triggerFull = "*" + row[0] + " : *\n" + row[1]
            triggerList.append(triggerFull)
        
        sentenceList = "\n\n".join(triggerList)
        context.bot.send_message(user_id, text="Full Detail Trigger List:\n\n" + sentenceList, parse_mode='markdown')
    else: 
        error = 'Something went wrong or trigger wasnt found'
        context.bot.send_message(chat_id, text="Hmm, doesn't look like this group has any triggers yet!")
        return 0, error

# Passive chat polling 
# Processes each message received in any groups where the Bot is active
# Feeds into the Trigger and Activity functionality
def chat_polling(update: Update, context: CallbackContext) -> None:
    print(update)
    
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text
    user_id = str(update.message.from_user.id)
    user_status = (context.bot.get_chat_member(chat_id,user_id)).status

    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))
    
    # Lookup to check if text is a trigger - send trigger message to group.
    lookup = trigger_lookup(chat_text.lower(), chat_id)
    if lookup[0] == 1:
        context.bot.send_message(chat_id, text=lookup[1])

    # Lookup to check if user is in activity DB, update the DB either way.
    actLookup = activity_lookup(user_id, chat_id)
    if actLookup[0] == 1: 
        cursor.execute("UPDATE users SET timestamp = ?, status = ? WHERE user_id = ? AND chat_id = ?",(timestamp,user_status,user_id,chat_id))
        db.commit()
    elif actLookup[0] == 0:
        cursor.execute("INSERT INTO users (user_id,chat_id,timestamp,status) VALUES(?,?,?,?)",(user_id,chat_id,timestamp,user_status))
        db.commit()
    
    # Marvins Personality
    global frequency_count
    if frequency_count > frequency_total:
        marvin_says = marvin_personality()
        context.bot.send_message(chat_id, text=marvin_says)
        frequency_count = 0
    else:
        frequency_count += 1

def marvin_personality() -> None:
    json_file = open("Sass.json")
    Sass = json.load(json_file)
    json_file.close()

    return random.choice(Sass)


# Activity Lookup function
# Checks if user has been logged to the DB previously
# 
def activity_lookup(user_id, chat_id) -> None:
    select = cursor.execute("SELECT * from users WHERE user_id = ? AND chat_id = ?",(user_id,chat_id))
    rows = select.fetchall()
    
    if rows:
        for row in rows:
            if str(row[0]) == user_id and str(row[1]) == chat_id:
                return 1,row[0]
    else: 
        error = 'Something went wrong or user activity entry was not found.'
        return 0, error


# /activity Command
# Returns a sorted list of recent user activity
# User can optionally ask to filter by users who have not been active in X number of days with '/activity X' 
def activity_command(update: Update, context: CallbackContext) -> None:
    """Pulls a list of users activity and sends to the group"""
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text
    user_id = str(update.message.from_user.id)

    select = cursor.execute("SELECT * from users WHERE chat_id = ? AND status NOT IN ('kicked', 'left') ORDER BY timestamp DESC",(chat_id,))
    rows = select.fetchall()

    activityList = []
    if rows:
        for row in rows:
            user_detail = activity_status_check(row[0],row[1],context)
            if user_detail[0] == 0:
                # User no longer part of group, update status appropriately
                cursor.execute("UPDATE users SET status = 'left' WHERE user_id = ? AND chat_id = ?",(str(row[0]),chat_id))
                db.commit()
            else: 
                user_first_name = str((user_detail[1]).user.first_name)
                if (user_detail[1].user.last_name == None):
                    user_last_name = " "
                else: 
                    user_last_name = str((user_detail[1]).user.last_name)

                timestamp = row[2]
                timestampObject = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                prettyDate = pretty_date(timestampObject)

                activityFull = prettyDate + " : *" + user_first_name + user_last_name + "* " 
                activityList.append(activityFull)
        
        sentenceList = "\n".join(activityList)
        context.bot.send_message(chat_id, text="Activity List:\n\n" + sentenceList, parse_mode='markdown')
    else: 
        error = 'Something went wrong or activity wasnt found'
        return 0, error

# User Status Check
# Checks if a user is an active member of the group.
# 
def activity_status_check(user_id,chat_id,context: CallbackContext) -> None:
    try: 
        user_detail = context.bot.get_chat_member(chat_id,user_id)
        user_status = (user_detail).status

        if user_status in ("member","creator","administrator"):
            return user_status,user_detail
        else: 
            return 0,user_detail
    except: 
        user_detail = 'User not found.'
        return 0, user_detail

# Roll functionality
# User can either send a simple '/roll' command which will default to a single eight sided die or,
# User can send a '/roll XDY' command where X = number of dice, D is the separator, Y = sides on each die. 
def roll_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    chat_id = update.message.chat_id
    chat_text = update.message.text

    regexp = re.compile('[0-9]+D[0-9]+', re.IGNORECASE)

    json_file = open("rollSass.json")
    rollSass = json.load(json_file)
    json_file.close()

    if (len(chat_text) == 5):
        low = 1
        high = 8
        rolled = random.randint(low, high)
        context.bot.send_message(chat_id, text=random.choice(rollSass) + "\n\n" + str(rolled))

    elif(regexp.search(chat_text)):
        dice = chat_text.split()
        numbers = re.split("d",dice[1],flags=re.IGNORECASE)
        low = 1
        high = int(numbers[1])
        totaldice = int(numbers[0])            
        loop = 1
        rolled=[]
        while loop <= totaldice:                
            loop = loop + 1
            rolled.append(random.randint(low, high))
        context.bot.send_message(chat_id, text=random.choice(rollSass) + "\n\n" + str(rolled))

    else:
        context.bot.send_message(chat_id, text="Stupid human. Of course you typed the wrong format. It's either '/roll' or '/roll XdY' where X is the number of dice, and Y is how many sides each dice has. For example, '/roll 2d6'")

# Original Code below here
def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    updater = Updater(TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("roll", roll_command))
    dispatcher.add_handler(CommandHandler("add", add_trigger_command))
    dispatcher.add_handler(CommandHandler("del", del_trigger_command))
    dispatcher.add_handler(CommandHandler("list", list_trigger_command))
    dispatcher.add_handler(CommandHandler("listDetail", list_trigger_detail_command))
    dispatcher.add_handler(CommandHandler("activity", activity_command))

    # on non command i.e message - checks each message and runs it through our poller
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, chat_polling))

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()