#!/usr/bin/env python3
import logging
from time import sleep
import traceback
import sys
from html import escape
import time

# Set up logging
root = logging.getLogger()
root.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)



from telegram import ParseMode, TelegramError, Update
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters
from telegram.ext.dispatcher import run_async

# from config import BOTNAME, TOKEN

import os
import psycopg2

DATABASE_URL = os.environ['DATABASE_URL']
PORT = int(os.environ.get('PORT', 5000))
BOTNAME = os.environ.get('BOTNAME', 'sberlogawelcome-bot')
TOKEN = os.environ.get('TOKEN', 'bottoken')


conn = psycopg2.connect(DATABASE_URL, sslmode='require')


help_text = (
    "Welcomes everyone that enters a group chat that this bot is a "
    "part of. By default, only the person who invited the bot into "
    "the group is able to change settings.\nCommands:\n\n"
    "/welcome - Set welcome message\n"
    "/get_welcome - Returns current welcome message\n"
    "/goodbye - Set goodbye message\n"
    "/get_goodbye - Returns current goodbye message\n"
    "/disable\\_goodbye - Disable the goodbye message\n"
    "/lock - Only the person who invited the bot can change messages\n"
    "/unlock - Everyone can change messages\n"
    '/quiet - Disable "Sorry, only the person who..." '
    "& help messages\n"
    '/unquiet - Enable "Sorry, only the person who..." '
    "& help messages\n\n"
    "You can use _$username_ and _$title_ as placeholders when setting"
    " messages. [HTML formatting]"
    "(https://core.telegram.org/bots/api#formatting-options) "
    "is also supported.\n"
)

"""
Create database object
Database schema:
<chat_id> -> welcome message
<chat_id>_bye -> goodbye message
<chat_id>_adm -> user id of the user who invited the bot
<chat_id>_lck -> boolean if the bot is locked or unlocked
<chat_id>_quiet -> boolean if the bot is quieted
chats -> list of chat ids where the bot has received messages in.
"""
# Create database object
with conn.cursor() as cur:
    cur.execute("""SELECT EXISTS (
       SELECT FROM information_schema.tables 
       WHERE  table_name   = 'chats'
       )""")
    chats_exist =  not cur.fetchone()[0]
    logger.info('chats_exist = '+ str(chats_exist))

if chats_exist:
    sql = """create table chats(
                      chat_id BIGINT PRIMARY KEY, 
                      welcome text, 
                      goodbye text, 
                      admin BIGINT, 
                      lock BOOLEAN, 
                      quiet BOOLEAN,
                      disable_goodbye BOOLEAN)
                """
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()


@run_async
def send_short_async(context, *args, **kwargs):
    logger.info('send_short_async func')
    message = context.bot.send_message(*args, **kwargs)
    time.sleep(3)
    chat_id = message.chat.id
    message_id = message.message_id
    context.bot.delete_message(chat_id, message_id)

@run_async
def send_long_async(context, *args, **kwargs):
    logger.info('send_long_async func')
    message = context.bot.send_message(*args, **kwargs)
    time.sleep(180)
    chat_id = message.chat.id
    message_id = message.message_id
    context.bot.delete_message(chat_id, message_id)

    
@run_async
def delete_async(context, chat_id, message_id, *args, **kwargs):
    logger.info('delete_async func')
    time.sleep(3)
    context.bot.delete_message(chat_id, message_id)

def check_exist(conn, chat_id):
    logger.info('check_exist func')
    cur = conn.cursor()
    cur.execute("SELECT chat_id FROM chats WHERE chat_id = %s", (str(chat_id),))
    if cur.fetchone() is not None:
        pass
    else:
        logger.info('created chat = ' + str(chat_id))

        sql = """INSERT INTO chats(chat_id) VALUES (%s)"""
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (str(chat_id),))
                conn.commit()
        except Exception as e:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(sql, (str(chat_id),))
                conn.commit()

