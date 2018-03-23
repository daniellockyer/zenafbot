from collections import defaultdict
import datetime
import logging
import math
import os
import re
from pytz import timezone, all_timezones

import dateparser
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.error import BadRequest

import db

TOKEN = os.environ.get('BOT_TOKEN', None)
if TOKEN is None:
    raise Exception('No Token!')

updater = Updater(token=TOKEN)
dispatcher = updater.dispatcher
jobqueue = updater.job_queue

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def help(bot, update):
    message = \
        "/top = Shows top 5 people with the highest meditation count\n"\
        "/groupstats = Graph of total meditation time by the group\n"\
        "\n"\
        "/meditate [minutes] = Record your meditation (5 mins. minimum)\n"\
        "/anxiety [0-10] = Record your anxiety level (0 low, 10 high)\n"\
        "/sleep [0-24] = Record your sleep (hours)\n"\
        "/happiness [0-10] = Record your happiness level (0 low, 10 high)\n"\
        "/journal [entry] = Log a journal entry (Either publicly or in private to @zenafbot)\n"\
        "\n"\
        "/meditatestats [weekly|biweekly|monthly|all] = Graph of your meditation history\n"\
        "/anxietystats [weekly|biweekly|monthly|all] = Graph of your anxiety levels\n"\
        "/sleepstats [weekly|biweekly|monthly|all] = Graph of your sleep history\n"\
        "/happystats [weekly|biweekly|monthly|all] = Graph of your happiness levels\n"\
        "/journalentries day-month-year = Retrieve journal entries (eg. /journalentries 22-MARCH-2018)"

    try:
        bot.deleteMessage(chat_id=update.message.chat.id, message_id=update.message.message_id)
    except BadRequest:
        pass

    bot.send_message(chat_id=update.message.chat_id, text=message)

def pm(bot, update):
    user = get_or_create_user(bot, update)
    has_pm_bot = user[5]
    if has_pm_bot is True:
        bot.send_message(chat_id=update.message.from_user.id, text="Sorry, I didn't understand that!")
    else:
        db.set_has_pmed(update.message.from_user.id)
        bot.send_message(chat_id=update.message.from_user.id, text="Thanks for PMing me! 👋 Now I can PM you too! " \
            "📨 Please don't delete this chat or I won't be able PM you anymore. 😢 " \
            "Any command that you can perform with me in the Mindful Makers channel can also be ran here! " \
            "That way you can keep things private with me! 💖")

def meditate(bot, update):
    def validationCallback(parts):
        value = int(parts[1])
        if value < 5 or value > 1440:
            bot.send_message(chat_id=update.message.from_user.id, text="🙏 Meditation time must be between 5 and 1440 minutes. 🙏")
            return False
        return value

    def successCallback(name_to_show, value, update):
        bot.send_message(chat_id=update.message.chat.id, text="🙏 {} meditated for {} minutes 🙏".format(name_to_show, value))
        db.increase_streak_of(update.message.from_user.id)

    delete_and_send(bot, update, validationCallback, successCallback, {
        "table_name": "meditation",
        "wrong_length": "🙏 How many minutes did you meditate? 🙏",
        "value_error": "🙏 You need to specify the minutes as a number! 🙏"
    })

