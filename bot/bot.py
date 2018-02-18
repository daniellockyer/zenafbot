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
        if value > 7:
            em = "😥"
        elif value > 3:
            em = "😐"
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
    if user.username:
        name_to_show = "@" + user.username
    else:
        name_to_show = user.first_name
        if user.last_name:
            name_to_show += " " + user.last_name
    successCallback(name_to_show, value, update)

def stats(bot, update):
    db.get_or_create_user(update.message.from_user)
    parts = update.message.text.split(' ')
    command = parts[0]
    duration = 7

    if len(parts) == 2:
        if parts[1] == 'weekly':
            duration = 7
        elif parts[1] == 'biweekly':
            duration = 14
        elif parts[1] == 'monthly':
            duration = 30

    if command == "/meditatestats":
        generate_timelog_report_from("meditation", update.message.from_user.id, duration)
        with open('./chart.png', 'rb') as photo:
            bot.send_photo(chat_id=update.message.chat_id, photo=photo)
    elif command == "/anxietystats":
        generate_linechart_report_from("anxiety", update.message.from_user.id, duration)
        with open('./chart.png', 'rb') as photo:
            bot.send_photo(chat_id=update.message.chat_id, photo=photo)
    elif command == "/sleepstats":
        generate_timelog_report_from("sleep", update.message.from_user.id, duration)
        with open('./chart.png', 'rb') as photo:
            bot.send_photo(chat_id=update.message.chat_id, photo=photo)
    elif command == "/groupstats":
        generate_timelog_report_from("meditation", update.message.from_user.id, duration, all_data=True)
        with open('./chart.png', 'rb') as photo:
            bot.send_photo(chat_id=update.message.chat_id, photo=photo)

def generate_timelog_report_from(table, id, days, all_data=False):
    if all_data:
        results = db.get_all(table)
    else:
        results = db.get_values(table, id, days - 1)

    past_week = {}

    for days_to_subtract in reversed(range(days)):
        d = datetime.datetime.today() - datetime.timedelta(days=days_to_subtract)
        past_week[d.day] = 0

    for result in results:
        past_week[result[1].day] += result[0]

    total = sum(past_week.values())
    y_pos = np.arange(len(past_week.keys()))

    if table == "meditation":
        units = "minutes"
    elif table == "sleep":
        units = "hours"

    plt.bar(y_pos, past_week.values(), align='center', alpha=0.5)
    plt.xticks(y_pos, past_week.keys())
    plt.ylabel(table.title())
    plt.title('Last {} days report. Total: {} {}'.format(days, total, units))
    plt.savefig('chart.png')
    plt.close()

def generate_linechart_report_from(table, id, days):
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
    plt.title('Last {} days report. Average: {:.2f}'.format(days, average))
    plt.ylabel(table.title())

    plt.plot(dates, ratings)
    plt.savefig('chart.png')
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

updater.start_polling()
updater.idle()