def check(update, context, override_lock=None):
    """
    Perform some checks on the update. If checks were successful, returns True,
    else sends an error message to the chat and returns False.
    """
    logger.info('check func')

    chat_id = update.message.chat_id
    message_id = update.message.message_id
    user_id = update.message.from_user.id
    user_member = context.bot.get_chat_member(chat_id, user_id)['status']
    chat_str = str(chat_id)

    if chat_id > 0:
        send_short_async(
            context, chat_id=chat_id, text="Please add me to a group first!",
        )
        return False

    logger.info('user_id = ' + str(user_id) + ' is ' + str(user_member))

    cur = conn.cursor()
    logger.info("select lock, admin, quiet from chats where chat_id="+str(chat_id))
    cur.execute("select lock, admin, quiet from chats where chat_id=%s", (str(chat_id),))
    data = cur.fetchone()
    logger.info('data = ' + str(data))
    lock, admin, quiet = data
    logger.info('lock = '+ str(lock)+ 'quiet = ' + str(quiet)+ 'admin = ' + str(admin))
    cur.close()

    locked = override_lock if override_lock is not None else lock

    if locked and (str(user_member) not in ["creator", "administrator"]):
        if  not quiet:
            send_short_async(
                context,
                chat_id=chat_id,
                text="Sorry, only the person who invited me can do that.",
            )
        return False

    return True