def schedulereminders(bot, update):
    parts = update.message.text.split(' ')
    if len(parts) == 2 and parts[1] == "off":
        #Delete is too powerful to have as a generalised function
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM meditationreminders WHERE id = %s', (update.message.from_user.id,))
        conn.commit()
        cursor.close()
        bot.send_message(chat_id=update.message.from_user.id, text="Okay, you won't recieve reminders anymore! ✌️")
        return True

    new_parts = []
    if parts[len(parts) - 1] in all_timezones:
        tz = timezone(parts[len(parts) - 1])
        for i in range(1, len(parts) - 1):
            part = parts[i]
            if not re.match('((([1-9])|(1[0-2]))(AM|PM|am|pm))', part):
                bot.send_message(chat_id=update.message.chat.id, text="Sorry, I didn't understand this hour: `{}`. "\
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
        bot.send_message(chat_id=update.message.chat.id, text="Sorry, I didn't understand the timezone you specified: `{}`. "\
                        "It can take the form of a specific time like `UTC` or as for a country `Europe/Amsterdam`. "\
                        "The whole command should look similar to this: "\
                        "`\\reminders 1PM 5PM 11PM UTC`. You can specify as many hours as you like.".format(parts[len(parts) - 1]))
        return False

    user = get_or_create_user(bot, update)
    for hours in new_parts:
        db.add_meditation_reminder(update.message.from_user.id, hours[0], hours[1])
    username = get_name(update.message.from_user)
    has_pm_bot = user[5]
    if has_pm_bot is True:
        bot.send_message(chat_id=update.message.from_user.id, text="Okay {}, I've scheduled those reminders for you! 🕑".format(username))
    else:
        bot.send_message(chat_id=update.message.chat.id, text="Okay {}, I've scheduled those reminders for you! 🕑 "/
                            "If you haven't already, please send me a PM at @zenafbot so that I can PM your reminders to you!")


def executereminders(bot, job):
    now = datetime.datetime.now()
    users_to_notify = db.get_values("meditationreminders", value=now.hour)
    for user in users_to_notify:
        user_id = user[0]
        user_midnight_utc = user[2] #Will be an int like 2, meaning midnight is at 2AM UTC for the user
        #We don't want to notify if the user already meditated today
        #Because of timezones, 'today' probably means something different for user
        #So we check between their midnight and now
        if user_midnight_utc > now.hour:
            start_check_period = get_x_days_before(now, 1).replace(hour=user_midnight_utc, minute=0, second=0)
        else:
            start_check_period = now.replace(hour=user_midnight_utc, minute=0, second=0)
        meditations = db.get_values("meditation", start_date=start_check_period, end_date=now, user_id=user_id)
        if len(meditations) == 0:
            bot.send_message(chat_id=user_id, text="Hey! You asked me to send you a private message to remind you to meditate! 🙏 "\
                                               "You can turn off these notifications with `/reminders off`. 🕑")

def find_rating_change(table, user_id, new_value):
    now = datetime.datetime.now()
    yesterday = get_x_days_before(now, 1)
    # We want to find change in rating between current value and most recent value in 24 last hours
    ratings_last_day = db.get_values(table, start_date=yesterday, end_date=now, user_id=user_id)
    difference_str = ""
    if len(ratings_last_day) > 1:
        ratings_last_day.sort(key=lambda r: r[2], reverse=True)
        difference = new_value - ratings_last_day[1][1]
        difference_str = ' ({})'.format("{:+}".format(difference) if difference else "no change")
    return difference_str

def anxiety(bot, update):
    def validationCallback(parts):
        value = int(parts[1])
        if value < 0 or value > 10:
            bot.send_message(chat_id=update.message.from_user.id, text="Please rate your anxiety between 0 (low) and 10 (high).")
            return False
        return value

    def successCallback(name_to_show, value, update):
        if value >= 9:
            em = "😭"
        elif value >= 7:
            em = "😦"
        elif value >= 5:
            em = "😐"
        elif value >= 3:
            em = "🙂"
        else:
            em = "😎"

        difference = find_rating_change("anxiety", update.message.from_user.id, value)
        bot.send_message(chat_id=update.message.chat.id,
                         text="{} {} rated their anxiety at {}{} {}".format(em, name_to_show, value, difference, em))

    delete_and_send(bot, update, validationCallback, successCallback, {
        "table_name": "anxiety",
        "wrong_length": "Please give your anxiety levels.",
        "value_error": "You need to specify the value as a number."
    })

def happiness(bot, update):
    def validationCallback(parts):
        value = int(parts[1])
        if value < 0 or value > 10:
            bot.send_message(chat_id=update.message.chat.id, text="Please rate your happiness level 0-10")
            return False
        return value

    def successCallback(name_to_show, value, update):
        if value >= 9:
            em = "😎"
        elif value >= 7:
            em = "😄"
        elif value >= 5:
            em = "🙂"
        elif value >= 4:
            em = "😐"
        elif value >= 3:
            em = "😕"
        elif value >= 1:
            em = "😦"
        else:
            em = "😭"

        difference = find_rating_change("anxiety", update.message.from_user.id, value)
        bot.send_message(chat_id=update.message.chat.id,
                         text="{} {} rated their happiness at {}{} {}".format(em, name_to_show, value, difference, em))

    delete_and_send(bot, update, validationCallback, successCallback, {
        "table_name": "happiness",
        "wrong_length": "Please rate your happiness level between 0-10",
        "value_error": "You need to specify the value as a decimal number (eg. 7.5)"
    })

def sleep(bot, update):
    def validationCallback(parts):
        value = float(parts[1])
        if value < 0 or value > 24:
            bot.send_message(chat_id=update.message.from_user.id, text="💤 Please give how many hours you slept. 💤")
            return False
        return value

    def successCallback(name_to_show, value, update):
        bot.send_message(chat_id=update.message.chat.id, text="💤 {} slept for {} hours 💤".format(name_to_show, value))

    delete_and_send(bot, update, validationCallback, successCallback, {
        "table_name": "sleep",
        "wrong_length": "💤 Please give how many hours you slept. 💤",
        "value_error": "💤 You need to specify the value as a decimal number (eg. 7.5) 💤"
    })

#Add an entry to your journal
def journaladd(bot, update):
    def validationCallback(parts):
        #String will always fit in db as db stores as much as max length for telegram message
        del parts[0]
        journalentry = " ".join(parts)
        if len(journalentry) == 0 or len(journalentry) > 4000:
            bot.send_message(chat_id=update.message.from_user.id, text="✏️ Please give a journal entry between 0 and 4000 characters! ✏️")
            return False
        return journalentry

    def successCallback(name_to_show, _, update):
        bot.send_message(chat_id=update.message.chat.id, text="✏️ {} logged a journal entry! ✏️".format(name_to_show))

    delete_and_send(bot, update, validationCallback, successCallback, {
        "table_name": "journal",
        "wrong_length": "✏️ Please give a journal entry. ✏️",
        "value_error": "✏️ Please give a valid journal entry. ✏️" #Don't think this one will trigger
    })

#Recall entries from your journal for a particular day
def journallookup(bot, update):
    user_id = update.message.from_user.id
    username = get_name(update.message.from_user)
    parts = update.message.text.split(' ')
    del parts[0]
    datestring = " ".join(parts)

    #Parse the string - prefer DMY to MDY - most of world uses DMY
    dateinfo = dateparser.parse(datestring, settings={'DATE_ORDER': 'DMY', 'STRICT_PARSING': True})
    if dateinfo is not None:
        dateinfo = dateinfo.date()
        start_of_day = datetime.datetime(dateinfo.year, dateinfo.month, dateinfo.day)
        end_of_day = start_of_day + datetime.timedelta(days=1)
        entries = db.get_values("journal", start_date=start_of_day, end_date=end_of_day, user_id=user_id)

        try:
            bot.deleteMessage(chat_id=update.message.chat.id, message_id=update.message.message_id)
        except BadRequest:
            pass

        if len(entries) == 0:
            bot.send_message(chat_id=update.message.chat.id, text="📓 {} had no journal entries on {}. 📓".format(username, dateinfo.isoformat()))

        for entry in entries:
            #Seperate entry for each message, or we'll hit the telegram length limit for many (or just a few long ones) in one day
            bot.send_message(chat_id=update.message.chat.id, text="📓 Journal entry by {}, dated {}: {}".format(username, entry[1].strftime("%a. %d %B %Y %I:%M%p %Z"), entry[0]))
    else:
        bot.send_message(chat_id=update.message.chat.id, text="Sorry, I couldn't understand that date format. 🤔")

def top(bot, update):
    get_or_create_user(bot, update)
    top_users = db.get_top(5)
    line = []
    for i, user in enumerate(top_users):
        first_name = user[0]
        last_name = user[1]
        username = user[2]
        streak = user[3]

        if username:
            name_to_show = username
        else:
            name_to_show = first_name
            if last_name:
                name_to_show += f' {last_name}'

        line.append(f'{i + 1}. {name_to_show}   ({streak}🔥)')

    message = '\n'.join(line)
    bot.send_message(chat_id=update.message.chat_id, text=message)

def delete_and_send(bot, update, validationCallback, successCallback, strings):
    get_or_create_user(bot, update)
    parts = update.message.text.split(' ')
    if len(parts) < 2:
        bot.send_message(chat_id=update.message.from_user.id, text=strings["wrong_length"])
        return

    try:
        value = validationCallback(parts)
        if value is False:
            return
    except ValueError:
        bot.send_message(chat_id=update.message.from_user.id, text=strings["value_error"])
        return

    db.add_to_table(strings["table_name"], update.message.from_user.id, value)
    try:
        bot.deleteMessage(chat_id=update.message.chat.id, message_id=update.message.message_id)
    except BadRequest:
        pass

    user = update.message.from_user
    name_to_show = get_name(user)
    successCallback(name_to_show, value, update)

def get_or_create_user(bot, update):
    user = update.message.from_user
    cursor = db.get_connection().cursor()

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


    db.get_connection().commit()
    cursor.close()
    return result

def get_name(user):
    if user.username:
        name_to_show = "@" + user.username
    else:
        name_to_show = user.full_name
    return name_to_show

def get_x_days_before(start_date, days_before):
    return start_date - datetime.timedelta(days=days_before)

def stats(bot, update):
    get_or_create_user(bot, update)
    parts = update.message.text.split(' ')
    command = parts[0].split("@")[0]
    duration = 7
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
            #Unbounded search for all dates
            start_date = None
    else:
        #Default to a week ago
        start_date = get_x_days_before(now, 7)

    filename = "./{}-chart.png".format(user.id)
    if command == "/meditatestats":
        generate_timelog_report_from("meditation", filename, user, start_date, now)
    elif command == "/anxietystats":
        generate_linechart_report_from("anxiety", filename, user, start_date, now)
    elif command == "/sleepstats":
        generate_timelog_report_from("sleep", filename, user, start_date, now)
    elif command == "/groupstats":
        generate_timelog_report_from("meditation", filename, user, start_date, now, all_data=True)
    # synonyms as 'happinessstats' is weird AF
    elif command == "/happinessstats" or command == "/happystats":
        generate_linechart_report_from("happiness", filename, user, start_date, now)

    try:
        bot.deleteMessage(chat_id=update.message.chat.id, message_id=update.message.message_id)
    except BadRequest:
        pass

    with open(filename, 'rb') as photo:
        bot.send_photo(chat_id=update.message.chat_id, photo=photo)
    #Telegram API is synchronous, so it's OK to clean up now!
    os.remove(filename)

def get_chart_x_limits(start_date, end_date, dates):
    #Limits are difficult as start_date or end_date are allowed to be None
    #So set limit based on those if set, otherwise based on returned earliest/latest in data
    sorted_dates = sorted(dates)
    lower_limit = start_date.date() if start_date else sorted_dates[0]
    upper_limit = end_date.date() if end_date else sorted_dates[-1]
    return [lower_limit, upper_limit]

def generate_timelog_report_from(table, filename, user, start_date, end_date, all_data=False):
    user_id = None if all_data else user.id
    username = "Group" if all_data else get_name(user)
    results = db.get_values(table, start_date=start_date, end_date=end_date, user_id=user_id)

    dates_to_value_mapping = defaultdict(int)
    for result in results:
        dates_to_value_mapping[result[2].date()] += result[1]

    dates = dates_to_value_mapping.keys()
    values = dates_to_value_mapping.values()
    total = sum(values)

    if table == "meditation":
        units = "minutes"
    elif table == "sleep":
        units = "hours"

    _, ax = plt.subplots()

    x_limits = get_chart_x_limits(start_date, end_date, dates)
    ax.set_xlim(x_limits)
    ax.xaxis_date()

    plt.bar(dates, values, align='center', alpha=0.5)
    plt.ylabel(table.title())

    interval = (x_limits[1] - x_limits[0]).days
    #Try to keep the ticks on the x axis readable by limiting to max of 25
    if interval > 25:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=math.ceil(interval/25)))
        ax.xaxis.set_minor_locator(mdates.DayLocator())
    else:
        ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    plt.title('{}\'s {} chart\n{} days report. Total: {:.1f} {}'.format(username, table, interval, total, units))
    plt.savefig(filename)
    plt.close()

