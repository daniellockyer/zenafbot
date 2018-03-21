import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.cbook as cbook
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.error import BadRequest
import db
import dateparser
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

    def successCallback(name_to_show, value, update):
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
        dates_to_value_mapping[result[1].date()] += result[0]

    dates = dates_to_value_mapping.keys()
    values = dates_to_value_mapping.values()
    total = sum(values)

    if table == "meditation":
        units = "minutes"
    elif table == "sleep":
        units = "hours"

    fig, ax = plt.subplots()

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

    ratings = [x[0] for x in results]
    dates = [x[1] for x in results]
    average = float(sum(ratings)) / max(len(ratings), 1)

    fig, ax = plt.subplots()

    x_limits = get_chart_x_limits(start_date, end_date, [x.date() for x in dates])
    ax.set_xlim(x_limits)
    ax.set_ylim([0,10])

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
# Respond to private messages
dispatcher.add_handler(MessageHandler(Filters.private, pm))

updater.start_polling()
updater.idle()
