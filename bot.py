#!/usr/bin/python

from collections import defaultdict
from email.utils import parseaddr
import datetime
from email.mime.text import MIMEText
import math
import os
import re
from pytz import timezone, all_timezones
import smtplib
from configparser import ConfigParser

import dateparser
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import psycopg2
from psycopg2 import sql
import seaborn as sns
sns.set(style="white")
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.error import BadRequest

PARSER = ConfigParser()
PARSER.read('creds.ini')

TOKEN = PARSER.get('DEFAULT', 'BOT_TOKEN')

UPDATER = Updater(token=TOKEN)
DISPATCHER = UPDATER.dispatcher
JOBQUEUE = UPDATER.job_queue

CONNECTION = None
DB_NAME = PARSER.get('DEFAULT', 'DB_NAME')
DB_USER = PARSER.get('DEFAULT', 'DB_USER')
DB_PASSWORD = PARSER.get('DEFAULT', 'DB_PASSWORD')
DB_HOST = PARSER.get('DEFAULT', 'DB_HOST')

GMAIL_EMAIL = PARSER.get('DEFAULT', 'GMAIL_EMAIL')
GMAIL_PASSWORD = PARSER.get('DEFAULT', 'GMAIL_PASSWORD')

def get_connection():
    global CONNECTION

    if not CONNECTION or CONNECTION.closed != 0:
        CONNECTION = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port="5432"
        )

    return CONNECTION

def get_streak_of(user_id):
    cursor = get_connection().cursor()
    cursor.execute(
        sql.SQL(
            "WITH t AS ("\
                "SELECT distinct(meditation.created_at::date) AS created_at "\
                "FROM meditation "\
                "WHERE id = %s"\
            ")"\
            "SELECT COUNT(*) FROM t WHERE t.created_at > ("\
                "SELECT d.d "\
                "FROM generate_series('2018-01-01'::date, TIMESTAMP 'yesterday'::date, '1 day') d(d) "\
                "LEFT OUTER JOIN t ON t.created_at = d.d::date "\
                "WHERE t.created_at IS NULL "\
                "ORDER BY d.d DESC "\
                "LIMIT 1"\
            ")"
        ), (user_id,)
    )
    results = cursor.fetchall()
    get_connection().commit()
    return results[0][0]

def add_to_table(table, user_id, value, sentdate):
    cursor = get_connection().cursor()
    cursor.execute(sql.SQL("INSERT INTO {} (id, value, created_at) VALUES (%s, %s, %s)").format(sql.Identifier(table)), (user_id, value, sentdate))
    get_connection().commit()
    cursor.close()

def add_meditation_reminder(user_id, value, midnight):
    cursor = get_connection().cursor()
    cursor.execute("INSERT INTO meditationreminders (id, value, midnight) VALUES (%s, %s, %s)", (user_id, value, midnight))
    get_connection().commit()
    cursor.close()

def get_values(table, start_date=None, end_date=None, user_id=None, value=None):
    cursor = get_connection().cursor()
    query = sql.SQL("SELECT * FROM {} WHERE "\
                    "(%s is NULL OR id = %s) "\
                    "AND (%s is NULL OR created_at > %s) "\
                    "AND (%s is NULL OR created_at < %s) "\
                    "AND (%s is NULL OR value = %s);").format(sql.Identifier(table))
    cursor.execute(query, (user_id, user_id, start_date, start_date, end_date, end_date, value, value))
    results = cursor.fetchall()
    get_connection().commit()
    return results