def generate_linechart_report_from(table, filename, user, start_date, end_date):
    user_id = user.id
    username = get_name(user)
    results = db.get_values(table, start_date=start_date, end_date=end_date, user_id=user_id)

    ratings = [x[1] for x in results]
    dates = [x[2] for x in results]
    average = float(sum(ratings)) / max(len(ratings), 1)

    _, ax = plt.subplots()

    x_limits = get_chart_x_limits(start_date, end_date, [x.date() for x in dates])
    ax.set_xlim(x_limits)
    ax.set_ylim([0, 10])

    interval = (x_limits[1] - x_limits[0]).days
    #Try to keep the ticks on the x axis readable by limiting to max of 25
    if interval > 25:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=math.ceil(interval/25)))
        ax.xaxis.set_minor_locator(mdates.DayLocator())
    else:
        ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    plt.title('{}\'s {} chart\n{} days report. Average: {:.2f}'.format(username, table, interval, average))
    plt.ylabel(table.title())

    plt.plot(dates, ratings)
    plt.savefig(filename)
    plt.close()

#Returns number of seconds until xx:00:00.
#If currently 11:43:23, then should return 37 + 60 * 16
def time_until_next_hour():
    now = datetime.datetime.now()
    return (60 - now.second) + 60 * (60 - now.minute)

