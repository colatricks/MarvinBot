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
- Launch with 'python3 MarvinBot.py
- Group configuration can be controlled by /config from inside the group.

FEATURES: 
- Dice Roll (/roll or /roll XdY e.g /roll 2d8)
- Text based Triggers (/add trigger -> triggerResponse ... /del trigger)
- Media Based Triggers, with the MEDIA keyword (/add trigger_word -> MEDIA) 
- Activity tracker, check the last time users interacted with the group. (Passive feature, /activity to check the log)
- 'Personality' - Marvin can be configured to 'talk' at the group occassionally. How sassy he is, is up to you!
- Harry Potter Reputation System
    - Add users to their HP House (/sortinghat @username <housename>)
    - List HP House members (/sortinghat)
    - Give/Take reputation from a user (Reply to their message with + or -)
    - Bulk award reputation (Admin only) (/points @username <pointsTotal>)
    - List points totals (/points totals)
    - Random Character Appearances (via Stickers) - characters from the movies appear to influence House Points
"""

import logging
import sqlite3
import random
import re
import uuid
import json
import time
from datetime import timedelta
from datetime import datetime
from telegram import Update, ForceReply, ParseMode, ReplyKeyboardMarkup, ReplyKeyboardRemove, ChatMemberUpdated, ChatMember, Chat
from typing import Tuple, Optional
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ChatMemberHandler
from decouple import config

# USER CONFIGURATION

# .env Variables
# Place a .env file in the directory with 'TOKEN=<YOURTOKENHERE>' - alternatively replace TOKEN in the line below with your Bots token
TOKEN = config('TOKEN')
TERMLENGTH = config('TERMLENGTH')

# Service Message - how long Marvins service messages stay before deletion in seconds
short_duration = 30
standard_duration = 60
long_duration = 90

# Separator character. Used for commands with a to/from type response
separator = '->'

# END USER CONFIGURATION 

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# Open connection to the Database and define table names
dbname = "marvin"
db = sqlite3.connect(dbname+".db", check_same_thread=False)
db.row_factory = sqlite3.Row
cursor = db.cursor()

def db_initialise(chat_id) -> None:
    cursor.execute("CREATE TABLE IF NOT EXISTS 'triggers' ('trigger_word' TEXT NOT NULL, 'trigger_response' TEXT NOT NULL, 'chat_id' INTEGER NOT NULL, 'trigger_response_type' TEXT, 'trigger_response_media_id' TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'users' ('user_id' INTEGER NOT NULL, 'chat_id' INTEGER NOT NULL, 'timestamp' TEXT NOT NULL, 'status' TEXT NOT NULL, 'hp_house' TEXT, 'username' TEXT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'hp_points' ('user_id' INTEGER NOT NULL, chat_id INT NOT NULL, 'points' INT NOT NULL, 'timestamp' TEXT NOT NULL, 'term_id' TEXT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'hp_terms' ('chat_id' INT NOT NULL, 'term_id' TEXT NOT NULL, 'start_date' TEXT NOT NULL, 'end_date' TEXT NOT NULL, 'is_current' INT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'hp_past_winners' ('chat_id' INT NOT NULL, 'winning_house' TEXT NOT NULL, 'house_points_total' INT NOT NULL, 'house_champion' TEXT NOT NULL, 'champion_points_total' INT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'hp_config' ('chat_id' INT NOT NULL, 'config_name' TEXT NOT NULL, 'affected_entity' TEXT NOT NULL, 'expiry_time' TEXT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'counters' ('chat_id' INT NOT NULL, 'counter_name' TEXT NOT NULL, 'counter_value' TEXT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'bot_service_messages' ('chat_id' INT NOT NULL, 'message_id' TEXT NOT NULL, 'created_date' TEXT NOT NULL, 'status' TEXT NOT NULL, 'duration' INT, 'type' TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'bot_question_messages' ('chat_id' INT NOT NULL, 'message_id' TEXT NOT NULL, 'trigger_word' TEXT, 'new_value' TEXT, 'status' TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'config' ('chat_id' INT NOT NULL, 'config_name' TEXT NOT NULL, 'config_group' TEXT NOT NULL, 'config_value' TEXT NOT NULL, 'config_description' TEXT NOT NULL, 'config_type' TEXT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS 'welcome_message' ('welcome_message' TEXT NOT NULL, 'chat_id' INTEGER NOT NULL)")

    # Create Default Config Values if they don't exist
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"roll_enabled","Roll","yes","Toggles the /roll function - options are Yes/No","boolean",chat_id,"roll_enabled"))
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"reputation_enabled","Harry Potter","yes","Toggles the +/- reputation system - options are Yes/No","boolean",chat_id,"reputation_enabled"))
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"marvin_sass_enabled","Marvin","yes","Toggles Marvins random chatter and poll comments - options are Yes/No","boolean",chat_id,"marvin_sass_enabled"))
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"marvin_sass_frequency","Marvin","250","How many messages between Marvin chatter","int",chat_id,"marvin_sass_frequency"))
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"standard_characters_enabled","Harry Potter","yes","Toggles Standard HP Characters appearances. reputation_enabled must be Yes.","boolean",chat_id,"standard_characters_enabled"))
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"standard_characters_frequency","Harry Potter","500","How many messages between Standard characters appearance","int",chat_id,"standard_characters_frequency"))
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"epic_characters_enabled","Harry Potter","yes","Toggles Epic HP Characters appearances. reputation_enabled must be Yes.","boolean",chat_id,"epic_characters_enabled"))
    cursor.execute("INSERT INTO config(chat_id,config_name,config_group,config_value,config_description,config_type) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS(SELECT 1 FROM config WHERE chat_id = ? AND config_name = ?);",(chat_id,"epic_characters_frequency","Harry Potter","1200","How many messages between Epic characters appearance","int",chat_id,"epic_characters_frequency"))
    cursor.execute("INSERT INTO welcome_message(welcome_message,chat_id) SELECT ?, ? WHERE NOT EXISTS(SELECT 1 FROM welcome_message WHERE chat_id = ?);",("",chat_id,chat_id))
    

# HELPERS
# Make timestamps pretty again
#
def pretty_date(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    now = datetime.now()
    if type(time) is int:
        if datetime.fromtimestamp(time) < now:
            diff = now - datetime.fromtimestamp(time)
            future = False
        elif datetime.fromtimestamp(time) > now:
            diff = datetime.fromtimestamp(time) - now
            future = True
    elif isinstance(time,datetime):
        if time < now:
            diff = now - time
            future = False
        elif time > now:
            diff = time - now
            future = True
    elif not time:
        diff = now - now

    second_diff = diff.seconds
    day_diff = diff.days

    if future == False:
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
    elif future == True:
        if day_diff == 0:
            if second_diff < 10:
                return "in a few seconds"
            if second_diff < 60:
                return str(second_diff) + " seconds"
            if second_diff < 120:
                return "a minute"
            if second_diff < 3600:
                return str(second_diff // 60) + " minutes"
            if second_diff < 7200:
                return "an hour ago"
            if second_diff < 86400:
                return str(second_diff // 3600) + " hours"
        if day_diff == 1:
            return "Tomorrow"
        if day_diff < 7:
            return str(day_diff) + " days"
        if day_diff < 31:
            return str(day_diff // 7) + " weeks"
        if day_diff < 365:
            return str(day_diff // 30) + " months"
        return str(day_diff // 365) + " years"        

def add_values_in_dict(sample_dict, key, list_of_values):
    # Append multiple values to a key in the given dictionary
    if key not in sample_dict:
        sample_dict[key] = list()
    sample_dict[key].extend(list_of_values)
    return sample_dict

# Help Functionality
# /help prompts the user to talk directly to the bot and issue the /start command which shows the full help context
# Contents of the help message sent to users is stored in helpText.txt
def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))

    chat_id = str(update.message.chat_id)
    user_detail = activity_status_check(context.bot.id,chat_id,context)
    messageinfo = context.bot.send_message(chat_id, text="To get help, PM me  @" + user_detail[1].user.mention_markdown() + " and send me the Start or /start command", parse_mode='markdown')
    log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    chat_id = str(update.message.chat_id)
    help_text = open('helpText.txt', encoding="utf8")
    context.bot.send_message(chat_id, text=help_text.read(), parse_mode='markdown')

# Trigger Functionality
# Allows users to create automatic responses to specied keywords. Creation is via '/add triggerWord -> triggerResponse'
# Deletion is via '/del triggerWord', a list of current triggers can be pulled via '/list' or '/listDetail which will PM the user.

def update_trigger_question(update: Update, context: CallbackContext, trigger_word, trigger_value,chat_id,timestamp,new_value) -> int:
    reply_keyboard = [['Yes', 'No']]

    messageinfo = update.message.reply_text(
        "Trigger already exists. \n\nCurrent value is: " + trigger_value,
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, selective=True, input_field_placeholder="Do you want to update "+ trigger_word + "?"
        ),
    )

    log_bot_message(messageinfo.message_id,chat_id,timestamp,long_duration,"TriggerQuestion","Unanswered",trigger_word,new_value)

def add_trigger_command(update: Update, context: CallbackContext) -> None:
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text

    if(chat_text.startswith("/add ")):
        pass
    else:
        chat_text = "/add " + chat_text

    # Validations.
    if(len(chat_text.split()) < 2):
        messageinfo = update.message.reply_text("Bad Arguments, create a trigger with: \n\n/add trigger " + separator + " trigger_response")
        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)
        return
    if(chat_text.find(separator, 1) == -1):
        messageinfo = update.message.reply_text("Separator not found, create a trigger with: \n\n/add trigger " + separator + " trigger_response")
        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)
        return

    rest_text = chat_text.split(' ', 1)[1]
    trigger_word = u'' + rest_text.split(separator)[0].strip().lower()
    trigger_word.encode('utf-8')
    trigger_response = u'' + rest_text.split(separator, 1)[1].strip()

    if(len(trigger_response) < 1):
        messageinfo = update.message.reply_text("Bad Arguments, create a trigger with: \n\n /add trigger " + separator + " trigger_response")
        log_bot_message(messageinfo.message_id,chat_id,timestamp)
        return
    if(len(trigger_response) > 3000):
        messageinfo = update.message.reply_text('Response too long. [chars > 3000]')
        log_bot_message(messageinfo.message_id,chat_id,timestamp)
        return
    
    # If this is a media trigger, prompt user for what they want to save
    # Response is captured in chat_image_polling()
    if(trigger_response.lower() == "media"):
        messageinfo = context.bot.send_message(chat_id,text=chat_text + "\n\nIt looks like you want to save a GIF, Image or Sticker for your trigger. Reply to this message inside 90 seconds with the content and I'll add it.")
        log_bot_message(messageinfo.message_id,chat_id,timestamp,long_duration,type="MediaTrigger")
        return

    # Does the trigger already exist? If yes, kick user out to a question otherwise go ahead and save the trigger
    # User reply is handled in chat_polling() and trigger saved directly there
    lookup = trigger_lookup(trigger_word,chat_id)
    if(lookup[0] == 1):
        question = update_trigger_question(update,context,trigger_word,lookup[1],chat_id,timestamp,trigger_response)
    elif(lookup[0] in [2,3,4]):
        messageinfo = update.message.reply_text("That trigger already exists and it's a " + lookup[2] + ". You'll need to delete it first with '/del " + trigger_word + "'")
    else:  
        # Save trigger for the group
        save_trigger(chat_id,trigger_word,trigger_response,timestamp,context)

def save_trigger(chat_id,trigger_word,trigger_response,timestamp,context,trigger_response_type = 'text',trigger_response_media_id = 'None') -> None:
    # Save trigger for the group
    lookup = trigger_lookup(trigger_word, chat_id)
    if lookup[0] == 1: 
        cursor.execute("UPDATE triggers SET trigger_response = ? WHERE trigger_word = ? AND chat_id = ? AND trigger_response_type = ? AND trigger_response_media_id = ?",(trigger_response, trigger_word, chat_id,trigger_response_type,trigger_response_media_id))
        db.commit()
        messageinfo = context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] updated.")
        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)
    elif lookup[0] == 0:
        cursor.execute("INSERT INTO triggers (trigger_word,trigger_response,chat_id,trigger_response_type,trigger_response_media_id) VALUES(?,?,?,?,?)",(trigger_word,trigger_response,chat_id,trigger_response_type,trigger_response_media_id))
        db.commit()
        messageinfo = context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] created.")
        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)

def del_trigger_command(update: Update, context: CallbackContext) -> None:
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))

    """Removes a trigger when the /del command is used"""
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text

    if(len(chat_text.split()) < 2):
        context.bot.send_message(chat_id, text="Bad Arguments")
        return
    trigger_word = chat_text.split(' ', 1)[1].strip().lower()

    lookup = trigger_lookup(trigger_word, chat_id)
    if lookup[0]in (1,2,3,4): 
        cursor.execute("DELETE FROM triggers WHERE trigger_word = ? AND chat_id = ?",(trigger_word,chat_id))
        db.commit()
        messageinfo = context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] deleted.")
        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)
    elif lookup[0] == 0:
        messageinfo = context.bot.send_message(chat_id, text="Trigger not found.")
        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)

def trigger_lookup(trigger_word, chat_id) -> None:
    select = cursor.execute("SELECT * from triggers WHERE trigger_word = ? AND chat_id = ?",(trigger_word,chat_id))
    rows = select.fetchall()
    
    if rows:
        for row in rows:
            if str(row['trigger_word']) == trigger_word and str(row['chat_id']) == chat_id:
                if row['trigger_response_type'] == "text":
                    return 1,row['trigger_response'],row['trigger_response_type']
                elif row['trigger_response_type'] == "gif":
                    return 2,row['trigger_response_media_id'],row['trigger_response_type']
                elif row['trigger_response_type'] == "photo":
                    return 3,row['trigger_response_media_id'],row['trigger_response_type']  
                elif row['trigger_response_type'] == "sticker":
                    return 4,row['trigger_response_media_id'],row['trigger_response_type']               
            else: 
                return 0
    else: 
        error = 'Something went wrong or trigger wasnt found'
        return 0, error

def list_trigger_command(update: Update, context: CallbackContext) -> None:
    chat_id = str(update.message.chat_id)

    select = cursor.execute("SELECT * from triggers WHERE chat_id = ? ORDER BY trigger_word ASC",(chat_id,))
    rows = select.fetchall()
    textTriggerList = []
    stickerTriggerList = []
    photoTriggerList = []
    gifTriggerList = []
    if rows:
        for row in rows:
            if row['trigger_response_type'] == "text":
                textTriggerList.append(row['trigger_word'])
            elif row['trigger_response_type'] == "sticker":
                stickerTriggerList.append(row['trigger_word'])
            elif row['trigger_response_type'] == "photo":
                photoTriggerList.append(row['trigger_word'])
            elif row['trigger_response_type'] == "gif":
                gifTriggerList.append(row['trigger_word'])
        textSentenceList = ", ".join(textTriggerList)
        stickerSentenceList = ", ".join(stickerTriggerList)
        photoSentenceList = ", ".join(photoTriggerList)
        gifSentenceList = ", ".join(gifTriggerList)
        context.bot.send_message(chat_id, text="*Text Trigger List:*\n" + textSentenceList + "\n\n*Sticker Trigger List:*\n" + stickerSentenceList + "\n\n*Image Trigger List:*\n" + photoSentenceList + "\n\n*GIF Trigger List:*\n" + gifSentenceList, parse_mode='markdown')
    else: 
        error = 'Something went wrong or trigger wasnt found'
        context.bot.send_message(chat_id, text="Hmm, doesn't look like this group has any triggers yet!")
        return 0, error

def list_trigger_detail_command(update: Update, context: CallbackContext) -> None:
    """Sends a message to the requester with the full detail of all triggers"""
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    select = cursor.execute("SELECT * from triggers WHERE chat_id = ? ORDER BY trigger_word ASC",(chat_id,))
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

# Activity Tracking Functionality
# /activity Returns a sorted list of inactive users in the last 3 days. Activity is updated any time the user sends a text post to the group.
# User can optionally request the full list of users with '/activity full' 
# activity_lookup and activity_status_check are helper functions which are used elsewhere in Marvin

def activity_command(update: Update, context: CallbackContext) -> None:
    """Pulls a list of users activity and sends to the group"""
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text
    user = update.effective_user

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
                timestamp = row[2]
                timestampObject = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                prettyDate = pretty_date(timestampObject)

                activityFull = prettyDate + " : *" + user_detail[1].user.mention_markdown_v2() + "* " 
                activityList.append(activityFull)

            if activity_type == "Standard":
                info_message = "To get the full chat activity list, use '/activity full'\n\n"
            else: 
                info_message = "To get the short chat activity list, use '/activity'\n\n"
        sentenceList = "\n".join(activityList)
        context.bot.send_message(chat_id, text="Activity List:\n\n" + info_message + sentenceList, parse_mode=ParseMode.MARKDOWN_V2)
    else: 
        error = 'Something went wrong or activity wasnt found'
        context.bot.send_message(chat_id, text="It's a busy little group! Everybody has been active in the last 2 days. If you want the full chat list, use '/activity full'", parse_mode='markdown')
        return 0, error

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

# Harry Potter House Functionality
# Points reputation system. Points are awarded with either +/- or via /points @username <pointsTotal>
# Users are assigned to houses with /sortinghat @username <houseName>, and the current House list is pulled with just /sortinghat
# Points are tracked on a 'term' basis where a term length is defined in your .env file. End of term notices and points reset are automatic.
# Character Appearances - two tiers, Standard and Epic, Standard Characters allocate/remove up to 10 points with the exception of the Golden Snitch which awards 20.
# Character Appearances - Epic Characters are more devastating and also rarer, their impacts can completely wipe house points, swap them etc. 

def hp_assign_house(update: Update, context: CallbackContext) -> None:
    chat_id = str(update.message.chat_id)
    command = update.message.text.split()
    if len(command) == 3:
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
            context.bot.send_message(chat_id, text="Did you Avada Kedavra someone?\n\nI didn't find that username in my database. Most likely they haven't set a username in Telegram yet. Either that or they haven't spoken before or you typo'd it.", parse_mode='markdown')    
    elif len(command) == 2:
        select = cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE AND chat_id = ?",(command[1][1:],chat_id))
        rows = select.fetchone()
        if rows:
            user_detail = activity_status_check(rows[0],rows[1],context)
            if rows[4].lower() == "gryffindor":
                context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " is a Gryffindor! 🦁", parse_mode='markdown')            
            elif rows[4].lower() == "slytherin":
                context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " is a Slytherin! 🐍", parse_mode='markdown')  
            elif rows[4].lower() == "hufflepuff":
                context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " is a Hufflepuff! 🦡", parse_mode='markdown')  
            elif rows[4].lower() == "ravenclaw":
                context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " is a Ravenclaw! 🦅", parse_mode='markdown') 
            elif rows[4].lower() == "houseelf":
                context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " is a House Elf! 🧝‍♀️", parse_mode='markdown') 
        else: 
            context.bot.send_message(chat_id, text="Oops they don't have a house yet. Go to https://www.wizardingworld.com/news/discover-your-hogwarts-house-on-wizarding-world to find yours then do:\n\n /sortinghat <YourUsername> <YourHouse>'", parse_mode='markdown')
    elif len(command) == 1:
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
                if user_detail[0] != 0:
                    if row[4] == "Gryffindor":
                        gryffindor.append(user_detail[1].user.mention_markdown())
                    elif row[4] == "Slytherin":
                        slytherin.append(user_detail[1].user.mention_markdown())
                    elif row[4] == "Hufflepuff":
                        hufflepuff.append(user_detail[1].user.mention_markdown())
                    elif row[4] == "Ravenclaw":
                        ravenclaw.append(user_detail[1].user.mention_markdown())
                    elif row[4] == "Houseelf":
                        houseelf.append(user_detail[1].user.mention_markdown())
                    else:
                        muggles.append(user_detail[1].user.mention_markdown())
            
            sentenceGryffindor = ", ".join(gryffindor)
            sentenceSlytherin = ", ".join(slytherin)
            sentenceHufflepuff = ", ".join(hufflepuff)
            sentenceRavenclaw = ", ".join(ravenclaw)
            sentenceHouseelf = ", ".join(houseelf)
            sentenceMuggles = ", ".join(muggles)

            context.bot.send_message(chat_id, text="🦁 GRYFFINDOR 🦁\n" + sentenceGryffindor + "\n\n🦡 HUFFLEPUFF 🦡\n" + sentenceHufflepuff + "\n\n🐍 SLYTHERIN 🐍\n" + sentenceSlytherin + "\n\n🦅 RAVENCLAW 🦅\n" + sentenceRavenclaw + "\n\n🧝‍♀️ HOUSE ELVES 🧝‍♀️\n" + sentenceHouseelf + "\n\n❌ FILTHY MUGGLES ❌\n" + sentenceMuggles + "\n\nDon't want to be a filthy muggle? Take the test on the official Harry Potter website and then: \n\n'/sortinghat @yourusername yourhousename' ", parse_mode='markdown')
    else:
        context.bot.send_message(chat_id, text="You dare use my spells against me? You did it wrong anyway\. \n\n Sort someone into their house with:\n '/sortinghat @username <houseName>'\n\nHouse options are:\n Gryffindor, Slytherin, Hufflepuff, Ravenclaw, HouseElf", parse_mode='markdown')

def hp_term_tracker(chat_id, context) -> None:
    chat_id = chat_id
    time = datetime.now()
    time_plus = time + timedelta(days=int(TERMLENGTH))
    timestamp_now = str(time.strftime("%Y-%m-%d %H:%M:%S"))
    timestamp_plus = str(time_plus.strftime("%Y-%m-%d %H:%M:%S"))

    select = cursor.execute("SELECT * FROM hp_terms WHERE is_current = 1 AND chat_id = ?",(chat_id,))
    rows = select.fetchone()
    if rows:
        term_id = rows[1]
        # Is the term still current?
        if timestamp_now < rows[3]:
            pass
        else:
            # Pull back final totals & send results to group
            term_id = rows[1]
            term_end = rows[3]
            results = hp_totals(chat_id, term_id, term_end, timestamp_now, context, "EndTerm")
            # Update past winners
            winning_house = results[0]
            house_points_total = results[1]
            house_champion = results[2]
            champion_points_total = results[3]
            select = cursor.execute("SELECT * FROM hp_past_winners WHERE chat_id = ?",(chat_id,))
            rows = select.fetchone()
            if rows:
                cursor.execute("UPDATE hp_past_winners SET winning_house = ?, house_points_total = ?, house_champion = ?, champion_points_total = ? WHERE chat_id = ?",(winning_house,house_points_total,house_champion,champion_points_total,chat_id))
                db.commit()
            else: 
                cursor.execute("INSERT INTO hp_past_winners (chat_id,winning_house,house_points_total,house_champion,champion_points_total) VALUES(?,?,?,?,?)",(chat_id,winning_house,house_points_total,house_champion,champion_points_total))
                db.commit()
            # Close old term
            cursor.execute("UPDATE hp_terms SET is_current = ? WHERE chat_id = ? AND term_id = ?",(0,chat_id, term_id))
            # Start new term
            cursor.execute("INSERT INTO hp_terms (chat_id, term_id, start_date, end_date, is_current) VALUES(?,?,?,?,1)",(chat_id,str(uuid.uuid4()),timestamp_now,timestamp_plus))
            db.commit()

        # If the term is no longer current, publish results and start a new term

    else:
        # First ever term!
        term_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO hp_terms (chat_id, term_id, start_date, end_date, is_current) VALUES(?,?,?,?,1)",(chat_id,term_id,timestamp_now,timestamp_plus))
        db.commit()
    
    return term_id

def hp_get_user_house(chat_id,user_id) -> None:
    select = cursor.execute("SELECT hp_house FROM users WHERE chat_id = ? and user_id = ?",(chat_id,user_id))
    user = select.fetchone()
    if user[0] == "Gryffindor":
        house = "🦁"
    elif user[0] == "Slytherin":
        house = "🐍"
    elif user[0] == "Hufflepuff":
        house = "🦡"
    elif user[0] == "Ravenclaw":
        house = "🦅"
    elif user[0] == "Houseelf":
        house = "🧝‍♀️"
    else: 
        house = "❌"
    
    return house

def hp_points(update,context,chat_id,timestamp) -> None:
    # Get Current Term
    select = cursor.execute("SELECT * FROM hp_terms WHERE is_current = 1 AND chat_id = ?",(chat_id,))
    rows = select.fetchone()
    term_id = rows[1]
    positive = ["+","❤️","😍","👍"]
    negative = ["-","😡","👎"]
    
    to_user_id = update.message.reply_to_message.from_user.id
    from_user_id = update.message.from_user.id

    # Get Sender & Target Users House
    senderHouse = hp_get_user_house(chat_id,from_user_id)
    receiverHouse = hp_get_user_house(chat_id,to_user_id)

    # Rules Check
    outcome = hp_rules_checker(chat_id,context,to_user_id)

    # Check if message was positive or not
    if update.message.text in positive:
        if outcome[0] == "bellatrix_block":
            messageinfo = context.bot.send_message(chat_id, text="*The house of " + receiverHouse + " is cursed by Bellatrix*!\n\n" + receiverHouse + " can't receive points. The curse ends in around " + pretty_date(outcome[1]), parse_mode='markdown')
            log_bot_message(messageinfo.message_id,chat_id,outcome[1], short_duration)
        else: 
            hp_allocate_points(chat_id,timestamp,to_user_id,term_id,"positive",1,"from_user",update,context,senderHouse,receiverHouse)
    elif update.message.text in negative:
        hp_allocate_points(chat_id,timestamp,to_user_id,term_id,"negative",-1,"from_user",update,context,senderHouse,receiverHouse)

def hp_allocate_points(chat_id,timestamp,to_user_id,term_id,positive_negative,points_allocated,from_who,update,context,senderHouse=None,receiverHouse=None) -> None:

    # Get Current Points
    select = cursor.execute("SELECT points FROM hp_points WHERE chat_id = ? AND term_id = ? and user_id = ?",(chat_id,term_id,to_user_id))
    rows = select.fetchone()

    # Rules Check
    outcome = hp_rules_checker(chat_id,context,to_user_id)
    if outcome[0] == "dumbledore_boost" and positive_negative == "positive":
        points_allocated = points_allocated * 2

    if rows:
        current_points = rows[0]
        current_points += points_allocated
        cursor.execute("UPDATE hp_points SET points = ?, timestamp = ? WHERE user_id = ? AND chat_id = ? AND term_id = ?",(current_points,timestamp,to_user_id,chat_id,term_id))
        db.commit()
    else: 
        current_points = points_allocated    
        cursor.execute("INSERT INTO hp_points (user_id, chat_id, points, timestamp, term_id) VALUES(?,?,?,?,?)",(to_user_id,chat_id,current_points,timestamp,term_id))
        db.commit()
    
    if from_who == "from_user" and positive_negative == "positive":
        if points_allocated > 1:
            messageinfo = context.bot.send_message(chat_id, text=update.message.from_user.mention_markdown() + " of " + senderHouse + " has awarded " + update.message.reply_to_message.from_user.mention_markdown() + " of " + receiverHouse + " " + str(points_allocated) + " House points due to the *Engorgio* spell cast by *Dumbledore*!\n\nTheir new total for this Term is: " + str(current_points), parse_mode='markdown')
        else:
            messageinfo = context.bot.send_message(chat_id, text=update.message.from_user.mention_markdown() + " of " + senderHouse + " has awarded " + update.message.reply_to_message.from_user.mention_markdown() + " of " + receiverHouse + " a House point!\nTheir new total for this Term is: " + str(current_points), parse_mode='markdown')
        log_bot_message(messageinfo.message_id,chat_id,timestamp)
    elif from_who == "from_user" and positive_negative == "negative":
        messageinfo = context.bot.send_message(chat_id, text=update.message.from_user.mention_markdown() + " of " + senderHouse + " has deducted " + update.message.reply_to_message.from_user.mention_markdown() + " of " + receiverHouse + " a House point!\nTheir new total for this Term is: " + str(current_points), parse_mode='markdown' )
        log_bot_message(messageinfo.message_id,chat_id,timestamp)
    
    return current_points

def hp_points_admin(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    user_detail = activity_status_check(user_id,chat_id,context)
    user_status = user_detail[0]
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))

    # Get Current Term
    select = cursor.execute("SELECT * FROM hp_terms WHERE is_current = 1 AND chat_id = ?",(chat_id,))
    rows = select.fetchone()
    term_id = rows[1]
    term_end = rows[3]
    term_endObject = datetime.strptime(term_end, '%Y-%m-%d %H:%M:%S')
    prettyDate = pretty_date(term_endObject)

    if len(update.message.text.split()) == 3:
        if user_status in ("creator","administrator"):
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
                    receiverHouse = hp_get_user_house(chat_id,user_detail[1].user.id)

                    # Get Current Points                   
                    if int(command[2]) > 0:
                        outcome = hp_rules_checker(chat_id,context,user_detail[1].user.id)
                        if outcome[0] == "bellatrix_block":
                            messageinfo = context.bot.send_message(chat_id, text="*The house of " + receiverHouse + " is cursed by Bellatrix*!\n\n" + receiverHouse + " can't receive points. The curse ends in around " + pretty_date(outcome[1]), parse_mode='markdown')
                            log_bot_message(messageinfo.message_id,chat_id,outcome[1], short_duration)
                        elif outcome[0] == "dumbledore_boost":
                            current_points = hp_allocate_points(chat_id,timestamp,user_detail[1].user.id,term_id,"positive",int(command[2]),"from_admin",update,context,None,receiverHouse)
                            messageinfo = context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " of " + receiverHouse + " has been awarded " + str(int(command[2]) * 2) + " House points due to the *Engorgio* spell cast by *Dumbledore*!\nTheir new total for this Term is: " + str(current_points),parse_mode='markdown' )
                            log_bot_message(messageinfo.message_id,chat_id,timestamp)
                        else:
                            current_points = hp_allocate_points(chat_id,timestamp,user_detail[1].user.id,term_id,"positive",int(command[2]),"from_admin",update,context,None,receiverHouse)
                            messageinfo = context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " of " + receiverHouse + " has been awarded " + str(command[2]) + " House points!\nTheir new total for this Term is: " + str(current_points),parse_mode='markdown' )
                            log_bot_message(messageinfo.message_id,chat_id,timestamp)
                    elif int(command[2]) == 0:
                        messageinfo = context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " of " + receiverHouse + " has been um ... awarded no extra House points.",parse_mode='markdown' )
                        log_bot_message(messageinfo.message_id,chat_id,timestamp)
                    else:
                        current_points = hp_allocate_points(chat_id,timestamp,user_detail[1].user.id,term_id,"negative",int(command[2]),"from_admin",update,context,None,receiverHouse)
                        messageinfo = context.bot.send_message(chat_id, text=user_detail[1].user.mention_markdown() + " of " + receiverHouse + " has been deducted " + str(command[2]) + " House points!\nTheir new total for this Term is: " + str(current_points),parse_mode='markdown' )
                        log_bot_message(messageinfo.message_id,chat_id,timestamp)
                else: 
                    messageinfo = context.bot.send_message(chat_id, text="Hmm, that user doesn't seem to exist.",parse_mode='markdown' )
                    log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)
        else:
            messageinfo = context.bot.send_message(chat_id, text="Yer not a Wizard Harry ... or ... an Admin ... " + user_detail[1].user.mention_markdown(), parse_mode='markdown')
            log_bot_message(messageinfo.message_id,chat_id,timestamp)
    elif len(update.message.text.split()) == 2:
        # Fetch House Totals and House Champions
        command = update.message.text.split()
        if command[1] == 'totals':
            hp_totals(chat_id, term_id, term_end, timestamp, context)
        else:
            messageinfo = context.bot.send_message(chat_id, text="Admin Only: \n/points @username <pointsTotal>\n\nAll Users:\n/points totals")
            log_bot_message(messageinfo.message_id,chat_id,timestamp)
    elif len(update.message.text.split()) == 1:
        hp_totals(chat_id, term_id, term_end, timestamp, context)
    else: 
        messageinfo = context.bot.send_message(chat_id, text="Admin Only: \n/points @username <pointsTotal>\n\nAll Users:\n/points totals")
        log_bot_message(messageinfo.message_id,chat_id,timestamp)

def hp_totals(chat_id, term_id, term_end, timestamp, context, query_type="Standard") -> None:
    term_endObject = datetime.strptime(term_end, '%Y-%m-%d %H:%M:%S')
    prettyDate = pretty_date(term_endObject)

    points_Gryffindor = 0
    points_Slytherin = 0
    points_Hufflepuff = 0
    points_Ravenclaw = 0
    points_Houseelf = 0
    points_Muggles = 0

    # Grab the points totals for the current term
    select = cursor.execute("SELECT * FROM hp_points WHERE chat_id = ? AND term_id = ?",(chat_id,term_id))
    rows = select.fetchall()
    if rows:
        for row in rows:
            user_detail = activity_status_check(row[0],chat_id,context)
            if user_detail[0] != 0:
                user_status = (context.bot.get_chat_member(chat_id,user_detail[1].user.id)).status
                if user_status in ("member","creator","administrator"):
                    user_house = cursor.execute("SELECT hp_house FROM users WHERE chat_id = ? AND user_id = ?",(chat_id,user_detail[1].user.id))
                    user_house = user_house.fetchone()
                    user_points = row[2]

                    if user_house[0] == "Gryffindor":
                        points_Gryffindor += user_points
                    elif user_house[0] == "Slytherin":
                        points_Slytherin += user_points
                    elif user_house[0] == "Hufflepuff":
                        points_Hufflepuff += user_points
                    elif user_house[0] == "Ravenclaw":
                        points_Ravenclaw += user_points
                    elif user_house[0] == "Houseelf":
                        points_Houseelf += user_points
                    else: 
                        points_Muggles += user_points
                else: 
                    cursor.execute("UPDATE users SET status = 'left' WHERE user_id = ? AND chat_id = ?",(str(user_detail[1].user.id),chat_id))
                    db.commit()


        # Create points list, sort it, format it.
        points_list = {"🦁 : ": points_Gryffindor, "🐍 : ": points_Slytherin, "🦡 : ": points_Hufflepuff, "🦅 : ": points_Ravenclaw, "🧝‍♀️ : ": points_Houseelf}
        points_list = dict(sorted(points_list.items(), key=lambda item: item[1], reverse=True))
        sentenceHouse = ""

        for key, value in points_list.items():
            sentenceHouse += key + str(value) + "\n"

        # Get House Champion for each House
        select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE hp_points.term_id = ? AND users.hp_house = 'Gryffindor' AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (term_id,))
        rows = select.fetchone()
        if rows:
            gryffindor_champion_points = f"({rows[2]})"
            gryffindor_user_detail = activity_status_check(rows[0],rows[3],context)
            gryffindor_sentence = gryffindor_user_detail[1].user.mention_markdown()
        else:
            gryffindor_champion_points = " "
            gryffindor_sentence = "Nobody yet!" 

        select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE hp_points.term_id = ? AND users.hp_house = 'Slytherin' AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (term_id,))
        rows = select.fetchone()
        if rows:
            slytherin_champion_points = f"({rows[2]})"
            slytherin_user_detail = activity_status_check(rows[0],rows[3],context)
            slytherin_sentence = slytherin_user_detail[1].user.mention_markdown()
        else: 
            slytherin_champion_points = " "
            slytherin_sentence = "Nobody yet!" 

        select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE hp_points.term_id = ? AND users.hp_house = 'Hufflepuff' AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (term_id,))
        rows = select.fetchone()
        if rows:
            hufflepuff_champion_points = f"({rows[2]})"
            hufflepuff_user_detail = activity_status_check(rows[0],rows[3],context)
            hufflepuff_sentence = hufflepuff_user_detail[1].user.mention_markdown()
        else: 
            hufflepuff_champion_points = " "
            hufflepuff_sentence = "Nobody yet!" 

        select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE hp_points.term_id = ? AND users.hp_house = 'Ravenclaw' AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (term_id,))
        rows = select.fetchone()
        if rows:
            ravenclaw_champion_points = f"({rows[2]})"
            ravenclaw_user_detail = activity_status_check(rows[0],rows[3],context)
            ravenclaw_sentence = ravenclaw_user_detail[1].user.mention_markdown()
        else: 
            ravenclaw_champion_points = " "
            ravenclaw_sentence = "Nobody yet!" 

        select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE hp_points.term_id = ? AND users.hp_house = 'Houseelf' AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (term_id,))
        rows = select.fetchone()
        if rows:
            houseelf_champion_points = f"({rows[2]})"
            houseelf_user_detail = activity_status_check(rows[0],rows[3],context)
            houseelf_sentence = houseelf_user_detail[1].user.mention_markdown()
        else: 
            houseelf_champion_points = " "
            houseelf_sentence = "Nobody yet!" 

        # Finished, send message to users
        if query_type == "Standard":
            # Get last terms winner
            select = cursor.execute("SELECT * FROM hp_past_winners WHERE chat_id = ?",(chat_id,))
            rows = select.fetchone()
            if rows:
                messageinfo = context.bot.send_message(chat_id, text=f"🏰 *House Points Totals* 🏰\n{sentenceHouse}\nPoints wasted by Filthy Muggles: {points_Muggles}\n\n⚔️*Current House Champions*⚔️\n🦁: {gryffindor_sentence} {gryffindor_champion_points}\n🐍: {slytherin_sentence} {slytherin_champion_points}\n🦡: {hufflepuff_sentence} {hufflepuff_champion_points}\n🦅: {ravenclaw_sentence} {ravenclaw_champion_points}\n🧝‍♀️: {houseelf_sentence} {houseelf_champion_points}\n\n*Last Terms Winning House & Champion:*\n{rows[1]}\n{rows[3]} with {rows[4]} points!\n\n*This term ends in {prettyDate}*", parse_mode="Markdown")
            else:
                messageinfo = context.bot.send_message(chat_id, text=f"🏰 *House Points Totals* 🏰\n{sentenceHouse}\nPoints wasted by Filthy Muggles: {points_Muggles}\n\n⚔️*Current House Champions*⚔️\n🦁: {gryffindor_sentence} {gryffindor_champion_points}\n🐍: {slytherin_sentence} {slytherin_champion_points}\n🦡: {hufflepuff_sentence} {hufflepuff_champion_points}\n🦅: {ravenclaw_sentence} {ravenclaw_champion_points}\n🧝‍♀️: {houseelf_sentence} {houseelf_champion_points}\n\n*This term ends in {prettyDate}*", parse_mode="Markdown")
        # If End of Term do other stuff
        elif query_type == "EndTerm":
            house_champion_points = list(points_list.values())[0]
            if list(points_list)[0] == "🦁 : ":
                house_champion = "🦁 Gryffindor! 🦁"
                house_champion_user = gryffindor_user_detail[1].user.mention_markdown()
                house_champion_user_points = gryffindor_champion_points
                house_champion_points = points_Gryffindor

            elif list(points_list)[0] == "🐍 : ":
                house_champion = "🐍 Slytherin! 🐍"
                house_champion_user = slytherin_user_detail[1].user.mention_markdown()
                house_champion_user_points = slytherin_champion_points
                house_champion_points = points_Slytherin

            elif list(points_list)[0] == "🦡 : ":
                house_champion = "🦡 Hufflepuff! 🦡"
                house_champion_user = hufflepuff_user_detail[1].user.mention_markdown()
                house_champion_user_points = hufflepuff_champion_points
                house_champion_points = points_Hufflepuff

            elif list(points_list)[0] == "🦅 : ":
                house_champion = "🦅 Ravenclaw! 🦅"
                house_champion_user = ravenclaw_user_detail[1].user.mention_markdown()
                house_champion_user_points = ravenclaw_champion_points
                house_champion_points = points_Ravenclaw

            elif list(points_list)[0] == "🧝‍♀️ : ":
                house_champion = "🧝‍♀️ House Elves! 🧝‍♀️"
                house_champion_user = houseelf_user_detail[1].user.mention_markdown()
                house_champion_user_points = houseelf_champion_points
                house_champion_points = points_Houseelf

            messageinfo = context.bot.send_message(chat_id, text=f"✨✨✨ *END OF TERM!* ✨✨✨\n\nThe winner of this terms House Cup with a total of *{house_champion_points} points* ...\n\n{house_champion}\n\nAlso a huge congratulations to each of this terms ... \n\n⚔️*House Champions*⚔️\n🦁: {gryffindor_sentence} {gryffindor_champion_points}\n🐍: {slytherin_sentence} {slytherin_champion_points}\n🦡: {hufflepuff_sentence} {hufflepuff_champion_points}\n🦅: {ravenclaw_sentence} {ravenclaw_champion_points}\n🧝‍♀️: {houseelf_sentence} {houseelf_champion_points}\n\n*Points have been reset and a new term has begun!*", parse_mode="Markdown")
            context.bot.pin_chat_message(chat_id,messageinfo.message_id)
            return house_champion, house_champion_points, house_champion_user, house_champion_user_points
        elif query_type == "GeneralTotals":
            return points_list
        log_bot_message(messageinfo.message_id,chat_id,timestamp,9000)
    else: 
        messageinfo = context.bot.send_message(chat_id, text="It appears nobody has earned any points this term!")
        log_bot_message(messageinfo.message_id,chat_id,timestamp)

def hp_tags(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    user_detail = activity_status_check(user_id,chat_id,context)
    user_status = user_detail[0]
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))

    if user_status in ("creator","administrator"):
        if len(update.message.text.split()) == 4:
            command = update.message.text.split()
            if "#" in command[1] and command[2].isdigit() and command[3].isdigit():
                points = int(command[2])
                limit = int(command[3])
                if points > 20 or points < 1:
                    messageinfo = context.bot.send_message(chat_id, text="Points need to be between 1 and 20", parse_mode='markdown')
                else:
                    messageinfo = context.bot.send_message(chat_id, text=f"Tag Name: {command[1]}\n Points Awarded: {points}\n Limit per day: {limit}", parse_mode='markdown')
            elif "delete" in command[1].lower():
                if "#" in command[2]:
                    messageinfo = context.bot.send_message(chat_id, text="Delete command found, do something", parse_mode='markdown')
                else:
                    messageinfo = context.bot.send_message(chat_id, text="Didn't find a tag to delete.", parse_mode='markdown')
            else:
                messageinfo = context.bot.send_message(chat_id, text="Something isn't right or you provided a negative points total. Command options are:\n\n/tags #tagname <pointsTotal>\n/tags delete #tagname", parse_mode='markdown')
        else:
            messageinfo = context.bot.send_message(chat_id, text="Something isn't right or you provided a negative points total. Command options are:\n\n/tags #tagname <pointsTotal>\n/tags delete #tagname", parse_mode='markdown')
    else: 
        messageinfo = context.bot.send_message(chat_id, text="Yer not a Wizard Harry ... or ... an Admin ... " + user_detail[1].user.mention_markdown(), parse_mode='markdown')
        log_bot_message(messageinfo.message_id,chat_id,timestamp)

def hp_character_appearance(chat_id,update,context,timestamp,term_id,user=False,standard_or_epic = "Standard") -> None:

    if user == False:
        if standard_or_epic == "Standard":
            hp_random_character(chat_id,context,update,timestamp,term_id,standard_or_epic)
        elif standard_or_epic == "Epic":
            hp_random_character(chat_id,context,update,timestamp,term_id,standard_or_epic)

    elif user == True:
        # Used to handle user responses to game prompts
        if update.message.reply_to_message:
            receiverHouse = hp_get_user_house(chat_id,update.message.from_user.id)
            chat_text = update.message.text
            reply_message_id = update.message.reply_to_message.message_id

            # Check if Message ID is still valid
            select = cursor.execute("SELECT * FROM bot_service_messages WHERE chat_id = ? AND message_id = ?",(chat_id,reply_message_id))
            row = select.fetchone()
            if row:
                # Message exists
                # Which game is it related to?
                if row[5] == "Snitch":
                    if chat_text.lower() == "caught it!" and row[3] == "open":
                        current_points = hp_allocate_points(chat_id,timestamp,update.message.from_user.id,term_id,"positive",20,"from_admin",update,context,None,receiverHouse)
                        context.bot.send_message(chat_id, text="🥇 " + update.message.from_user.mention_markdown() + " *of " + receiverHouse + " caught the Golden Snitch!* 🥇\n\nThey have received 20 points.\n\nTheir new total for this term is " + str(current_points), parse_mode='markdown')
                        cursor.execute("UPDATE bot_service_messages SET status = ? WHERE chat_id = ? AND message_id = ?",("closed",chat_id,reply_message_id))
                        db.commit()
                    elif row[3] == "closed":
                        messageinfo = context.bot.send_message(chat_id, text="Looks like you could use a Nimbus 2000 " + update.message.from_user.mention_markdown() + "\n\nThis Snitch has already been caught!", parse_mode='markdown')
                        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)
                    else: 
                        messageinfo = context.bot.send_message(chat_id, text=update.message.from_user.mention_markdown() + "leaps for the Golden Snitch and ... falls on their keyboard with a typo!", parse_mode='markdown')
                        log_bot_message(messageinfo.message_id,chat_id,timestamp,short_duration)

            else:
                # Message no longer exists, do nothing (or maybe let the user know? Not sure yet.)
                pass

def hp_random_character(chat_id,context,update,timestamp,term_id,standard_or_epic) -> None:
    total_standard_characters = 7
    random_standard_char = random.randint(1, total_standard_characters)
    
    total_epic_characters = 4
    random_epic_char = random.randint(1, total_epic_characters)

    # Get the sticker set(s) to pull associated file_id's

    # Main Sticker Set
    sticker_set = context.bot.get_sticker_set("BoyWhoLived")
    for sticker in sticker_set.stickers:
        if sticker.emoji == "✊️":
            snitch_file_id = sticker.file_id 
        elif sticker.emoji == "😒":
            snape_file_id = sticker.file_id 
        elif sticker.emoji == "😜":
            slughorn_file_id = sticker.file_id 
        elif sticker.emoji == "👍":
            harry_file_id = sticker.file_id 
        elif sticker.emoji == "🔮":
            trelawney_file_id = sticker.file_id 
        elif sticker.emoji == "😁":
            umbridge_file_id = sticker.file_id
        elif sticker.emoji == "😉":
            buckbeak_file_id = sticker.file_id
        elif sticker.emoji == "😎":
            dumbledore_file_id = sticker.file_id
        elif sticker.emoji == "🖕":
            bellatrix_file_id = sticker.file_id
    
    # Extra Ones Made Manually
    sticker_set = context.bot.get_sticker_set("PotterAdditional")
    for sticker in sticker_set.stickers:
        if sticker.emoji == "👾":
            troll_file_id = sticker.file_id

    # Voldemort Extras
    sticker_set = context.bot.get_sticker_set("Lord_Voldemort")
    for sticker in sticker_set.stickers:
        if sticker.emoji == "😂":
            voldemort_file_id = sticker.file_id

    # Get Most Recent Message ID
    select = cursor.execute("SELECT * FROM bot_service_messages WHERE chat_id = ? AND type = ?",(chat_id,"MostRecent"))
    row = select.fetchone()
    if row:
        most_recent_message_id = row[1]
        most_recent_user_id = row[3]
        receiverHouse = hp_get_user_house(chat_id,most_recent_user_id)
    user_detail = activity_status_check(most_recent_user_id,chat_id,context)

    if standard_or_epic == "Standard":
        # Random STANDARD Characters
        if random_standard_char == 1:
            # Golden Snitch Game
            # Reply logic for Snitch game is in hp_character_appearance()
            messageinfo = context.bot.send_sticker(chat_id, sticker=snitch_file_id)
            log_bot_message(messageinfo.message_id,chat_id,timestamp,172800,"Snitch_Sticker","open")
            messageinfo = context.bot.send_message(chat_id, text="*Quick!\n\nThe Golden Snitch just flew past your head!*\n\n_Reply to this message_ with '*CAUGHT IT!*' to catch it!", parse_mode='markdown')
            log_bot_message(messageinfo.message_id,chat_id,timestamp,172800,"Snitch","open")
        elif random_standard_char == 2:
            # Snape Unimpressed
            current_points = hp_allocate_points(chat_id,timestamp,most_recent_user_id,term_id,"negative",-10,"from_admin",update,context,None,receiverHouse)
            context.bot.send_sticker(chat_id, sticker=snape_file_id, reply_to_message_id=most_recent_message_id)
            messageinfo = context.bot.send_message(chat_id, text="*Professor Snape is unimpressed!\n\n*He deducts 10 points from " + user_detail[1].user.mention_markdown() + "of " + receiverHouse + "\n\nTheir new total for the term is " + str(current_points), parse_mode='markdown')
        elif random_standard_char == 3:
            # Trelawney
            # Get Random User ID for Trelawney because she's a bit weird
            select = cursor.execute("SELECT * FROM users WHERE chat_id = ? AND status NOT IN ('kicked','left') ORDER BY RANDOM() LIMIT 1",(chat_id,))
            row = select.fetchone()
            if row:
                random_user_id = row[0]
                user_detail = activity_status_check(random_user_id,chat_id,context)
            current_points = hp_allocate_points(chat_id,timestamp,random_user_id,term_id,"positive",10,"from_admin",update,context,None,receiverHouse)
            context.bot.send_sticker(chat_id, sticker=trelawney_file_id)
            messageinfo = context.bot.send_message(chat_id, text="*Sybill Trelawney sees ... points ... in someones future ... but she's not sure ... who!?*\n\nShe randomly gives " + user_detail[1].user.mention_markdown() + " of " + receiverHouse + " 10 points!\n\nTheir new total for the term is " + str(current_points), parse_mode='markdown')
        elif random_standard_char == 4:
            # Umbridge
            current_points = hp_allocate_points(chat_id,timestamp,most_recent_user_id,term_id,"negative",-2,"from_admin",update,context,None,receiverHouse)
            context.bot.send_sticker(chat_id, sticker=umbridge_file_id, reply_to_message_id=most_recent_message_id)
            messageinfo = context.bot.send_message(chat_id, text="*Dolores Umbridge thinks *" + user_detail[1].user.mention_markdown() + "* of * " + receiverHouse + "* is a Muggle-Born!*\n\nShe deducts 2 points from them!\n\nTheir new total for the term is " + str(current_points), parse_mode='markdown')
        elif random_standard_char == 5:
            # Slughorn
            current_points = hp_allocate_points(chat_id,timestamp,most_recent_user_id,term_id,"positive",2,"from_admin",update,context,None,receiverHouse)
            context.bot.send_sticker(chat_id, sticker=slughorn_file_id, reply_to_message_id=most_recent_message_id)
            messageinfo = context.bot.send_message(chat_id, text="*Professor Slughorn thinks *" + user_detail[1].user.mention_markdown() + "* of * " + receiverHouse + " *looks lucky today!*\n\nHe awards them 2 points!\n\nTheir new total for the term is " + str(current_points), parse_mode='markdown')
        elif random_standard_char == 6:
            # Troll
            # Troll has wide area of effect, hits three people
            select = cursor.execute("SELECT * FROM users WHERE chat_id = ? AND status NOT IN ('kicked','left') ORDER BY RANDOM() LIMIT 3",(chat_id,))
            rows = select.fetchall()
            userList = []
            for row in rows:
                user_id = row[0]
                user_detail = activity_status_check(user_id,chat_id,context)
                current_points = hp_allocate_points(chat_id,timestamp,user_id,term_id,"negative",-5,"from_admin",update,context,None,receiverHouse)
                receiverHouse = hp_get_user_house(chat_id,user_id)
                sentence = user_detail[1].user.mention_markdown() + "* of * " + receiverHouse + " (New Total: " + str(current_points) + ")"
                userList.append(sentence)
            sentenceList = "\n".join(userList)
            context.bot.send_sticker(chat_id, sticker=troll_file_id)
            messageinfo = context.bot.send_message(chat_id, text="*TROLLLL IN THE DUNGEON!*\n\nHe swings his club and hits the following for 5 points:\n\n" + sentenceList, parse_mode='markdown')
        elif random_standard_char == 7:
            # Buckbeak
            # Troll has wide area of effect, hits three people
            select = cursor.execute("SELECT * FROM users WHERE chat_id = ? AND status NOT IN ('kicked','left') ORDER BY RANDOM() LIMIT 3",(chat_id,))
            rows = select.fetchall()
            userList = []
            for row in rows:
                user_id = row[0]
                user_detail = activity_status_check(user_id,chat_id,context)
                current_points = hp_allocate_points(chat_id,timestamp,user_id,term_id,"positive",5,"from_admin",update,context,None,receiverHouse)
                receiverHouse = hp_get_user_house(chat_id,user_id)
                sentence = user_detail[1].user.mention_markdown() + "* of * " + receiverHouse + " (New Total: " + str(current_points) + ")"
                userList.append(sentence)
            sentenceList = "\n".join(userList)
            context.bot.send_sticker(chat_id, sticker=buckbeak_file_id)
            messageinfo = context.bot.send_message(chat_id, text="*Buckbeak has landed nearby!*\n\nApproaching carefully, the following are granted 5 points:\n\n" + sentenceList, parse_mode='markdown')
    elif standard_or_epic == "Epic":
        if random_epic_char == 1:
            # Bellatrix
            #
            time_future = datetime.now() + timedelta(hours=4)
            time_future = str(time_future.strftime("%Y-%m-%d %H:%M:%S"))

            messageinfo = context.bot.send_sticker(chat_id, sticker=bellatrix_file_id)
            messageinfo = context.bot.send_message(chat_id, text="*Bellatrix has marked *" + user_detail[1].user.mention_markdown() + "* and the House of " + receiverHouse + "*\n\nThey can't receive points for 4 hours!", parse_mode='markdown')
            cursor.execute("INSERT INTO hp_config (chat_id, config_name, affected_entity, expiry_time) VALUES(?,?,?,?)",(chat_id, "bellatrix_block", receiverHouse, time_future))
            db.commit()
        elif random_epic_char == 2:
            # Dumbledore
            #
            time_future = datetime.now() + timedelta(hours=4)
            time_future = str(time_future.strftime("%Y-%m-%d %H:%M:%S"))

            messageinfo = context.bot.send_sticker(chat_id, sticker=dumbledore_file_id)
            messageinfo = context.bot.send_message(chat_id, text="*Dumbledore has cast Engorgio!*\n\n" + user_detail[1].user.mention_markdown() + "and the House of " + receiverHouse + " points are doubled for the next 4 hours!", parse_mode='markdown')
            cursor.execute("INSERT INTO hp_config (chat_id, config_name, affected_entity, expiry_time) VALUES(?,?,?,?)",(chat_id, "dumbledore_boost", receiverHouse, time_future))
            db.commit()
        elif random_epic_char == 3:
            # Voldemort
            #

            select = cursor.execute("SELECT * FROM hp_points WHERE chat_id = ? AND term_id = ? ORDER BY points DESC LIMIT 1",(chat_id,term_id))
            rows = select.fetchone()
            user_detail = activity_status_check(rows[0],chat_id,context)
            receiverHouse = hp_get_user_house(chat_id,rows[0])
            cursor.execute("UPDATE hp_points SET points = '0' WHERE chat_id = ? AND term_id = ? AND user_id = ?",(chat_id,term_id,rows[0]))
            db.commit()
            messageinfo = context.bot.send_sticker(chat_id, sticker=voldemort_file_id)
            messageinfo = context.bot.send_message(chat_id, text="*Voldemort has struck down *" + user_detail[1].user.mention_markdown() + " of " + receiverHouse + "\n\nThey did have the most points this term with " + str(rows[2]) + "\n\nTheir points have been set to zero!", parse_mode='markdown')
        elif random_epic_char == 4:
            # Harry
            #
            # Get Current Term
            select = cursor.execute("SELECT * FROM hp_terms WHERE is_current = 1 AND chat_id = ?",(chat_id,))
            rows = select.fetchone()
            term_id = rows[1]
            term_end = rows[3]

            # Get House Totals
            house_elf_sacrifice = False
            totals = hp_totals(chat_id,term_id,term_end,timestamp,context,"GeneralTotals")
            totals_items = list(totals.items())[3] # this should be the 4th house (0 = 1) 
            if totals_items[0] == "🧝‍♀️ : ":
                # House Elves aren't a real house ...
                totals_items = list(totals.items())[4]
                house_elf_sacrifice = True
            elif totals_items[0] == "🦁 : ":
                lowest_house = "Gryffindor"
            elif totals_items[0] == "🦅 : ":
                lowest_house = "Ravenclaw"
            elif totals_items[0] == "🐍 : ":
                lowest_house = "Slytherin"
            elif totals_items[0] == "🦡 : ":
                lowest_house = "Hufflepuff"

            # Get Highest Points User from House with Lowest Totals
            select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE users.hp_house = ? AND hp_points.term_id = ? AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (lowest_house,term_id,))
            rows = select.fetchone()
            # Possible that ^ this query returns nothing, if its early in the season it's possible only one or two houses have points so we repeat for the next nearest
            if rows == None:
                totals_items = list(totals.items())[2]
                if totals_items[0] == "🧝‍♀️ : ":
                    # House Elves aren't a real house ...
                    totals_items = list(totals.items())[4]
                    house_elf_sacrifice = True
                elif totals_items[0] == "🦁 : ":
                    lowest_house = "Gryffindor"
                elif totals_items[0] == "🦅 : ":
                    lowest_house = "Ravenclaw"
                elif totals_items[0] == "🐍 : ":
                    lowest_house = "Slytherin"
                elif totals_items[0] == "🦡 : ":
                    lowest_house = "Hufflepuff"
            select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE users.hp_house = ? AND hp_points.term_id = ? AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (lowest_house,term_id,))
            rows = select.fetchone()
            # Possible that ^ this query returns nothing, if its early in the season it's possible only one or two houses have points so we repeat for the next nearest
            if rows == None:
                totals_items = list(totals.items())[1]
                if totals_items[0] == "🧝‍♀️ : ":
                    # House Elves aren't a real house ...
                    totals_items = list(totals.items())[4]
                    house_elf_sacrifice = True
                elif totals_items[0] == "🦁 : ":
                    lowest_house = "Gryffindor"
                elif totals_items[0] == "🦅 : ":
                    lowest_house = "Ravenclaw"
                elif totals_items[0] == "🐍 : ":
                    lowest_house = "Slytherin"
                elif totals_items[0] == "🦡 : ":
                    lowest_house = "Hufflepuff"
            select = cursor.execute("SELECT users.user_id, users.hp_house, hp_points.points, hp_points.chat_id, hp_points.term_id, users.username FROM users INNER JOIN hp_points ON hp_points.user_id = users.user_id AND hp_points.chat_id = users.chat_id WHERE users.hp_house = ? AND hp_points.term_id = ? AND users.status NOT IN ('kicked', 'left') ORDER BY hp_points.points DESC LIMIT 1", (lowest_house,term_id,))
            rows = select.fetchone()
            if rows == None:
                print('Give up, Mr Potter can appear again some other time.')
            else: 
                current_points = rows[2]
                new_points = int(current_points) + 75
                user_detail = activity_status_check(rows[0],chat_id,context)
                receiverHouse = hp_get_user_house(chat_id,rows[0])
                
                cursor.execute("UPDATE hp_points SET points = ? WHERE chat_id = ? AND term_id = ? AND user_id = ?",(new_points,chat_id,term_id,rows[0]))
                db.commit()
                messageinfo = context.bot.send_sticker(chat_id, sticker=harry_file_id)
                if house_elf_sacrifice == False:
                    messageinfo = context.bot.send_message(chat_id, text="*Harry Potter* has awarded " + user_detail[1].user.mention_markdown() + " of " + receiverHouse + " as the best performing pupil of the lowest scoring house, 75 House points!\n\nTheir new total is " + str(new_points), parse_mode='markdown')
                elif house_elf_sacrifice == True:
                    messageinfo = context.bot.send_message(chat_id, text="*Harry Potter* almost awarded points to the House Elves as the lowest scoring House! However, in keeping with their manner they sacrificed themselves for the next lowest house - choosing " + user_detail[1].user.mention_markdown() + " of " + receiverHouse + " who has been granted 75 House points!", parse_mode='markdown')

def hp_character_appearance_counter(chat_id,update,context,term_id,timestamp) -> None:
    
    standard_character_count = int(get_counter(chat_id,"standard_character_counter"))
    epic_character_count = int(get_counter(chat_id,"epic_character_counter"))

    chat_config = get_chat_config(chat_id)
    standard_character_total = int(chat_config['standard_characters_frequency'][1])
    epic_character_total = int(chat_config['epic_characters_frequency'][1])

    if standard_character_count > standard_character_total:
        hp_character_appearance(chat_id,update,context,timestamp,term_id,False,"Standard")
        set_counter(chat_id,"standard_character_counter",1)
    else:
        standard_character_count += 1
        set_counter(chat_id,"standard_character_counter",standard_character_count)

    if epic_character_count > epic_character_total:
        hp_character_appearance(chat_id,update,context,timestamp,term_id,False,"Epic")
        set_counter(chat_id,"epic_character_counter",1)
    else: 
        epic_character_count += 1
        set_counter(chat_id,"epic_character_counter",epic_character_count)

def hp_rules_checker(chat_id,context,user_id = None) -> None:
    time = datetime.now()
    time = str(time.strftime("%Y-%m-%d %H:%M:%S"))
    
    # Target User House
    recipientHouse = hp_get_user_house(chat_id,user_id)

    # Cleanup old blocks/rules
    select = cursor.execute("SELECT * FROM hp_config WHERE chat_id = ?",(chat_id,))
    rows = select.fetchall()
    for row in rows:
        if row[3] < time:
            cursor.execute("DELETE FROM hp_config WHERE chat_id = ? AND expiry_time = ?",(chat_id,row[3]))
            db.commit()

    # Check if we need to do something 
    select = cursor.execute("SELECT * FROM hp_config WHERE chat_id = ?",(chat_id,))
    rows = select.fetchall()
    outcome = ""
    timestampObject = ""
    for row in rows:
        if row[1] == "bellatrix_block" and recipientHouse == row[2]:
            timestampObject = datetime.strptime(row[3], '%Y-%m-%d %H:%M:%S')
            outcome = "bellatrix_block"
        elif row[1] == "dumbledore_boost" and recipientHouse == row[2]:
            timestampObject = datetime.strptime(row[3], '%Y-%m-%d %H:%M:%S')
            outcome = "dumbledore_boost"
    
    return outcome,timestampObject

def log_bot_message(message_id, chat_id, timestamp, duration = standard_duration, type = "Standard", status = "sent", trigger_word = "", new_value = "") -> None:

    # Used for keeping track of questions
    # This will need improving if we end up needing to ask more question types!
    if type == "TriggerQuestion":
        cursor.execute("INSERT INTO bot_question_messages (chat_id,message_id,trigger_word,new_value,status) VALUES(?,?,?,?,?)",(chat_id,message_id,trigger_word,new_value,status))
        db.commit()

    # Used for keeping track of the most recent message_id from users
    elif type == "MostRecent":
        select = cursor.execute("SELECT * FROM bot_service_messages WHERE chat_id = ? AND type = ?",(chat_id,type))
        rows = select.fetchone()
        if rows:
            cursor.execute("UPDATE bot_service_messages SET created_date = ?, status = ?, message_id = ? WHERE chat_id = ? AND type = ?",(timestamp,status,message_id,chat_id,type))
        else: 
            cursor.execute("INSERT INTO bot_service_messages (message_id, chat_id, created_date, status, duration, type) VALUES(?,?,?,?,?,?)",(message_id, chat_id, timestamp, status, duration, type))
            db.commit()
    # Used for keeping track of bot messages
    else:
        cursor.execute("INSERT INTO bot_service_messages (message_id, chat_id, created_date, status, duration, type) VALUES(?,?,?,?,?,?)",(message_id, chat_id, timestamp, status, duration, type))
        db.commit()

def log_question_lookup(message_id,chat_id):
    # Looks up a message in the bot log to see if it exists
    # This will need improving if we end up needing to ask more question types!
    select = cursor.execute("SELECT * FROM bot_question_messages WHERE chat_id = ? AND message_id = ?",(chat_id,message_id))
    rows = select.fetchone()
    if rows:
        return rows

def del_bot_message(chat_id, context):
    time = datetime.now()
    select = cursor.execute("SELECT * FROM bot_service_messages WHERE chat_id = ?",(chat_id,))
    rows = select.fetchall()
    if rows:
        for row in rows:
            message_id = row[1]
            duration = row[4]
            created_date = datetime.strptime(row[2], '%Y-%m-%d %H:%M:%S')
            target_date = created_date + timedelta(seconds=int(duration))
            if time > target_date:
                try: 
                    context.bot.delete_message(chat_id,message_id)
                    cursor.execute("DELETE FROM bot_service_messages WHERE chat_id = ? AND message_id = ?",(chat_id,message_id))
                    db.commit()
                except:
                    print("Message ID " + message_id + " not found, deleting from database.")
                    cursor.execute("DELETE FROM bot_service_messages WHERE chat_id = ? AND message_id = ?",(chat_id,message_id))
                    db.commit()

# Roll functionality
# User can either send a simple '/roll' command which will default to a single eight sided die or,
# User can send a '/roll XDY' command where X = number of dice, D is the separator, Y = sides on each die. 
def roll_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    chat_text = update.message.text
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))

    chat_config = get_chat_config(chat_id)

    if chat_config['roll_enabled'][1].lower() == "yes":
        regexp = re.compile('[0-9]+D[0-9]+', re.IGNORECASE)

        json_file = open("rollSass.json")
        rollSass = json.load(json_file)
        json_file.close()

        if (len(chat_text) == 5):
            low = 1
            high = 8
            rolled = random.randint(low, high)
            messageinfo = context.bot.send_message(chat_id, text=random.choice(rollSass) + "\n\n" + str(rolled))

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
            messageinfo = context.bot.send_message(chat_id, text=random.choice(rollSass) + "\n\n" + str(rolled))

        else:
            messageinfo = context.bot.send_message(chat_id, text="Silly human. Of course you typed the wrong format. It's either '/roll' or '/roll XdY' where X is the number of dice, and Y is how many sides each dice has. For example, '/roll 2d6'")
            log_bot_message(messageinfo.message_id,chat_id,timestamp, short_duration)

# Chat Polling 
# Processes each message received in any groups where the Bot is active
# 
def chat_polling(update: Update, context: CallbackContext) -> None:
    if update.message.chat_id:      
        chat_id = str(update.message.chat_id)
    elif update.message.chat.id:
        chat_id = str(update.message.chat.id)

    # Start the DB for each chat
    db_initialise(chat_id)

    # Get Chat Config
    chat_config = get_chat_config(chat_id)

    chat_text = update.message.text
    user_id = str(update.message.from_user.id)
    message_id = update.message.message_id
    user_status = (context.bot.get_chat_member(chat_id,user_id)).status
    username = context.bot.get_chat_member(chat_id,user_id).user.username
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S")) 

    # Console Logging
    print(f"\033[1mTime:\033[0m {timestamp} \033[1mGroup Name:\033[0m {update.message.chat.title} \033[1mGroup ID: \033[0m{update.message.chat.id} \033[1m User:\033[0m {username} \n{chat_text} ")
    # Log Most Recent message ID for each chat
    # The user_id on the end here is a bit of a cludge, status isn't really supposed to hold user ID's but it works for the HP Character Appearance stuff will likely refactor at some point
    log_bot_message(message_id,chat_id,timestamp,3600,"MostRecent",user_id)

    # Kik style trigger adding
    if(separator in chat_text):
        add_trigger_command(update,context)

    # Lookup to check if text is a trigger - send trigger message to group.
    lookup = trigger_lookup(chat_text.lower(), chat_id)
    if lookup[0] == 1:
        context.bot.send_message(chat_id, text=lookup[1])
    elif lookup[0] == 2:
        context.bot.send_animation(chat_id, animation=lookup[1])
    elif lookup[0] == 3:
        context.bot.send_photo(chat_id, photo=lookup[1])
    elif lookup[0] == 4:
        context.bot.send_sticker(chat_id, sticker=lookup[1])  

    # Lookup to check if user is in activity DB, update the DB either way.
    actLookup = activity_lookup(user_id, chat_id)
    if actLookup[0] == 1: 
        cursor.execute("UPDATE users SET timestamp = ?, status = ?, username = ? WHERE user_id = ? AND chat_id = ?",(timestamp,user_status,username,user_id,chat_id))
        db.commit()
    elif actLookup[0] == 0:
        cursor.execute("INSERT INTO users (user_id,chat_id,timestamp,status,username) VALUES(?,?,?,?,?)",(user_id,chat_id,timestamp,user_status,username))
        db.commit()
    
    # Marvins Personality
    if chat_config['marvin_sass_enabled'][1].lower() == "yes":
        global frequency_count
        frequency_total = int(chat_config['marvin_sass_frequency'][1])
        marvin_counter = int(get_counter(chat_id,"marvin_sass_counter"))
        if marvin_counter > frequency_total:
            marvin_says = marvin_personality()
            context.bot.send_message(chat_id, text=marvin_says)
            set_counter(chat_id,"marvin_sass_counter",1)
        else:
            marvin_counter += 1
            set_counter(chat_id,"marvin_sass_counter",marvin_counter)
    
    # Reputation System
    if chat_config['reputation_enabled'][1].lower() == "yes":
        term_id = hp_term_tracker(chat_id, context)
        # Check if message is a a reply
        if update.message.reply_to_message:
            if not update.message.reply_to_message.from_user.is_bot:
                # Reply to a user, award points if appropriate
                hp_points(update, context, chat_id, timestamp)
            else:
                # Replying to Marvin, do stuff if needed
                hp_character_appearance(chat_id,update,context,timestamp,term_id,user=True)

        hp_character_appearance_counter(chat_id,update,context,term_id,timestamp)  

    # Check if user is replying to a bot question
    if update.message.reply_to_message:
        reply_message_id = update.message.reply_to_message.message_id
        # Check if we're replying to a bot question
        # This will need improving if we end up needing to ask more question types!
        lookup = log_question_lookup(reply_message_id,chat_id)
        if lookup:
            # Update trigger reply?
            if update.message.text.lower() == "yes":
                save_trigger(chat_id,lookup['trigger_word'],lookup['new_value'],timestamp,context)
                context.bot.delete_message(chat_id,reply_message_id)
                context.bot.delete_message(chat_id,message_id)
                cursor.execute("DELETE FROM bot_question_messages WHERE chat_id = ? AND message_id = ?",(chat_id,reply_message_id))
                db.commit()
            elif update.message.text.lower() == "no":
                context.bot.delete_message(chat_id,reply_message_id)
                context.bot.delete_message(chat_id,message_id)
                cursor.execute("DELETE FROM bot_question_messages WHERE chat_id = ? AND message_id = ?",(chat_id,reply_message_id))
                messageinfo = context.bot.send_message(chat_id, text="User decided not to update " + lookup['trigger_word'])
                db.commit()


    del_bot_message(chat_id, context)

def marvin_personality() -> None:
    json_file = open("Sass.json")
    Sass = json.load(json_file)
    json_file.close()

    return random.choice(Sass)

# Image/GIF/Sticker Polling
def chat_media_polling(update: Update, context: CallbackContext) -> None:
    chat_id = str(update.message.chat_id)
    time = datetime.now()
    timestamp = str(time.strftime("%Y-%m-%d %H:%M:%S"))
    #print(update)
    # What sort of message have we received?
    if update.message.animation:
        file_id = update.message.animation.file_id
        trigger_type = "gif"
    elif update.message.photo: 
        file_id = update.message.photo[-1].file_id
        trigger_type = "photo"
    elif update.message.sticker: 
        file_id = update.message.sticker.file_id
        trigger_type = "sticker"
    else:
        print("Received a file type I'm not familiar with")
    
    # If this is a response to a Marvin service message, check if we need to save a trigger
    if update.message.reply_to_message:
        if update.message.reply_to_message.from_user.is_bot:
            # Check if there's a valid service message waiting for a response otherwise do nothing
            message_id = update.message.reply_to_message.message_id
            select = cursor.execute("SELECT * FROM bot_service_messages WHERE chat_id = ? AND message_id = ? AND type = 'MediaTrigger'",(chat_id,message_id))
            rows = select.fetchone()
            if rows:
                chat_text = update.message.reply_to_message.text
                rest_text = chat_text.split(' ', 1)[1]
                trigger_word = u'' + rest_text.split(separator)[0].strip().lower()
                save_trigger(chat_id,trigger_word,"media",timestamp,context,trigger_type,file_id)
            else:
                # Not a valid service message, move on
                pass
        else:
            pass # replying to a User with images etc, does nothing.

# General Marvin Functionality
def set_welcome(update: Update, context: CallbackContext) -> None:
    if update.message.chat_id:      
        chat_id = str(update.message.chat_id)
    elif update.message.chat.id:
        chat_id = str(update.message.chat.id)
    chat_text = update.message.text
    user_id = update.message.from_user.id
    user_status = (context.bot.get_chat_member(chat_id,user_id)).status
    
    if len(update.message.text.split()) > 1:
        if user_status in ("creator","administrator"):
            welcome_message = chat_text.split(' ', 1)[1]
            cursor.execute("UPDATE welcome_message SET welcome_message = ? WHERE chat_id = ?",(welcome_message,chat_id))
            messageinfo = context.bot.send_message(chat_id, text="Welcome message updated.", parse_mode='markdown')
            db.commit()
        else:
            messageinfo = context.bot.send_message(chat_id, text="You don't seem to be an admin.", parse_mode='markdown')
            log_bot_message()
    elif len(update.message.text.split()) == 1:
        welcome_message = get_welcome(update, context, chat_id)
        messageinfo = context.bot.send_message(chat_id, text=welcome_message, parse_mode='markdown')

def get_welcome(update: Update, context: CallbackContext, chat_id) -> None:
    select = cursor.execute("SELECT * FROM welcome_message WHERE chat_id = ?",(chat_id,))
    rows = select.fetchone()
    if rows:
        welcome_message = rows['welcome_message']
        return welcome_message

def track_chats(update: Update, context: CallbackContext) -> None:
    """Tracks the chats the bot is in."""
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return
    was_member, is_member = result

    # Let's check who is responsible for the change
    cause_name = update.effective_user.full_name

    # Handle chat types differently:
    chat = update.effective_chat
    if chat.type == Chat.PRIVATE:
        if not was_member and is_member:
            logger.info("%s started the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).add(chat.id)
        elif was_member and not is_member:
            logger.info("%s blocked the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).discard(chat.id)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            logger.info("%s added the bot to the group %s", cause_name, chat.title)
            context.bot_data.setdefault("group_ids", set()).add(chat.id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the group %s", cause_name, chat.title)
            context.bot_data.setdefault("group_ids", set()).discard(chat.id)
    else:
        if not was_member and is_member:
            logger.info("%s added the bot to the channel %s", cause_name, chat.title)
            context.bot_data.setdefault("channel_ids", set()).add(chat.id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the channel %s", cause_name, chat.title)
            context.bot_data.setdefault("channel_ids", set()).discard(chat.id)

def show_chats(update: Update, context: CallbackContext) -> None:
    """Shows which chats the bot is in"""
    user_ids = ", ".join(str(uid) for uid in context.bot_data.setdefault("user_ids", set()))
    group_ids = ", ".join(str(gid) for gid in context.bot_data.setdefault("group_ids", set()))
    channel_ids = ", ".join(str(cid) for cid in context.bot_data.setdefault("channel_ids", set()))
    text = (
        f"@{context.bot.username} is currently in a conversation with the user IDs {user_ids}."
        f" Moreover it is a member of the groups with IDs {group_ids} "
        f"and administrator in the channels with IDs {channel_ids}."
    )
    update.effective_message.reply_text(text)

def extract_status_change(
    chat_member_update: ChatMemberUpdated,
) -> Optional[Tuple[bool, bool]]:
    """Takes a ChatMemberUpdated instance and extracts whether the 'old_chat_member' was a member
    of the chat and whether the 'new_chat_member' is a member of the chat. Returns None, if
    the status didn't change.
    """
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = (
        old_status
        in [
            ChatMember.MEMBER,
            ChatMember.CREATOR,
            ChatMember.ADMINISTRATOR,
        ]
        or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    )
    is_member = (
        new_status
        in [
            ChatMember.MEMBER,
            ChatMember.CREATOR,
            ChatMember.ADMINISTRATOR,
        ]
        or (new_status == ChatMember.RESTRICTED and new_is_member is True)
    )

    return was_member, is_member

def greet_chat_members(update: Update, context: CallbackContext) -> None:
    """Greets new users in chats and announces when someone leaves"""
    chat_id = update.effective_chat.id
    welcome_message = get_welcome(update, context, chat_id)
    result = extract_status_change(update.chat_member)
    if result is None:
        return

    was_member, is_member = result
    cause_name = update.chat_member.from_user.mention_html()
    member_name = update.chat_member.new_chat_member.user.mention_html()

    if not was_member and is_member:
        time.sleep(3)
        update.effective_chat.send_message(
            f"{member_name} was added by {cause_name}.",
            parse_mode=ParseMode.HTML,
        )
        messageinfo = context.bot.send_message(chat_id, text=welcome_message, parse_mode='markdown')
    elif was_member and not is_member:
        pass

def get_counter(chat_id, counter_name):
    select = cursor.execute("SELECT * FROM counters WHERE chat_id = ? AND counter_name = ?",(chat_id,counter_name))
    rows = select.fetchone()
    if rows:
        counter_value = rows['counter_value']
        return counter_value
    else:
       counter_value = 1
       cursor.execute("INSERT INTO counters (chat_id, counter_name, counter_value) VALUES(?,?,?)",(chat_id,counter_name,counter_value))
       db.commit()
       return counter_value

def set_counter(chat_id, counter_name, counter_value):
    select = cursor.execute("SELECT * FROM counters WHERE chat_id = ? AND counter_name = ?",(chat_id,counter_name))
    rows = select.fetchone()
    if rows:
        cursor.execute("UPDATE counters SET counter_value = ? WHERE chat_id = ? AND counter_name = ?",(counter_value,chat_id,counter_name))
        db.commit()
    else:
       cursor.execute("INSERT INTO counters (chat_id, counter_name, counter_value) VALUES(?,?,?)",(chat_id,counter_name,counter_value))
       db.commit()

def get_chat_config(chat_id, context = False, command = False, fullDetail = False) -> None:
    select = cursor.execute("SELECT * from config WHERE chat_id = ?",(chat_id,))
    rows = select.fetchall()
    configDict = {}
    for row in rows:
        add_values_in_dict(configDict,row[1],[row[2], row[3], row[4], row[5]])

    # Standard use, pulled by chat_polling() normally
    if command == False:
        return configDict
    
    # User invoked via /config
    elif command == True: 
        harryPotterConfig = ""
        marvinConfig = ""
        rollConfig = ""
        otherConfig = ""
        for config_name,config_values in configDict.items():
            # Check Config Groupings
            if config_values[0] == "Harry Potter":
                if fullDetail == True:
                    harryPotterConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n<i>" + config_values[2] + "</i>\n\n"
                else:
                    harryPotterConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n"
            elif config_values[0] == "Marvin":
                if fullDetail == True:
                    marvinConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n<i>" + config_values[2] + "</i>\n\n"
                else:
                    marvinConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n"
            elif config_values[0] == "Roll":
                if fullDetail == True:
                    rollConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n<i>" + config_values[2] + "</i>\n\n"
                else:
                    rollConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n"
            else: 
                if fullDetail == True:
                    otherConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n<i>" + config_values[2] + "</i>\n\n"
                else:
                    otherConfig += "<b>Name:</b> " + config_name + " <b>Value:</b> " + config_values[1] + "\n"
        
        messageinfo = context.bot.send_message(chat_id, text="<b>HP REPUTATION CONFIG:</b>\n" + harryPotterConfig + "<b>MARVIN CONFIG</b>:\n" + marvinConfig + "<b>ROLL CONFIG:</b>\n" + rollConfig + "<b>OTHER CONFIG:</b>\n" + otherConfig + "<i>\nConfig Notes:</i>\nIf you're unsure what a config is, get more detail with either: \n<i>/config full</i> \nor\n <i>/config config_name</i>\n\nTo set a new value for any config item, use:\n <i>/config config_name new_value</i>", parse_mode=ParseMode.HTML)
        
def set_chat_config(chat_id,config_to_update,new_value,context,configDict) -> None:
    try:
        if configDict[config_to_update]:
            for key, value in configDict.items():
                if key == config_to_update:
                    if value[3] == "boolean":
                        if new_value.lower() in ['yes','no']:
                            cursor.execute("UPDATE config SET config_value = ? WHERE config_name = ? AND chat_id = ?",(new_value.lower(),config_to_update,chat_id))
                            db.commit()
                            messageinfo = context.bot.send_message(chat_id, text=config_to_update + " updated.")
                        else:
                            messageinfo = context.bot.send_message(chat_id, text="Sorry that config only takes values of 'yes' or 'no'.")

                    elif value[3] == "int":
                        if new_value.isnumeric() and int(new_value) > 0:
                            new_value = int(new_value)
                            cursor.execute("UPDATE config SET config_value = ? WHERE config_name = ? AND chat_id = ?",(new_value,config_to_update,chat_id))
                            db.commit()
                            messageinfo = context.bot.send_message(chat_id, text=config_to_update + " updated.")
                        else: 
                            messageinfo = context.bot.send_message(chat_id, text="Sorry that config only takes positive numbers as a value.")
    except:
        messageinfo = context.bot.send_message(chat_id, text="Sorry that config name doesn't exist or something else went wrong.")

def config_command(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    user_detail = activity_status_check(user_id,chat_id,context)
    user_status = user_detail[0]
    command = update.message.text.split()

    if user_status in ("creator","administrator"):
        # Just the /config command
        if len(update.message.text.split()) == 1:
            get_chat_config(chat_id,context,True, False)
        # /config <config_name> <new_value>
        elif len(update.message.text.split()) == 2:
            if command[1].lower() == "full":
                get_chat_config(chat_id,context,True, True)
            else: 
                chat_config = get_chat_config(chat_id)
                for config_name,config_values in chat_config.items():
                    if config_name == command[1]:
                        messageinfo = context.bot.send_message(chat_id, text="<b>Name: </b>" + config_name + "\n<b>Value:</b> " + config_values[1] + "\n<b>Description: </b>" + config_values[2], parse_mode=ParseMode.HTML)
        # /config <config_name> <new_value>
        elif len(update.message.text.split()) == 3:
            configDict = get_chat_config(chat_id)
            set_chat_config(chat_id,command[1],command[2],context,configDict)
        else:
            messageinfo = context.bot.send_message(chat_id, text="Hmm. Command doesn't look right. Try /config on it's own for more information.")

    else: 
        messageinfo = context.bot.send_message(chat_id, text="Sorry config commands are Admin only!")

def broadcast_command() -> None:
    # Old code from TriggerBot.py - this needs completely reworked
    #SELECT DISTINCT chat_id FROM users;
    #if(m.from_user.id != owner):
    #    return
    #if(len(m.text.split()) == 1):
    #    bot.send_message(m.chat.id, 'No text provided!')
    #    return
    #count = 0
    #for g in triggers.keys():
    #    try:
    #        bot.send_message(int(g), m.text.split(' ', 1)[1])
    #        count += 1
    #    except ApiException:
    #        continue
    #bot.send_message(m.chat.id, 'Broadcast sent to {} groups of {}'.format(count, len(triggers.keys())))
    pass

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
    dispatcher.add_handler(CommandHandler("tags", hp_tags))
    dispatcher.add_handler(CommandHandler("config", config_command))
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))
    dispatcher.add_handler(CommandHandler("welcome", set_welcome))

    # Keep track of which chats the bot is in
    dispatcher.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    dispatcher.add_handler(CommandHandler("show_chats", show_chats))

    # Watch for new people
    dispatcher.add_handler(ChatMemberHandler(greet_chat_members, ChatMemberHandler.CHAT_MEMBER))

    # on non command i.e message - checks each message and runs it through our poller
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & ~Filters.update.edited_message, chat_polling))
    dispatcher.add_handler(MessageHandler(~Filters.text & ~Filters.command, chat_media_polling))

    # Start the Bot
    updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()