def delete_message(bot, chat_id, message_id):
    try:
        bot.deleteMessage(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        pass

def help_message(bot, update):
    message = \
        "/streak = Shows your current meditation streak\n"\
        "/summary \[<email> or `off`] - Enable or disable weekly email summaries \n"\
        "\n"\
        "`[backdate?]` allows you to log something in the past (eg. `/meditate 10 22-MARCH-2018.`) This is completely optional.\n"\
        "/anxiety \[0-10] \[backdate?] = Anxiety level (0 low, 10 high)\n"\
        "/exercise \[description] \[backdate?] = Log your exercise\n"\
        "/fasting \[hours] \[backdate?] = Your fasting session\n"\
        "/happiness \[0-10] \[backdate?] = Happiness level (0 low, 10 high)\n"\
        "/journal \[entry] \[backdate?] = Log a journal entry (Either publicly or in private to @zenafbot)\n"\
        "/meditate \[minutes] \[backdate?] = Record your meditation\n"\
        "/sleep \[0-24] \[backdate?] = Record your sleep (hours)\n"\
        "\n"\
        "`[period]` = either `weekly`, `biweekly`, `monthly` or `all`\n"\
        "/anxietystats \[period] = Graph of your anxiety levels\n"\
        "/fastingstats \[period] = Graph of your fasts\n"\
        "/groupstats \[period] = Total meditation time by the group\n"\
        "/happystats \[period] = Graph of your happiness levels\n"\
        "/journalentries \[dd-mm-yyyy] = Retrieve journal entries from date\n"\
        "/meditatestats \[period] = Graph of your meditation history\n"\
        "/sleepstats \[period] = Graph of your sleep history"

    delete_message(bot, update.message.chat.id, update.message.message_id)

    bot.send_message(chat_id=update.message.chat_id, parse_mode="Markdown", text=message)

def get_streak_emoji(streak):
    if streak == 0:
        return "🤔"
    elif streak < 50:
        return "🔥"
    else:
        return "🌶️"

def pm(bot, update):
    user = get_or_create_user(bot, update)
    has_pm_bot = user[5]
    if has_pm_bot is True:
        bot.send_message(chat_id=update.message.from_user.id, text="Sorry, I didn't understand that!")
    else:
        cursor = get_connection().cursor()
        cursor.execute('UPDATE users SET haspm = TRUE WHERE id = %s', (update.message.from_user.id,))
        get_connection().commit()
        cursor.close()

        bot.send_message(chat_id=update.message.from_user.id, text="Thanks for PMing me! 👋 Now I can PM you too! " \
            "📨 Please don't delete this chat or I won't be able PM you anymore. 😢 " \
            "Any command that you can perform with me in the Mindful Makers channel can also be ran here! " \
            "That way you can keep things private with me! 💖")

def meditate(bot, update):
    def validation_callback(parts):
        value = int(parts[0])
        if value < 5 or value > 1440:
            bot.send_message(chat_id=update.message.from_user.id, text="🙏 Meditation time must be between 5 and 1440 minutes. 🙏")
            return False
        return value

    def success_callback(name_to_show, value, update, historic_date):
        streak = get_streak_of(update.message.from_user.id)
        emoji = get_streak_emoji(streak)
        bot.send_message(chat_id=update.message.chat.id, text="✅ {} meditated for {} minutes{} ({}{}) 🙏".format(name_to_show, value, historic_date, streak, emoji))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "meditation",
        "wrong_length": "🙏 How many minutes did you meditate? 🙏",
        "value_error": "🙏 You need to specify the minutes as a number! 🙏"
    })

def schedulereminders(bot, update):
    parts = update.message.text.split(' ')
    if len(parts) == 2 and parts[1] == "off":
        # Delete is too powerful to have as a generalised function
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM meditationreminders WHERE id = %s', (update.message.from_user.id,))
        conn.commit()
        cursor.close()
        bot.send_message(chat_id=update.message.from_user.id, text="Okay, you won't receive reminders anymore! ✌️")
        return True

    new_parts = []
    if parts[-1] in all_timezones:
        tz = timezone(parts[-1])
        for i in range(1, len(parts) - 1):
            part = parts[i]
            if not re.match('((([1-9])|(1[0-2]))(AM|PM|am|pm))', part):
                bot.send_message(chat_id=update.message.from_user.id, text="Sorry, I didn't understand this hour: `{}`. "\
                                "It should look similar to this: `11AM`. The whole command should look similar to this: "\
                                "`\\reminders 1PM 5PM 11PM UTC`. You can specify as many hours as you like.".format(part))
                return False
            else:
                hour = 0
                if part.lower().endswith("pm"):
                    hour = 12
                hour = (hour + int(part[:-2])) % 24
                # Take our tz hour, convert it to utc hour
                notification_hour = tz.localize(datetime.datetime(2018, 3, 23, hour, 0, 0)).astimezone(timezone("UTC")).hour
                midnight = tz.localize(datetime.datetime(2018, 3, 23, 0, 0, 0)).astimezone(timezone("UTC")).hour
                new_parts.append((notification_hour, midnight))
    else:
        bot.send_message(chat_id=update.message.from_user.id, text="Sorry, I didn't understand the timezone you specified: `{}`. "\
                        "It can take the form of a specific time like `UTC` or as for a country `Europe/Amsterdam`. "\
                        "The whole command should look similar to this: "\
                        "`\\reminders 1PM 5PM 11PM UTC`. You can specify as many hours as you like.".format(parts[len(parts) - 1]))
        return False

    user = get_or_create_user(bot, update)
    for hours in new_parts:
        add_meditation_reminder(update.message.from_user.id, hours[0], hours[1])
    username = get_name(update.message.from_user)
    has_pm_bot = user[5]
    if has_pm_bot is True:
        bot.send_message(chat_id=update.message.from_user.id, text="Okay {}, I've scheduled those reminders for you! 🕑".format(username))
    else:
        bot.send_message(chat_id=update.message.from_user.id, text="Okay {}, I've scheduled those reminders for you! 🕑 "\
                        "If you haven't already, please send me a PM at @zenafbot so that I can PM your reminders to you!".format(username))