#######################################################################################

cursor = db.get_connection().cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users(\
    id INTEGER UNIQUE NOT NULL,\
    first_name text NOT NULL,\
    last_name text,\
    username text,\
    streak INTEGER NOT NULL DEFAULT 0,\
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

cursor.execute("CREATE TABLE IF NOT EXISTS happiness(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value INTEGER NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

# 4096 is max length of a telegram message;
# We should store 4000 to give us some room when sending the user a
# journal message they have recalled.
cursor.execute("CREATE TABLE IF NOT EXISTS journal(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value varchar(4096) NOT NULL,\
    created_at TIMESTAMP NOT NULL DEFAULT now()\
);")

db.get_connection().commit()
cursor.close()

dispatcher.add_handler(CommandHandler('help', help))

dispatcher.add_handler(CommandHandler('anxiety', anxiety))
dispatcher.add_handler(CommandHandler('anxietystats', stats))
dispatcher.add_handler(CommandHandler('meditate', meditate))
dispatcher.add_handler(CommandHandler('meditatestats', stats))
dispatcher.add_handler(CommandHandler('sleep', sleep))
dispatcher.add_handler(CommandHandler('sleepstats', stats))
dispatcher.add_handler(CommandHandler('top', top))
dispatcher.add_handler(CommandHandler('groupstats', stats))
dispatcher.add_handler(CommandHandler('happiness', happiness))
# Next two are synonyms as 'happinessstats' is weird AF
dispatcher.add_handler(CommandHandler('happystats', stats))
dispatcher.add_handler(CommandHandler('happinessstats', stats))
dispatcher.add_handler(CommandHandler('journal', journaladd))
dispatcher.add_handler(CommandHandler('journalentries', journallookup))
dispatcher.add_handler(CommandHandler('reminders', schedulereminders))
# Respond to private messages
dispatcher.add_handler(MessageHandler(Filters.private, pm))

#Run the function on every hour to remind people to meditate
jobqueue.run_repeating(executereminders, interval=3600, first=time_until_next_hour()+10)


updater.start_polling()
updater.idle()