# Welcome a user to the chat
def welcome(update, context, new_member):
    """ Welcomes a user to the chat """
    logger.info('welcome func')

    message = update.message
    chat_id = message.chat.id
    logger.info(
        "%s joined to chat %d (%s)",
        escape(new_member.first_name),
        chat_id,
        escape(message.chat.title),
    )

    # Pull the custom message for this chat from the database
    cur = conn.cursor()
    cur.execute("select welcome from chats where chat_id=%s", (str(chat_id),))
    text = cur.fetchone()[0]
    cur.close()

    # Use default message if there's no custom one set
    if text is None:
        text = "Hello $username! Welcome to $title 😊"

    # Replace placeholders and send message
    text = text.replace("$username", new_member.first_name)
    text = text.replace("$title", message.chat.title)
    send_long_async(context, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


# Welcome a user to the chat
def goodbye(update, context):
    """ Sends goodbye message when a user left the chat """
    logger.info('goodbye func')

    message = update.message
    chat_id = message.chat.id
    logger.info(
        "%s left chat %d (%s)",
        escape(message.left_chat_member.first_name),
        chat_id,
        escape(message.chat.title),
    )

    # Pull the custom message for this chat from the database
    cur = conn.cursor()
    cur.execute("select goodbye from chats where chat_id=%s", (str(chat_id),))
    text = cur.fetchone()[0]
    cur.close()

    # Goodbye was disabled
    if text is False:
        return

    # Use default message if there's no custom one set
    if text is None:
        text = "Goodbye, $username!"

    # Replace placeholders and send message
    text = text.replace("$username", message.left_chat_member.first_name)
    text = text.replace("$title", message.chat.title)
    send_long_async(context, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


# Introduce the bot to a chat its been added to
def introduce(update, context):
    """
    Introduces the bot to a chat its been added to and saves the user id of the
    user who invited us.
    """
    logger.info('introduce func')

    chat_id = update.message.chat.id
    invited = update.message.from_user.id

    logger.info(
        "Invited by %s to chat %d (%s)", invited, chat_id, update.message.chat.title,
    )

    check_exist(conn, chat_id)

    sql = """
                UPDATE chats
                SET admin = %s,
                    lock = %s
                WHERE
                    chat_id = %s
            """
    try:
        with conn.cursor() as cur:
            cur.execute(sql,  (invited, True, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql,  (invited, True, str(chat_id)))
            conn.commit()

    text = (
        f"Hello {update.message.chat.title}! "
        "I will now greet anyone who joins this chat with a "
        "nice message 😊 \nCheck the /help command for more info!"
    )
    send_short_async(context, chat_id=chat_id, text=text)

def get_welcome(update, context):
    logger.info('get_welcome func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    user_id = update.message.from_user.id
    user = context.bot.get_chat_member(chat_id, user_id)
    delete_async(context, chat_id, message_id)
    chat_str = str(chat_id)
    welcome(update, context,user)

def get_goodbye(update, context):
    logger.info('get_welcome func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    user_id = update.message.from_user.id
    user = context.bot.get_chat_member(chat_id, user_id)
    delete_async(context, chat_id, message_id)
    chat_str = str(chat_id)
    goodbye(update, context, user)

# Print help text
def help(update, context):
    """ Prints help text """
    logger.info('help func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    user_id = update.message.from_user.id
    user_member = context.bot.get_chat_member(chat_id, user_id)['status']
    delete_async(context, chat_id, message_id)
    chat_str = str(chat_id)

    cur = conn.cursor()
    cur.execute("select quiet, admin from chats where chat_id=%s", (str(chat_id),))
    quiet, admin = cur.fetchone()
    logger.info('quiet = ' + str(quiet)+ ', admin = '+ str(admin))
    cur.close()

    if (not quiet) or (str(user_member) in ["creator", "administrator"]):
        send_short_async(
            context,
            chat_id=chat_id,
            text=help_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )



# Set custom message
def set_welcome(update, context):
    """ Sets custom welcome message """
    logger.info('set_welcome func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    delete_async(context, chat_id, message_id)
    # Check admin privilege and group context
    if not check(update, context):
        return

    # Split message into words and remove mentions of the bot
    message = update.message.text.partition(" ")[2]

    # Only continue if there's a message
    if not message:
        send_short_async(
            context,
            chat_id=chat_id,
            text="You need to send a message, too! For example:\n"
            "<code>/welcome Hello $username, welcome to "
            "$title!</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Put message into database
    check_exist(conn, chat_id)

    sql = """
                UPDATE chats
                SET welcome = %s
                WHERE
                    chat_id = %s
            """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (message, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql, (message, str(chat_id)))
            conn.commit()


    send_short_async(context, chat_id=chat_id, text="Got it!")


# Set custom message
def set_goodbye(update, context):
    """ Enables and sets custom goodbye message """
    logger.info('set_goodbye func')

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(update, context):
        return

    # Split message into words and remove mentions of the bot
    message_id = update.message.message_id
    message = update.message.text.partition(" ")[2]

    # Only continue if there's a message
    if not message:
        send_short_async(
            context,
            chat_id=chat_id,
            text="You need to send a message, too! For example:\n"
            "<code>/goodbye Goodbye, $username!</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Put message into database
    check_exist(conn, chat_id)

    sql = """
                UPDATE chats
                SET goodbye = %s
                WHERE
                    chat_id = %s
            """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (message, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql, (message, str(chat_id)))
            conn.commit()

    delete_async(context, chat_id, message_id)

    send_short_async(context, chat_id=chat_id, text="Got it!")


def disable_goodbye(update, context):
    """ Disables the goodbye message """
    logger.info('disable_goodbye func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    delete_async(context, chat_id, message_id)

    # Check admin privilege and group context
    if not check(update, context):
        return

    # Disable goodbye message
    check_exist(conn, chat_id)
    sql = """
                UPDATE chats
                SET disable_goodbye = %s
                WHERE
                    chat_id = %s
            """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (False, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql, (False, str(chat_id)))
            conn.commit()

    send_short_async(context, chat_id=chat_id, text="Got it!")


def lock(update, context):
    """ Locks the chat, so only the invitee can change settings """
    logger.info('lock func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    delete_async(context, chat_id, message_id)

    # Check admin privilege and group context
    if not check(update, context, override_lock=True):
        return

    # Lock the bot for this chat

    check_exist(conn, chat_id)

    sql = """
        UPDATE chats
        SET lock = %s
        WHERE
            chat_id = %s
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (True, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql, (True, str(chat_id)))
            conn.commit()

    send_short_async(context, chat_id=chat_id, text="Got it!")


def quiet(update, context):
    """ Quiets the chat, so no error messages will be sent """
    logger.info('quiet func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    delete_async(context, chat_id, message_id)

    # Check admin privilege and group context
    if not check(update, context, override_lock=True):
        return

    # Lock the bot for this chat
    check_exist(conn, chat_id)

    sql = """
        UPDATE chats
        SET quiet = %s
        WHERE
            chat_id = %s
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (True, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql, (True, str(chat_id)))
            conn.commit()

    send_short_async(context, chat_id=chat_id, text="Got it!")


def unquiet(update, context):
    """ Unquiets the chat """
    logger.info('unquiet func')

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    delete_async(context, chat_id, message_id)

    # Check admin privilege and group context
    if not check(update, context, override_lock=True):
        return

    # Lock the bot for this chat
    check_exist(conn, chat_id)

    sql = """
        UPDATE chats
        SET quiet = %s
        WHERE
            chat_id = %s
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (False, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql, (False, str(chat_id)))
            conn.commit()

    send_short_async(context, chat_id=chat_id, text="Got it!")


def unlock(update, context):
    """ Unlocks the chat, so everyone can change settings """

    chat_id = update.message.chat.id
    message_id = update.message.message_id
    delete_async(context, chat_id, message_id)

    # Check admin privilege and group context
    if not check(update, context):
        return

    # Unlock the bot for this chat
    check_exist(conn, chat_id)

    sql = """
        UPDATE chats
        SET lock = %s
        WHERE
            chat_id = %s
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (False, str(chat_id)))
            conn.commit()
    except Exception as e:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql, (False, str(chat_id)))
            conn.commit()

    send_short_async(context, chat_id=chat_id, text="Got it!")


def empty_message(update, context):
    """
    Empty messages could be status messages, so we check them if there is a new
    group member, someone left the chat or if the bot has been added somewhere.
    """
    logger.info('empty_message func')
    # Keep chatlist
    cur = conn.cursor()
    cur.execute("""select chat_id from chats""")
    chats = cur.fetchall()

    chats = [chat[0] for chat in chats]

    logger.info('chats = '+str(chats))
    if update.message.chat.id not in chats:
        chat_id = update.message.chat.id

        sql = """INSERT INTO chats(chat_id) VALUES (%s)"""
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (str(chat_id),))
                conn.commit()
        except Exception as e:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(sql, (str(chat_id),))
                conn.commit()

        logger.info('creating new chat = ' + str(chat_id))

        logger.info("I have been added to %d chats" % len(chats))

    cur.close()

    if update.message.new_chat_members:
        logger.info("new_chat_members = "+str(update.message.new_chat_members))
        for new_member in update.message.new_chat_members:
            logger.info("new_member = " + str(new_member))
            # Bot was added to a group chat
            if new_member.username == BOTNAME:
                logger.info("new_member.username = " + str(new_member.username))
                return introduce(update, context)
            # Another user joined the chat
            else:
                return welcome(update, context, new_member)

    # Someone left the chat
    elif update.message.left_chat_member is not None:
        if update.message.left_chat_member.username != BOTNAME:
            return goodbye(update, context)


def error(update, context, **kwargs):
    """ Error handling """
    logger.info('error func')
    error = context.error

    try:
        if isinstance(error, TelegramError) and (
            error.message == "Unauthorized"
            or error.message == "Have no rights to send a message"
            or "PEER_ID_INVALID" in error.message
        ):
            logger.info('TelegramError = '+str(error))
            chat_id = update.message.chat_id

            sql = """delete from chats where chat_id = %s"""
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, (str(chat_id),))
                    conn.commit()
            except Exception as e:
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute(sql, (str(chat_id),))
                    conn.commit()

            logger.info('deleted chat = '+str(chat_id))
            cur.close()
            logger.info("Removed chat_id %s from chat list" % update.message.chat_id)
        else:
            logger.error("An error (%s) occurred: %s" % (type(error), error.message))
    except:
        logger.info('error = '+str(error))


def main():
    # Create the Updater and pass it your bot's token.
    updater = Updater(TOKEN, workers=10, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", help))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("welcome", set_welcome))
    dp.add_handler(CommandHandler("get_welcome", get_welcome))
    dp.add_handler(CommandHandler("goodbye", set_goodbye))
    dp.add_handler(CommandHandler("get_goodbye", get_goodbye))
    dp.add_handler(CommandHandler("disable_goodbye", disable_goodbye))
    dp.add_handler(CommandHandler("lock", lock))
    dp.add_handler(CommandHandler("unlock", unlock))
    dp.add_handler(CommandHandler("quiet", quiet))
    dp.add_handler(CommandHandler("unquiet", unquiet))

    dp.add_handler(MessageHandler(Filters.status_update, empty_message))

    dp.add_error_handler(error)

    # updater.start_polling(timeout=30, clean=True)
    updater.start_webhook(listen="0.0.0.0",
                          port=int(PORT),
                          url_path=TOKEN)
    updater.bot.setWebhook('https://whispering-taiga-43544.herokuapp.com/' + TOKEN)

    updater.idle()


if __name__ == "__main__":
    main()