def executereminders(bot, _):
    now = datetime.datetime.now()
    users_to_notify = get_values("meditationreminders", value=now.hour)
    for user in users_to_notify:
        user_id = user[0]
        user_midnight_utc = user[2] # Will be an int like 2, meaning midnight is at 2AM UTC for the user
        # We don't want to notify if the user already meditated today
        # Because of timezones, 'today' probably means something different for user
        # So we check between their midnight and now
        if user_midnight_utc > now.hour:
            start_check_period = get_x_days_before(now, 1).replace(hour=user_midnight_utc, minute=0, second=0)
        else:
            start_check_period = now.replace(hour=user_midnight_utc, minute=0, second=0)
        meditations = get_values("meditation", start_date=start_check_period, end_date=now, user_id=user_id)
        meditations_len = len(meditations)
        if meditations_len == 0:
            bot.send_message(chat_id=user_id, text="Hey! You asked me to send you a private message to remind you to meditate! 🙏 "\
                                                   "You can turn off these notifications with `/reminders off`. 🕑")

def find_rating_change(table, user_id, new_value):
    now = datetime.datetime.now()
    yesterday = get_x_days_before(now, 1)
    # We want to find change in rating between current value and most recent value in 24 last hours
    ratings_last_day = get_values(table, start_date=yesterday, end_date=now, user_id=user_id)
    difference_str = ""
    if len(ratings_last_day) > 1:
        ratings_last_day.sort(key=lambda r: r[2], reverse=True)
        difference = new_value - ratings_last_day[1][1]
        difference_str = ' ({})'.format("{:+}".format(difference) if difference else "no change")
    return difference_str

def anxiety(bot, update):
    def validation_callback(parts):
        value = int(parts[0])
        if value < 0 or value > 10:
            bot.send_message(chat_id=update.message.from_user.id, text="Please rate your anxiety between 0 (low) and 10 (high).")
            return False
        return value

    def success_callback(name_to_show, value, update, historic_date):
        if value >= 9:
            emoji = "😭"
        elif value >= 7:
            emoji = "😦"
        elif value >= 5:
            emoji = "😐"
        elif value >= 3:
            emoji = "🙂"
        else:
            emoji = "😎"

        difference = find_rating_change("anxiety", update.message.from_user.id, value)
        bot.send_message(chat_id=update.message.chat.id,
                         text="{} {} rated their anxiety at {}{}{} {}".format(emoji, name_to_show, value, difference, historic_date, emoji))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "anxiety",
        "wrong_length": "Please give your anxiety levels.",
        "value_error": "You need to specify the value as a number."
    })

def happiness(bot, update):
    def validation_callback(parts):
        value = int(parts[0])
        if value < 0 or value > 10:
            bot.send_message(chat_id=update.message.from_user.id, text="Please rate your happiness level 0-10")
            return False
        return value

    def success_callback(name_to_show, value, update, historic_date):
        if value >= 9:
            emoji = "😎"
        elif value >= 7:
            emoji = "😄"
        elif value >= 5:
            emoji = "🙂"
        elif value >= 4:
            emoji = "😐"
        elif value >= 3:
            emoji = "😕"
        elif value >= 1:
            emoji = "😦"
        else:
            emoji = "😭"

        difference = find_rating_change("happiness", update.message.from_user.id, value)
        bot.send_message(chat_id=update.message.chat.id,
                         text="{} {} rated their happiness at {}{}{} {}".format(emoji, name_to_show, value, difference, historic_date, emoji))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "happiness",
        "wrong_length": "Please rate your happiness level between 0-10",
        "value_error": "You need to specify the value as a whole number (eg. 7)"
    })

