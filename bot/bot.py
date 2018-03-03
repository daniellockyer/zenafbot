import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.cbook as cbook
from telegram.ext import Updater, CommandHandler
from telegram.error import BadRequest
import db

import logging
import datetime
import os
from collections import defaultdict

TOKEN = os.environ.get('BOT_TOKEN', None)
if TOKEN is None:
    raise Exception('No Token!')

updater = Updater(token=TOKEN)
dispatcher = updater.dispatcher

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

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

        # We want to find change in anxiety
        anxiety_last_day = db.get_values("anxiety", update.message.from_user.id, 1)
        difference_str = ""
        if len(anxiety_last_day) > 1:
            anxiety_last_day.sort(key=lambda r: r[1], reverse=True)
            difference = value - anxiety_last_day[1][0]
            difference_str = ' ({})'.format("{:+}".format(difference) if difference else "no change")

        bot.send_message(chat_id=update.message.chat.id,
            text="{} {} rated their anxiety at {}{} {}".format(em, name_to_show, value, difference_str, em))

    delete_and_send(bot, update, validationCallback, successCallback, {
        "table_name": "anxiety",
        "wrong_length": "Please give your anxiety levels.",
        "value_error": "You need to specify the value as a number."
    })

        #adding a happiness command
def happiness(bot,update):
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

        # We want to find change in happiness
        happiness_last_day = db.get_values("happiness", update.message.from_user.id, 1)
        difference_str = ""
        if len(happiness_last_day) > 1:
            happiness_last_day.sort(key=lambda r: r[1], reverse=True)
            difference = value - happiness_last_day[1][0]
            difference_str = ' ({})'.format("{:+}".format(difference) if difference else "no change")

        bot.send_message(chat_id=update.message.chat.id,
            text="{} {} rated their happiness at {}{} {}".format(em, name_to_show, value, difference_str, em))

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

def top(bot, update):
    db.get_or_create_user(update.message.from_user)
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
    db.get_or_create_user(update.message.from_user)
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

def get_name(user):
    if user.username:
        name_to_show = "@" + user.username
    else:
        name_to_show = user.first_name
        if user.last_name:
            name_to_show += " " + user.last_name
    return name_to_show

def stats(bot, update):
    db.get_or_create_user(update.message.from_user)
    parts = update.message.text.split(' ')
    command = parts[0].split("@")[0]
    duration = 7
    user = update.message.from_user

    if len(parts) == 2:
        if parts[1] == 'weekly':
            duration = 7
        elif parts[1] == 'biweekly':
            duration = 14
        elif parts[1] == 'monthly':
            duration = 30

    filename = "./{}-chart.png".format(user.id)
    if command == "/meditatestats":
        generate_timelog_report_from("meditation", filename, user, duration)
    elif command == "/anxietystats":
        generate_linechart_report_from("anxiety", filename, user, duration)
    elif command == "/sleepstats":
        generate_timelog_report_from("sleep", filename, user, duration)
    elif command == "/groupstats":
        generate_timelog_report_from("meditation", filename, user, duration, all_data=True)
    # synonyms as 'happinessstats' is weird AF
    elif command == "/happinessstats" or command == "/happystats":
        generate_linechart_report_from("happiness", filename, user, duration)

    with open(filename, 'rb') as photo:
        bot.send_photo(chat_id=update.message.chat_id, photo=photo)
    #Telegram API is synchronous, so it's OK to clean up now!
    os.remove(filename)

def generate_timelog_report_from(table, filename, user, days, all_data=False):
    id = user.id
    if all_data:
        results = db.get_all(table, days - 1)
        username = "Group"
    else:
        results = db.get_values(table, id, days - 1)
        username = get_name(user)

    dates_to_value_mapping = defaultdict(int)
    for result in results:
        dates_to_value_mapping[result[1].date()] += result[0]

    dates = dates_to_value_mapping.keys()
    values = dates_to_value_mapping.values()
    total = sum(values)

    if table == "meditation":
        units = "minutes"
    elif table == "sleep":
        units = "hours"

    #Give the x axis correct scale
    fig, ax = plt.subplots()
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    now = datetime.datetime.now()
    days_ago = now - datetime.timedelta(days=days)
    ax.set_xlim([days_ago,now])
    ax.xaxis_date()

    plt.bar(dates, values, align='center', alpha=0.5)
    plt.ylabel(table.title())
    plt.title('{}\'s {} chart\nLast {} days report. Total: {} {}'.format(username, table, days, total, units))
    plt.savefig(filename)
    plt.close()

def generate_linechart_report_from(table, filename, user, days):
    username = get_name(user)
    id = user.id
    results = db.get_values(table, id, days - 1)
    ratings = [x[0] for x in results]
    dates = [x[1] for x in results]
    average = np.mean(ratings)
    fig, ax = plt.subplots()
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))

    now = datetime.datetime.now()
    days_ago = now - datetime.timedelta(days=days)
    ax.set_xlim([days_ago,now])
    ax.set_ylim([0,10])
    plt.title('{}\'s {} chart\nLast {} days report. Average: {:.2f}'.format(username, table, days, average))
    plt.ylabel(table.title())

    plt.plot(dates, ratings)
    plt.savefig(filename)
    plt.close()

#######################################################################################

cursor = db.get_connection().cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users(\
    id INTEGER UNIQUE NOT NULL,\
    first_name text NOT NULL,\
    last_name text,\
    username text,\
    streak INTEGER NOT NULL DEFAULT 0\
);")

cursor.execute("CREATE TABLE IF NOT EXISTS meditation(\
    id INTEGER NOT NULL REFERENCES users(id),\
    value INTEGER NOT NULL,\
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

db.get_connection().commit()
cursor.close()

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

updater.start_polling()
updater.idle()
