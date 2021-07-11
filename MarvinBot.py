"""
Group Entertainment Bot written for Python 3

Marvin is your groups resident manic depressive robot with personality! 

REQUIREMENTS:
- Python 3.6+
- SQLite3
- Python-Telegram-Bot (https://github.com/python-telegram-bot/python-telegram-bot)

USAGE:
- pip install -r requirements.txt
- Rename .env.example to .env - update with your Telegram Bot Token
- Rename rollSass.json.example to rollSass.json - feel free to add your own snark/personality.

FEATURES: 
- Dice Roll (/roll or /roll XdY e.g /roll 2d8)
- Triggers (/add trigger -> triggerResponse ... /del trigger)

"""

import logging
import sqlite3
import random
import re
import json
from telegram import Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from decouple import config

# .env Variables
# Place a .env file in the directory with 'TOKEN=<YOURTOKENHERE>' - alternatively replace TOKEN in the line below with your Bots token
TOKEN = config('TOKEN')

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# Separator character. Used for commands with a to/from type response
separator = '->'

# Open connection to the Database and define table names
dbname = "marvin"
db = sqlite3.connect(dbname+".db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS 'triggers' ('trigger_word' TEXT NOT NULL, 'trigger_response' TEXT NOT NULL, 'chat_id' INTEGER NOT NULL)")


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
        cursor.execute("UPDATE triggers SET trigger_response = '" + trigger_response + "' WHERE trigger_word = '" + trigger_word + "' AND chat_id = '" + chat_id + "'")
        db.commit()
        context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] updated.")
    elif lookup[0] == 0:
        cursor.execute("INSERT INTO triggers (trigger_word,trigger_response,chat_id) VALUES('" + trigger_word + "','" + trigger_response + "','" + chat_id + "')")
        db.commit()
        context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] created.")

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
        cursor.execute("DELETE FROM triggers WHERE trigger_word = '" + trigger_word + "' AND chat_id = '" + chat_id + "'")
        db.commit()
        context.bot.send_message(chat_id, text="Trigger [" + trigger_word + "] deleted.")
    elif lookup[0] == 0:
        context.bot.send_message(chat_id, text="Trigger not found.")

def trigger_lookup(trigger_word, chat_id) -> None:
    select = cursor.execute("SELECT * from triggers WHERE trigger_word = '" + trigger_word + "' AND chat_id = '" + chat_id + "'")
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

def list_trigger_command(update: Update, context: CallbackContext) -> None:
    """Removes a trigger when the /list command is used"""
    chat_id = str(update.message.chat_id)

    select = cursor.execute("SELECT * from triggers WHERE chat_id = '" + chat_id + "'")
    rows = select.fetchall()
    triggerList = []
    if rows:
        for row in rows:
            triggerList.append(row[0])
        
        sentenceList = ", ".join(triggerList)
        context.bot.send_message(chat_id, text="Trigger list:\n\n" + sentenceList)
    else: 
        error = 'Something went wrong or trigger wasnt found'
        return 0, error

def list_trigger_detail_command(update: Update, context: CallbackContext) -> None:
    """Removes a trigger when the /list command is used"""
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)

    select = cursor.execute("SELECT * from triggers WHERE chat_id = '" + chat_id + "'")
    rows = select.fetchall()
    triggerList = []
    if rows:
        for row in rows:
            triggerFull = "*" + row[0] + " : *" + row[1]
            triggerList.append(triggerFull)
        
        sentenceList = "\n\n".join(triggerList)
        context.bot.send_message(user_id, text="Full Detail Trigger List:\n\n" + sentenceList, parse_mode='markdown')
    else: 
        error = 'Something went wrong or trigger wasnt found'
        return 0, error

def trigger_polling(update: Update, context: CallbackContext) -> None:
    chat_id = str(update.message.chat_id)
    chat_text = update.message.text
    
    lookup = trigger_lookup(chat_text.lower(), chat_id)
    if lookup[0] == 1:
        context.bot.send_message(chat_id, text=lookup[1])

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

    # on non command i.e message - check if message is a match in the trigger_polling function
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, trigger_polling))

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()