def sleep(bot, update):
    def validation_callback(parts):
        value = float(parts[0])
        if value < 0 or value > 24:
            bot.send_message(chat_id=update.message.from_user.id, text="💤 Please give how many hours you slept. 💤")
            return False
        return value

    def success_callback(name_to_show, value, update, historic_date):
        bot.send_message(chat_id=update.message.chat.id, text="✅ {} slept for {} hours{} 💤".format(name_to_show, value, historic_date))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "sleep",
        "wrong_length": "💤 Please give how many hours you slept. 💤",
        "value_error": "💤 You need to specify the value as a decimal number (eg. 7.5) 💤"
    })

def fasting(bot, update):
    def validation_callback(parts):
        value = float(parts[0])
        if value < 0:
            bot.send_message(chat_id=update.message.from_user.id, text="🍽 Please give how many hours you fasted for. 🍽")
            return False
        return value

    def success_callback(name_to_show, value, update, historic_date):
        bot.send_message(chat_id=update.message.chat.id, text="✅ {} fasted for {} hours{} 🍽".format(name_to_show, value, historic_date))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "fasting",
        "wrong_length": "🍽 Please give how many hours you fasted for. 🍽",
        "value_error": "🍽 You need to specify the value as a decimal number (eg. 18.5) 🍽"
    })

def done(bot, update):
    def validation_callback(parts):
        activity = " ".join(parts)
        activity_len = len(activity)
        if activity_len == 0 or activity_len > 4000:
            bot.send.message(chat_id=update.message.from_user.id, text="Please list your activity between 0 and 4000 characters!")
            return False
        return activity

    def success_callback(name_to_show, value, update, historic_date):
        bot.send_message(chat_id=update.message.chat.id, text="✅ {} completed{}: {}".format(name_to_show, historic_date, value))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "done",
        "wrong_length": "There is a limit of 4000 characters!",
        "value_error": "<shouldn't be hit>"
    })

def exercise(bot, update):
    def validation_callback(parts):
        activity = " ".join(parts)
        activity_len = len(activity)
        if activity_len == 0 or activity_len > 4000:
            bot.send_message(chat_id=update.message.from_user.id, text="💪 Please list your activity between 0 and 4000 characters! 💪")
            return False
        return activity

    def success_callback(name_to_show, value, update, historic_date):
        bot.send_message(chat_id=update.message.chat.id, text="✅ {} exercised{}: {}".format(name_to_show, historic_date, value))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "exercise",
        "wrong_length": "💪 Please specify your exercise. 💪",
        "value_error": "💪 You need to specify your exercise within 4000 characters! 💪"
    })

def rest(bot, update):
    get_or_create_user(bot, update)
    add_to_table("exercise", update.message.from_user.id, "rest", update.message.date)
    delete_message(bot, update.message.chat.id, update.message.message_id)
    name_to_show = get_name(update.message.from_user)
    bot.send_message(chat_id=update.message.chat.id, text="✅ {} is resting today!".format(name_to_show,))

def summary(bot, update):
    get_or_create_user(bot, update)
    parts = update.message.text.split(" ")
    delete_message(bot, update.message.chat.id, update.message.message_id)

    if len(parts) != 2:
        bot.send_message(chat_id=update.message.from_user.id, text="📧 Please give your email address or `off`!")
        return

    if parts[1] == "now":
        send_summary_email(update.message.from_user.id)
        bot.send_message(chat_id=update.message.from_user.id, text="📧 We've sent you a summary email!")
        return

    if parts[1] == "off":
        cursor = get_connection().cursor()
        cursor.execute('DELETE FROM summary WHERE id = %s', (update.message.from_user.id,))
        get_connection().commit()
        cursor.close()
        bot.send_message(chat_id=update.message.from_user.id, text="📧 Okay, you'll no longer receive weekly summaries!")
        return

    checked_addr = parseaddr(parts[1])[1]

    if "@" not in checked_addr:
        bot.send_message(chat_id=update.message.from_user.id, text="📧 It doesn't seem like your email address ({}) is valid!".format(checked_addr,))
        return

    cursor = get_connection().cursor()
    cursor.execute("INSERT INTO summary (id, email) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET email = %s", (update.message.from_user.id, checked_addr, checked_addr))
    get_connection().commit()
    cursor.close()
    bot.send_message(chat_id=update.message.from_user.id, text="📧 Great! You'll start receiving summaries to {}".format(checked_addr,))

