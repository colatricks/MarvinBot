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

WISHLIST:
- Create GIF based Triggers (probably something like '/add trigger_word -> <MAGIC-GIF-WORD>' and wait for user to send gif)

IN PROGRESS: 
- Harry Potter Game - details TBC

"""

import logging
import sqlite3
import random
import re
import json
import uuid
from datetime import timedelta
from datetime import datetime
from telegram import Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from decouple import config

# USER CONFIGURATION

# .env Variables
# Place a .env file in the directory with 'TOKEN=<YOURTOKENHERE>' - alternatively replace TOKEN in the line below with your Bots token
TOKEN = config('TOKEN')
TERMLENGTH = config('TERMLENGTH')

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
cursor.execute("CREATE TABLE IF NOT EXISTS 'users' ('user_id' INTEGER NOT NULL, 'chat_id' INTEGER NOT NULL, 'timestamp' TEXT NOT NULL, 'status' TEXT NOT NULL, 'hp_house' TEXT, 'username' TEXT NOT NULL)")
cursor.execute("CREATE TABLE IF NOT EXISTS 'hp_points' ('user_id' INTEGER NOT NULL, chat_id INT NOT NULL, 'points' INT NOT NULL, 'timestamp' TEXT NOT NULL, 'term_id' TEXT NOT NULL)")
cursor.execute("CREATE TABLE IF NOT EXISTS 'hp_terms' ('chat_id' INT NOT NULL, 'term_id' TEXT NOT NULL, 'start_date' TEXT NOT NULL, 'end_date' TEXT NOT NULL, 'is_current' INT NOT NULL)")
cursor.execute("CREATE TABLE IF NOT EXISTS 'bot_service_messages' ('chat_id' INT NOT NULL, 'message_id' TEXT NOT NULL, 'created_date' TEXT NOT NULL, 'status' TEXT NOT NULL)")


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
    
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text
    user_id = str(update.message.from_user.id)
    user_status = (context.bot.get_chat_member(chat_id,user_id)).status
    username = context.bot.get_chat_member(chat_id,user_id).user.username

    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))
    
    # Lookup to check if text is a trigger - send trigger message to group.
    lookup = trigger_lookup(chat_text.lower(), chat_id)
    if lookup[0] == 1:
        context.bot.send_message(chat_id, text=lookup[1])

    # Lookup to check if user is in activity DB, update the DB either way.
    actLookup = activity_lookup(user_id, chat_id)
    if actLookup[0] == 1: 
        cursor.execute("UPDATE users SET timestamp = ?, status = ?, username = ? WHERE user_id = ? AND chat_id = ?",(timestamp,user_status,username,user_id,chat_id))
        db.commit()
    elif actLookup[0] == 0:
        cursor.execute("INSERT INTO users (user_id,chat_id,timestamp,status,username) VALUES(?,?,?,?,?)",(user_id,chat_id,timestamp,user_status,username))
        db.commit()
    
    # Marvins Personality
    global frequency_count
    if frequency_count > frequency_total:
        marvin_says = marvin_personality()
        context.bot.send_message(chat_id, text=marvin_says)
        frequency_count = 0
    else:
        frequency_count += 1

    hp_term_tracker(chat_id)
    hp_points(update, context, chat_id, timestamp)
    del_bot_message(chat_id, context)


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

    if len(chat_text) == 9: 
        select = cursor.execute("SELECT * from users WHERE chat_id = ? AND status NOT IN ('kicked', 'left') AND timestamp < DateTime('Now', 'LocalTime', '-2 Day') ORDER BY timestamp DESC",(chat_id,))
        activity_type = "Standard"
    elif len(chat_text) == 14: 
        select = cursor.execute("SELECT * from users WHERE chat_id = ? AND status NOT IN ('kicked', 'left') ORDER BY timestamp DESC",(chat_id,))
        activity_type = "Full"
    else: 
        context.bot.send_message(chat_id, text="Hmm. That command wasn't quite right. It's either '/activity' or '/activity full'", parse_mode='markdown')

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

            if activity_type == "Standard":
                info_message = "To get the full chat activity list, use '/activity full'\n\n"
            else: 
                info_message = "To get the short chat activity list, use '/activity'\n\n"
        sentenceList = "\n".join(activityList)
        context.bot.send_message(chat_id, text="Activity List:\n\n" + info_message + sentenceList, parse_mode='markdown')
    else: 
        error = 'Something went wrong or activity wasnt found'
        context.bot.send_message(chat_id, text="It's a busy little group! Everybody has been active in the last 2 days. If you want the full chat list, use '/activity full'", parse_mode='markdown')
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
            cursor.execute("UPDATE users SET status = 'left' WHERE user_id = ? AND chat_id = ?",(user_id,chat_id))
            db.commit()
            return 0,user_detail
    except: 
        user_detail = 'User not found.'
        return 0, user_detail

# Harry Potter House Functionality
# User can either send a simple '/roll' command which will default to a single eight sided die or,
# User can send a '/roll XDY' command where X = number of dice, D is the separator, Y = sides on each die. 

def hp_assign_house(update: Update, context: CallbackContext) -> None:
    chat_id = str(update.message.chat_id)
    if len(update.message.text.split()) == 3:
        command = update.message.text.split()
        select = cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE AND chat_id = ?",(command[1][1:],chat_id))
        rows = select.fetchone()
        if rows:
            user_detail = activity_status_check(rows[0],rows[1],context)
            if command[2].capitalize() not in ['Gryffindor','Slytherin','Hufflepuff','Ravenclaw','Houseelf']:
                context.bot.send_message(chat_id, text="Accio brain, perhaps?\n\nHouse options are: Gryffindor, Slytherin, Hufflepuff, Ravenclaw, HouseElf", parse_mode='markdown')    
            else: 
                cursor.execute("UPDATE users SET hp_house = ? WHERE username = ? AND chat_id = ?",(command[2].capitalize(),command[1][1:],chat_id))
                db.commit()
                if command[2].lower() == "gryffindor":
                    context.bot.send_message(chat_id, text="🦁 Gryffindor! 🦁 \n\nWhere dwell the brave at heart,\nTheir daring, nerve, and chivalry,\nSet Gryffindors apart!", parse_mode='markdown')            
                elif command[2].lower() == "slytherin":
                    context.bot.send_message(chat_id, text="🐍 Slytherin! 🐍 \n\nYou'll make your real friends,\nThose cunning folks use any means,\nTo achieve their ends!", parse_mode='markdown')  
                elif command[2].lower() == "hufflepuff":
                    context.bot.send_message(chat_id, text="🦡 Hufflepuff! 🦡 \n\nWhere they are just and loyal, \nThose patient Hufflepuffs are true,\nAnd unafraid of toil!", parse_mode='markdown')  
                elif command[2].lower() == "ravenclaw":
                    context.bot.send_message(chat_id, text="🦅 Ravenclaw! 🦅 \n\nIf you've a ready mind, \nWhere those of wit and learning,\nWill always find their kind!", parse_mode='markdown')  
                elif command[2].lower() == "houseelf":
                    context.bot.send_message(chat_id, text="🧝‍♀️ House Elf 🧝‍♀️ \n\nA little unsure of their home,\nThey get to clean up our dirty work.", parse_mode='markdown')  
                db.commit()
        else:
            context.bot.send_message(chat_id, text="Did you Avada Kedavra someone?\n\nI didn't find that username in my database. Either they haven't spoken before or you typo'd it.", parse_mode='markdown')    
    elif len(update.message.text.split()) == 2:
        command = update.message.text.split()
        select = cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE AND chat_id = ?",(command[1][1:],chat_id))
        rows = select.fetchone()
        if rows:
            user_detail = activity_status_check(rows[0],rows[1],context)
            user_first_name = str((user_detail[1]).user.first_name)
            
            if (user_detail[1].user.last_name == None):
                user_last_name = ""
            else: 
                user_last_name = str(" " + (user_detail[1]).user.last_name)

            if rows[4].lower() == "gryffindor":
                context.bot.send_message(chat_id, text=user_first_name + user_last_name + " is a Gryffindor! 🦁", parse_mode='markdown')            
            elif rows[4].lower() == "slytherin":
                context.bot.send_message(chat_id, text=user_first_name + user_last_name + " is a Slytherin! 🐍", parse_mode='markdown')  
            elif rows[4].lower() == "hufflepuff":
                context.bot.send_message(chat_id, text=user_first_name + user_last_name + " is a Hufflepuff! 🦡", parse_mode='markdown')  
            elif rows[4].lower() == "ravenclaw":
                context.bot.send_message(chat_id, text=user_first_name + user_last_name + " is a Ravenclaw! 🦅", parse_mode='markdown')  
            elif rows[4].lower() == "houseelf":
                context.bot.send_message(chat_id, text=user_first_name + user_last_name + " is a House Elf! 🧝‍♀️", parse_mode='markdown')
        else: 
            context.bot.send_message(chat_id, text="Oops they don't have a house yet. Go to https://www.wizardingworld.com/news/discover-your-hogwarts-house-on-wizarding-world to find yours then do:\n\n /sortinghat <YourUsername> <YourHouse>'", parse_mode='markdown')
    elif len(update.message.text.split()) == 1:
        select = cursor.execute("SELECT * FROM users WHERE chat_id = ? AND status NOT IN ('kicked', 'left')",(chat_id,))
        rows = select.fetchall()

        gryffindor = []
        ravenclaw = []
        slytherin = []
        hufflepuff = []
        houseelf = []
        muggles = []

        if rows:
            for row in rows:
                user_detail = activity_status_check(row[0],row[1],context)
                user_first_name = str((user_detail[1]).user.first_name)
                if user_detail[0] != 0:
                    if (user_detail[1].user.last_name == None):
                        user_last_name = ""
                    else: 
                        user_last_name = str(" " + (user_detail[1]).user.last_name)

                    if row[4] == "Gryffindor":
                        gryffindor.append(user_first_name + user_last_name)
                    elif row[4] == "Slytherin":
                        slytherin.append(user_first_name + user_last_name)
                    elif row[4] == "Hufflepuff":
                        hufflepuff.append(user_first_name + user_last_name)
                    elif row[4] == "Ravenclaw":
                        ravenclaw.append(user_first_name + user_last_name)
                    elif row[4] == "Houseelf":
                        houseelf.append(user_first_name + user_last_name)
                    else:
                        muggles.append(user_first_name + user_last_name)
            
            sentenceGryffindor = ", ".join(gryffindor)
            sentenceSlytherin = ", ".join(slytherin)
            sentenceHufflepuff = ", ".join(hufflepuff)
            sentenceRavenclaw = ", ".join(ravenclaw)
            sentenceHouseelf = ", ".join(houseelf)
            sentenceMuggles = ", ".join(muggles)

            context.bot.send_message(chat_id, text="Hogwarts House Lists:\n\n🦁 GRYFFINDOR 🦁\n" + sentenceGryffindor + "\n\n🦡 HUFFLEPUFF 🦡\n" + sentenceHufflepuff + "\n\n🐍 SLYTHERIN 🐍\n" + sentenceSlytherin + "\n\n🦅 RAVENCLAW 🦅\n" + sentenceRavenclaw + "\n\n🧝‍♀️ HOUSE ELVES 🧝‍♀️\n" + sentenceHouseelf + "\n\n❌ FILTHY MUGGLES ❌\n" + sentenceMuggles + "\n\nDon't want to be a filthy muggle? Take the test on the official Harry Potter website and then: \n\n'/sortinghat @yourusername yourhousename' ")

    else:
        context.bot.send_message(chat_id, text="You dare use my spells against me? You did it wrong anyway. \n\n Sort someone into their house with:\n '/sortinghat @username <houseName>'\n\nHouse options are: Gryffindor, Slytherin, Hufflepuff, Ravenclaw, HouseElf", parse_mode='markdown')

def hp_term_tracker(chat_id) -> None:
    chat_id = chat_id
    time = datetime.now()
    time_plus = time + timedelta(days=int(TERMLENGTH))
    timestamp_now = str(time.strftime("%Y-%m-%d %H:%M:%S"))
    timestamp_plus = str(time_plus.strftime("%Y-%m-%d %H:%M:%S"))

    select = cursor.execute("SELECT * FROM hp_terms WHERE is_current = 1 AND chat_id = ?",(chat_id,))
    rows = select.fetchone()
    if rows:
        # Is the term still current?
        if timestamp_now < rows[3]:
            pass
        else:
            # Pull back final totals
            # Send results to group
            # Update past winners?
            # Close old term
            cursor.execute("UPDATE hp_terms SET is_current = ? WHERE chat_id = ? AND term_id = ?",(0,chat_id, rows[1]))
            # Start new term
            cursor.execute("INSERT INTO hp_terms (chat_id, term_id, start_date, end_date, is_current) VALUES(?,?,?,?,1)",(chat_id,str(uuid.uuid4()),timestamp_now,timestamp_plus))
            db.commit()

        # If the term is no longer current, publish results and start a new term

    else:
        # First ever term!
        cursor.execute("INSERT INTO hp_terms (chat_id, term_id, start_date, end_date, is_current) VALUES(?,?,?,?,1)",(chat_id,str(uuid.uuid4()),timestamp_now,timestamp_plus))
        db.commit()

def hp_points(update,context,chat_id,timestamp) -> None:
    # Get Current Term
    select = cursor.execute("SELECT * FROM hp_terms WHERE is_current = 1 AND chat_id = ?",(chat_id,))
    rows = select.fetchone()
    term_id = rows[1]
    positive = ["+","❤️","😍","👍"]
    negative = ["-","😡","👎"]

    # Check if message is a a reply
    if update.message.reply_to_message:
        if not update.message.reply_to_message.from_user.is_bot:
            to_user_id = update.message.reply_to_message.from_user.id
            from_user_id = update.message.from_user.id
        
            # Get Current Points
            select = cursor.execute("SELECT points FROM hp_points WHERE chat_id = ? AND term_id = ? and user_id = ?",(chat_id,term_id,to_user_id))
            rows = select.fetchone()

            # Get Sender & Target Users House
            sender = cursor.execute("SELECT hp_house FROM users WHERE chat_id = ? and user_id = ?",(chat_id,from_user_id))
            sender = sender.fetchone()
            if sender[0] == "Gryffindor":
                senderHouse = "🦁"
            elif sender[0] == "Slytherin":
                senderHouse = "🐍"
            elif sender[0] == "Hufflepuff":
                senderHouse = "🦡"
            elif sender[0] == "Ravenclaw":
                senderHouse = "🦅"
            elif sender[0] == "Houseelf":
                senderHouse = "🧝‍♀️"
            else: 
                senderHouse = "❌"

            receiver = cursor.execute("SELECT hp_house FROM users WHERE chat_id = ? and user_id = ?",(chat_id,to_user_id))
            receiver = receiver.fetchone()
            if receiver[0] == "Gryffindor":
                receiverHouse = "🦁"
            elif receiver[0] == "Slytherin":
                receiverHouse = "🐍"
            elif receiver[0] == "Hufflepuff":
                receiverHouse = "🦡"
            elif receiver[0] == "Ravenclaw":
                receiverHouse = "🦅"
            elif receiver[0] == "Houseelf":
                receiverHouse = "🧝‍♀️"
            else: 
                receiverHouse = "❌"

            # Check if message was positive or not
            if update.message.text in positive:
                if rows:
                    current_points = rows[0]
                    current_points += 1
                    cursor.execute("UPDATE hp_points SET points = ?, timestamp = ? WHERE user_id = ? AND chat_id = ? AND term_id = ?",(current_points,timestamp,to_user_id,chat_id,term_id))
                    db.commit()
                else: 
                    current_points = 1    
                    cursor.execute("INSERT INTO hp_points (user_id, chat_id, points, timestamp, term_id) VALUES(?,?,?,?,?)",(to_user_id,chat_id,current_points,timestamp,term_id))
                    db.commit()
                messageinfo = context.bot.send_message(chat_id, text=update.message.from_user.first_name + " of " + senderHouse + " has awarded " + update.message.reply_to_message.from_user.first_name + " of " + receiverHouse + " a House point!\nTheir new total for this Term is: " + str(current_points) )
                log_bot_message(messageinfo.message_id,chat_id,timestamp)
            elif update.message.text in negative:
                if rows:
                    current_points = rows[0]
                    current_points -= 1
                    cursor.execute("UPDATE hp_points SET points = ?, timestamp = ? WHERE user_id = ? AND chat_id = ? AND term_id = ?",(current_points,timestamp,to_user_id,chat_id,term_id))
                    db.commit()
                else: 
                    current_points = -1    
                    cursor.execute("INSERT INTO hp_points (user_id, chat_id, points, timestamp, term_id) VALUES(?,?,?,?,?)",(to_user_id,chat_id,current_points,timestamp,term_id))
                    db.commit()
                messageinfo = context.bot.send_message(chat_id, text=update.message.from_user.first_name + " of " + senderHouse + " has deducted " + update.message.reply_to_message.from_user.first_name + " of " + receiverHouse + " a House point!\nTheir new total for this Term is: " + str(current_points) )
                log_bot_message(messageinfo.message_id,chat_id,timestamp)

def hp_points_admin(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    user_detail = activity_status_check(user_id,chat_id,context)
    user_status = user_detail[0]

    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))

    if user_status in ("creator","administrator"):
        # Get Current Term
        select = cursor.execute("SELECT * FROM hp_terms WHERE is_current = 1 AND chat_id = ?",(chat_id,))
        rows = select.fetchone()
        term_id = rows[1]

        if len(update.message.text.split()) == 3:
            command = update.message.text.split()

            # Stop admins being silly
            if int(command[2]) > 20:
                messageinfo = context.bot.send_message(chat_id, text="Stupefy! Stop right there. The Ministry of Magic has mandated no more than 20 points can be awarded at a time!")
                log_bot_message(messageinfo.message_id,chat_id,timestamp)
            elif int(command[2]) < -20:
                messageinfo = context.bot.send_message(chat_id, text="Stupefy! Stop right there. The Ministry of Magic has mandated no more than 20 points can be deducted at a time!")
                log_bot_message(messageinfo.message_id,chat_id,timestamp)
            else: 

                select = cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE AND chat_id = ?",(command[1][1:],chat_id))
                rows = select.fetchone()
                if rows:
                    user_detail = activity_status_check(rows[0],rows[1],context)
                    user_first_name = str((user_detail[1]).user.first_name)
                    if (user_detail[1].user.last_name == None):
                        user_last_name = " "
                    else: 
                        user_last_name = str((user_detail[1]).user.last_name)

                    if rows[4] == "Gryffindor":
                        receiverHouse = "🦁"
                    elif rows[4] == "Slytherin":
                        receiverHouse = "🐍"
                    elif rows[4] == "Hufflepuff":
                        receiverHouse = "🦡"
                    elif rows[4] == "Ravenclaw":
                        receiverHouse = "🦅"
                    elif rows[4] == "Houseelf":
                        receiverHouse = "🧝‍♀️"
                    else: 
                        receiverHouse = "❌"

                    # Get Current Points
                    select = cursor.execute("SELECT points FROM hp_points WHERE chat_id = ? AND term_id = ? and user_id = ?",(chat_id,term_id,user_detail[1].user.id))
                    rows = select.fetchone()
                    if rows:
                        current_points = rows[0]
                        current_points = int(current_points) + int(command[2])
                        cursor.execute("UPDATE hp_points SET points = ?, timestamp = ? WHERE user_id = ? AND chat_id = ? AND term_id = ?",(current_points,timestamp,user_detail[1].user.id,chat_id,term_id))
                        db.commit()
                    else: 
                        current_points = command[2]    
                        cursor.execute("INSERT INTO hp_points (user_id, chat_id, points, timestamp, term_id) VALUES(?,?,?,?,?)",(user_detail[1].user.id,chat_id,current_points,timestamp,term_id))
                        db.commit()
                    
                    if int(command[2]) > 0:
                        messageinfo = context.bot.send_message(chat_id, text=user_first_name + " " + user_last_name + " of " + receiverHouse + " has been awarded " + str(command[2]) + " House points!\nTheir new total for this Term is: " + str(current_points) )
                        log_bot_message(messageinfo.message_id,chat_id,timestamp)
                    elif int(command[2]) == 0:
                        messageinfo = context.bot.send_message(chat_id, text=user_first_name + " " + user_last_name + " of " + receiverHouse + " has been um ... awarded no extra House points.\nTheir new total for this Term is: " + str(current_points) )
                        log_bot_message(messageinfo.message_id,chat_id,timestamp)
                    else:
                        messageinfo = context.bot.send_message(chat_id, text=user_first_name + " " + user_last_name + " of " + receiverHouse + " has been deducted " + str(command[2]) + " House points!\nTheir new total for this Term is: " + str(current_points) )
                        log_bot_message(messageinfo.message_id,chat_id,timestamp)
        elif len(update.message.text.split()) == 2:
            command = update.message.text.split()
            if command[1] == 'totals':
                pass
                #context.bot.send_message(chat_id, text="House points totals are: ")
            else:
                messageinfo = context.bot.send_message(chat_id, text="Available commands are:\n\n'/points @username <pointsTotal>'")
                log_bot_message(messageinfo.message_id,chat_id,timestamp)
        else: 
            messageinfo = context.bot.send_message(chat_id, text="Available commands are:\n\n'/points @username <pointsTotal>'")
            log_bot_message(messageinfo.message_id,chat_id,timestamp)
    else:
        user_first_name = str((user_detail[1]).user.first_name)
        if (user_detail[1].user.last_name == None):
            user_last_name = " "
        else: 
            user_last_name = str((user_detail[1]).user.last_name)
        messageinfo = context.bot.send_message(chat_id, text="Yer not a Wizard Harry ... or ... an Admin ... " + user_first_name + " " + user_last_name)
        log_bot_message(messageinfo.message_id,chat_id,timestamp)

def log_bot_message(message_id, chat_id, timestamp) -> None:
    cursor.execute("INSERT INTO bot_service_messages (message_id, chat_id, created_date, status) VALUES(?,?,?,'sent')",(message_id, chat_id, timestamp))
    db.commit()

def del_bot_message(chat_id, context):
    time = datetime.now()
    select = cursor.execute("SELECT * FROM bot_service_messages WHERE chat_id = ?",(chat_id,))
    rows = select.fetchall()
    if rows:
        for row in rows:
            message_id = row[1]
            created_date = datetime.strptime(row[2], '%Y-%m-%d %H:%M:%S')
            target_date = created_date + timedelta(seconds=15)
            if time > target_date:
                context.bot.delete_message(chat_id,message_id)
                cursor.execute("DELETE FROM bot_service_messages WHERE chat_id = ? AND message_id = ?",(chat_id,message_id))
                db.commit()

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
    dispatcher.add_handler(CommandHandler("sortinghat", hp_assign_house))
    dispatcher.add_handler(CommandHandler("points", hp_points_admin))

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