def journaladd(bot, update):
    def validation_callback(parts):
        # String will always fit in db as db stores as much as max length for telegram message
        journalentry = " ".join(parts)
        journalentry_len = len(journalentry)
        if journalentry_len == 0 or journalentry_len > 4000:
            bot.send_message(chat_id=update.message.from_user.id, text="✏️  Please give a journal entry between 0 and 4000 characters! ✏️")
            return False
        return journalentry

    def success_callback(name_to_show, _, update, historic_date):
        bot.send_message(chat_id=update.message.chat.id, text="✅ {} logged a journal entry{}! ✏️".format(name_to_show, historic_date))

    delete_and_send(bot, update, validation_callback, success_callback, {
        "table_name": "journal",
        "wrong_length": "✏️  Please give a journal entry. ✏️",
        "value_error": "✏️  Please give a valid journal entry. ✏️" # Don't think this one will trigger
    })

def journallookup(bot, update):
    user_id = update.message.from_user.id
    username = get_name(update.message.from_user)
    parts = update.message.text.split(' ')
    datestring = " ".join(parts)

    # Parse the string - prefer DMY to MDY - most of world uses DMY
    dateinfo = dateparser.parse(datestring, settings={'DATE_ORDER': 'DMY', 'STRICT_PARSING': True})
    if dateinfo is not None:
        dateinfo = dateinfo.date()
        start_of_day = datetime.datetime(dateinfo.year, dateinfo.month, dateinfo.day)
        end_of_day = start_of_day + datetime.timedelta(days=1)
        entries = get_values("journal", start_date=start_of_day, end_date=end_of_day, user_id=user_id)
        entries_len = len(entries)

        delete_message(bot, update.message.chat.id, update.message.message_id)

        if entries_len == 0:
            bot.send_message(chat_id=update.message.chat.id, text="📓 {} had no journal entries on {}. 📓".format(username, dateinfo.isoformat()))

        for entry in entries:
            # Separate entry for each message, or we'll hit the telegram length limit for many (or just a few long ones) in one day
            bot.send_message(chat_id=update.message.chat.id, text="📓 Journal entry by {}, dated {}: {}".format(username, entry[2].strftime("%a. %d %B %Y %I:%M%p %Z"), entry[1]))
    else:
        bot.send_message(chat_id=update.message.from_user.id, text="Sorry, I couldn't understand that date format. 🤔")

def top(bot, update):
    get_or_create_user(bot, update)
    parts = update.message.text.split(" ")

    count = 5

    if len(parts) > 1:
        try:
            count = max(int(parts[1]), 1)
        except ValueError:
            pass

    count = min(count, 20)

    results = []
    cursor = get_connection().cursor()
    cursor.execute("SELECT * FROM users;")
    users = cursor.fetchall()
    get_connection().commit()
    for user in users:
        results.append((user[1], user[2], user[3], get_streak_of(user[0])))
    results.sort(key=lambda x: x[3], reverse=True)
    top_users = results[:count]

    line = []
    for i, user in enumerate(top_users):
        first_name, last_name, username, streak = user
        emoji = get_streak_emoji(streak)

        if username:
            name_to_show = username
        else:
            name_to_show = first_name
            if last_name:
                name_to_show += f' {last_name}'

        line.append(f'{i + 1}. {name_to_show}   ({streak}{emoji})')

    message = '\n'.join(line)
    delete_message(bot, update.message.chat.id, update.message.message_id)
    bot.send_message(chat_id=update.message.chat_id, text=message)

def streak(bot, update):
    get_or_create_user(bot, update)
    user_id = update.message.from_user.id
    streak = get_streak_of(user_id)
    emoji = get_streak_emoji(streak)

    delete_message(bot, update.message.chat.id, update.message.message_id)

    name_to_show = get_name(update.message.from_user)
    bot.send_message(chat_id=update.message.chat.id, text="{} has a meditation streak of {}! {}".format(name_to_show, streak, emoji))

def delete_and_send(bot, update, validation_callback, success_callback, strings, backdate=None):
    get_or_create_user(bot, update)
    parts = update.message.text.split(' ')
    #No command needs parts[0] as it's just the name of the command to be executed.
    parts = parts[1:]
    if len(parts) < 1:
        bot.send_message(chat_id=update.message.from_user.id, text=strings["wrong_length"])
        return

    #ALLOW A USER TO BACKDATE THEIR RECORD
    if len(parts) > 1:
        #Try to parse the last 'word' of the user input (eg 24-12-2017)
        #This will allow the user to backdate the message
        #If the parsing fails, they probably didn't try to backdate;
        #instead they entered a real word (or made a typo).
        backdate = dateparser.parse(parts[-1], settings={'DATE_ORDER': 'DMY', 'STRICT_PARSING': True})

        #Stop users from accidentally logging at a time they didn't want.
        #Limit the backdate feature to the last month only.
        now = datetime.datetime.now()
        month_ago = get_x_days_before(now, 31)
        if backdate is None:
            pass
        elif month_ago.date() <= backdate.date() <= now.date():
            #If they backdated, remove the parsed date word so it doesn't show up in the journal, exercise, etc
            parts = parts[:-1]
            backdate = backdate.replace(hour=12)
        else:
            # Error, the backdate was parsed but was not in the appropriate date range
            backdate_err = "The backdated date {} (from `{}`) did not take place in the last month.".format(backdate.date().isoformat(), parts[-1])
            bot.send_message(chat_id=update.message.from_user.id, text=backdate_err)
            return

    try:
        value = validation_callback(parts)
        if value is False:
            return
    except ValueError:
        bot.send_message(chat_id=update.message.from_user.id, text=strings["value_error"])
        return

    if backdate is None:
        backdate = update.message.date

    add_to_table(strings["table_name"], update.message.from_user.id, value, backdate)
    delete_message(bot, update.message.chat.id, update.message.message_id)

    historic_date = "" if backdate is None else " on " + backdate.date().isoformat()
    success_callback(get_name(update.message.from_user), value, update, historic_date)

def get_or_create_user(bot, update):
    user = update.message.from_user
    cursor = get_connection().cursor()

    cursor.execute('SELECT * FROM users WHERE id = %s', (user.id,))
    result = cursor.fetchone()

    if result is None:
        values = []
        for attribute in ['id', 'first_name', 'last_name', 'username']:
            value = getattr(user, attribute, None)
            values.append(value)

        # If command was run in public, ask them to PM us!
        if update.message.chat_id is not update.message.from_user.id:
            bot.send_message(chat_id=update.message.chat_id, text="Hey {}! Please message me at @zenafbot so that I can PM you!".format(get_name(user)))
            values.append(False)
        else:
            values.append(True)

        cursor.execute("INSERT INTO users(id, first_name, last_name, username, haspm) VALUES (%s, %s, %s, %s, %s)", values)

        cursor.execute('SELECT * FROM users WHERE id = %s', (user.id,))
        result = cursor.fetchone()

    get_connection().commit()
    cursor.close()
    return result

def get_name(user):
    name_to_show = "@" + user.username if user.username else user.full_name
    return name_to_show

def get_x_days_before(start_date, days_before):
    return start_date - datetime.timedelta(days=days_before)

def stats(bot, update):
    get_or_create_user(bot, update)
    parts = update.message.text.split(' ')
    command = parts[0].split("@")[0]
    user = update.message.from_user

    now = datetime.datetime.now()
    if len(parts) == 2:
        if parts[1] == 'weekly':
            start_date = get_x_days_before(now, 7)
        elif parts[1] == 'biweekly':
            start_date = get_x_days_before(now, 14)
        elif parts[1] == 'monthly':
            start_date = get_x_days_before(now, 31)
        elif parts[1] == 'all':
            # Unbounded search for all dates
            start_date = None
    else:
        # Default to a week ago
        start_date = get_x_days_before(now, 7)

    filename = "./{}-chart.png".format(user.id)
    if command == "/meditatestats":
        generate_graph("meditation", filename, user, start_date, now)
    elif command == "/anxietystats":
        generate_graph("anxiety", filename, user, start_date, now, line=True)
    elif command == "/sleepstats":
        generate_graph("sleep", filename, user, start_date, now, calc_average=True)
    elif command == "/groupstats":
        generate_graph("meditation", filename, user, start_date, now, all_data=True)
    elif command == "/happinessstats" or command == "/happystats":
        generate_graph("happiness", filename, user, start_date, now, line=True)
    elif command == "/fastingstats":
        generate_graph("fasting", filename, user, start_date, now)

    delete_message(bot, update.message.chat.id, update.message.message_id)

    with open(filename, 'rb') as photo:
        bot.send_photo(chat_id=update.message.chat_id, photo=photo)
    # Telegram API is synchronous, so it's OK to clean up now!
    os.remove(filename)

def get_chart_x_limits(start_date, end_date, dates):
    # Limits are difficult as start_date or end_date are allowed to be None
    # So set limit based on those if set, otherwise based on returned earliest/latest in data
    sorted_dates = sorted(dates)
    lower_limit = start_date.date() if start_date else sorted_dates[0]
    upper_limit = end_date.date() if end_date else sorted_dates[-1]
    return [lower_limit, upper_limit]

def gen_data_collection(results):
    dates_to_value_mapping = defaultdict(int)
    for result in results:
        dates_to_value_mapping[result[2].date()] += result[1]

    return dates_to_value_mapping.keys(), dates_to_value_mapping.values()

def generate_graph(table, filename, user, start_date, end_date, all_data=False, calc_average=False, line=False):
    user_id = None if all_data else user.id
    username = "Group" if all_data else get_name(user)
    results = get_values(table, start_date=start_date, end_date=end_date, user_id=user_id)

    if line:
        results = sorted(results, key=lambda x: x[2])
        values = [x[1] for x in results]
        dates = [x[2].date() for x in results]
    else:
        dates, values = gen_data_collection(results)

    if calc_average or line:
        title_text = "average: {:.1f}".format(float(sum(values)) / max(len(values), 1))
    else:
        title_text = "total: {:.1f}".format(sum(values))

    if table == "meditation":
        title_text += " minutes"
    elif table == "sleep" or table == "fasting":
        title_text += " hours"

    _, axis = plt.subplots()
    x_limits = get_chart_x_limits(start_date, end_date, dates)
    axis.set_xlim(x_limits)
    axis.xaxis_date()

    if line:
        axis.set_ylim([0, 10])
        sns.lineplot(dates, values)
    else:
        plt.bar(dates, values, align='center', alpha=0.5)

    sns.despine()

    interval = (x_limits[1] - x_limits[0]).days
    if interval > 10:
        axis.xaxis.set_major_locator(mdates.DayLocator(interval=math.ceil(interval/10)))
        axis.xaxis.set_minor_locator(mdates.DayLocator())
    else:
        axis.xaxis.set_major_locator(mdates.DayLocator())
    axis.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))

    plt.title('{}\'s {}\n{} days {}'.format(username, table, interval, title_text))
    plt.savefig(filename)
    plt.close()

def send_summaries(bot, job):
    now = datetime.datetime.now()
    seven_days_ago = get_x_days_before(now, 7)

    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM summary WHERE last_emailed < %s', (seven_days_ago,))
    results = cursor.fetchall()

    for result in results:
        send_summary_email(result[0])
        cursor.execute('UPDATE summary SET last_emailed = %s WHERE id = %s', (now, result[0]))

    get_connection().commit()
    cursor.close()

def send_summary_email(user_id):
    cursor = get_connection().cursor()

    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()

    cursor.execute('SELECT * FROM summary WHERE id = %s', (user_id,))
    result = cursor.fetchone()
    cursor.close()

    if user is None:
        return

    if result is None:
        return

    TO = result[1]

    def f(output):
        return "{:.2f}".format(output)

    def mean(results):
        dates, values = gen_data_collection(results)
        return float(sum(values)) / max(len(values), 1)

    now = datetime.datetime.now()
    seven_days_ago = get_x_days_before(now, 7).replace(hour=0, minute=0, second=0)
    body = ""

    meditation_events = get_values("meditation", start_date=seven_days_ago, end_date=now, user_id=user_id)
    if len(meditation_events) != 0:
        meditation_sum = f(sum([v[1] for v in meditation_events]))
        body += "🙏 Meditated "+meditation_sum+" total minutes\n"

    meditation_streak = str(get_streak_of(user_id))
    body += "🔥 Meditation streak is at "+meditation_streak+" days in a row\n"

    exercise_events = get_values("exercise", start_date=seven_days_ago, end_date=now, user_id=user_id)
    exercise_events_len = str(len(exercise_events))
    body += "💪 Exercised "+exercise_events_len+" times\n"

    sleep_events = get_values("sleep", start_date=seven_days_ago, end_date=now, user_id=user_id)
    if len(sleep_events) != 0 :
        sleep_mean = f(mean(sleep_events))
        body += "😴 Slept on average "+sleep_mean+" hours per night\n"

    happiness_events = get_values("happiness", start_date=seven_days_ago, end_date=now, user_id=user_id)
    if len(happiness_events) != 0:
        happiness_mean = f(mean(happiness_events))
        body += "🙂 Average happiness level was "+happiness_mean+"\n"

    anxiety_events = get_values("anxiety", start_date=seven_days_ago, end_date=now, user_id=user_id)
    if len(anxiety_events) != 0:
        anxiety_mean = f(mean(anxiety_events))
        body += "😅 Average anxiety level was "+anxiety_mean+"\n"

    TEXT = "Hi "+user[1]+"!\n\nHere are your logged stats for the last seven days:\n\n"+body+"\n\
Remember, you can log a multitude of things using the bot - check out /help for more details!\n\n\
❤️  Mindful Makers\n\
https://mindfulmakers.club/"

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(GMAIL_EMAIL, GMAIL_PASSWORD)

    try:
        m = MIMEText(TEXT.encode("UTF-8"), 'plain', "UTF-8")
        m["From"] = "Mindful Makers <"+GMAIL_EMAIL+">"
        m["To"] = TO
        m["Subject"] = "⛩ Weekly Summary"
        server.sendmail(GMAIL_EMAIL, [TO], m.as_string())
    except Exception as e:
        print(e)

    server.quit()

# Returns number of seconds until xx:00:00.
# If currently 11:43:23, then should return 37 + 60 * 16
def time_until_next_hour():
    now = datetime.datetime.now()
    return (60 - now.second) + 60 * (60 - now.minute)

#######################################################################################

cursor = get_connection().cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users(\
    id INTEGER UNIQUE NOT NULL,\
    first_name text NOT NULL,\
    last_name text,\
    username text,\
    haspm boolean DEFAULT FALSE\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS meditation(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value INTEGER NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS meditationreminders(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value INTEGER NOT NULL,\
    midnight INTEGER NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS anxiety(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value INTEGER NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS sleep(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value REAL NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS fasting(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value REAL NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS happiness(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value INTEGER NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS journal(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value varchar(4096) NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS exercise(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value varchar(4096) NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS done(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value varchar(4096) NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS summary(\
    id INTEGER UNIQUE NOT NULL REFERENCES users(id),\
    email varchar(128) NOT NULL,\
    last_emailed TIMESTAMP NOT NULL DEFAULT 'epoch',\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

get_connection().commit()
cursor.close()

DISPATCHER.add_handler(CommandHandler('anxiety', anxiety))
DISPATCHER.add_handler(CommandHandler('anxietystats', stats))
DISPATCHER.add_handler(CommandHandler('done', done))
DISPATCHER.add_handler(CommandHandler('exercise', exercise))
DISPATCHER.add_handler(CommandHandler('fast', fasting))
DISPATCHER.add_handler(CommandHandler('fasting', fasting))
DISPATCHER.add_handler(CommandHandler('fastingstats', stats))
DISPATCHER.add_handler(CommandHandler('groupstats', stats))
DISPATCHER.add_handler(CommandHandler('happinessstats', stats))
DISPATCHER.add_handler(CommandHandler('happiness', happiness))
DISPATCHER.add_handler(CommandHandler('happystats', stats))
DISPATCHER.add_handler(CommandHandler('help', help_message))
DISPATCHER.add_handler(CommandHandler('journal', journaladd))
DISPATCHER.add_handler(CommandHandler('journalentries', journallookup))
DISPATCHER.add_handler(CommandHandler('meditate', meditate))
DISPATCHER.add_handler(CommandHandler('meditation', meditate))
DISPATCHER.add_handler(CommandHandler('meditatestats', stats))
DISPATCHER.add_handler(CommandHandler('reminders', schedulereminders))
DISPATCHER.add_handler(CommandHandler('rest', rest))
DISPATCHER.add_handler(CommandHandler('sleep', sleep))
DISPATCHER.add_handler(CommandHandler('sleepstats', stats))
DISPATCHER.add_handler(CommandHandler('streak', streak))
DISPATCHER.add_handler(CommandHandler('summary', summary))
DISPATCHER.add_handler(MessageHandler(Filters.private, pm))

JOBQUEUE.run_repeating(executereminders, interval=3600, first=time_until_next_hour()+10)
JOBQUEUE.run_daily(send_summaries, time=datetime.time(18, 0, 0), days=(6,))

UPDATER.start_polling()
UPDATER.idle()
