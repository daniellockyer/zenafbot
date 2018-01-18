from telegram.ext import Updater, CommandHandler
import logging
import db
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt; plt.rcdefaults()
import numpy as np
import matplotlib.pyplot as plt

import datetime

TOKEN = os.environ.get('BOT_TOKEN', None)
if TOKEN is None:
    raise Exception('No Token!')

updater = Updater(token=TOKEN)
dispatcher = updater.dispatcher

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def meditate(bot, update):
    db.get_or_create_user(update.message.from_user)
    if(len(update.message.text.split(' ')) == 2):
        db.increase_streak_of(update.message.from_user.id)

        minutes = update.message.text.split(' ')[1]
        db.add_timelog_to(update.message.from_user.id, minutes)

        bot.send_message(chat_id=update.message.chat_id, text="You have meditated today!")
    else:
        bot.send_message(chat_id=update.message.chat_id, text="You need to specify how many minutes did you meditate!")
    
def generate_past_week_report(results):
    
    now = datetime.datetime.now()
    past_week = {}
    for days_to_subtract in range(7):
        d = datetime.datetime.today() - datetime.timedelta(days=days_to_subtract)
        past_week[d.day] = 0

    for result in results:
        past_week[result[1].day] += result[0]
        
    y_pos = np.arange(len(past_week.keys()))
    performance = past_week.values()
 
    plt.bar(y_pos, performance, align='center', alpha=0.5)
    plt.xticks(y_pos, past_week)
    plt.ylabel('Minutes')
    plt.title('Last 7 days report')

    plt.savefig('barchart.png')

def stats(bot, update):
    db.get_or_create_user(update.message.from_user)

    results = db.get_past_week_timelog_from(update.message.from_user.id)
    generate_past_week_report(results)
    with open('./barchart.png', 'rb') as photo:
        bot.send_photo(chat_id=update.message.chat_id, photo=photo)


def format_top_results(arr):
    line = []
    for i, user in enumerate(arr):
        first_name = user[0]
        last_name = user[1]
        username = user[2]
        streak = user[3]

        if not username:
            name_to_show = first_name
            if last_name:
                full_name += f' {last_name}'
        else:
            name_to_show = username

        line.append(f'{i + 1}. {name_to_show}   ({streak}🔥)')
    return '\n'.join(line)

def top(bot, update):
    db.get_or_create_user(update.message.from_user)
    top_users = db.get_top(5)
    message = format_top_results(top_users)

    bot.send_message(chat_id=update.message.chat_id, text=message)

meditate_handler = CommandHandler('meditate', meditate)
stats_handler = CommandHandler('stats', stats)
top_handler = CommandHandler('top', top)

dispatcher.add_handler(meditate_handler)
dispatcher.add_handler(stats_handler)
dispatcher.add_handler(top_handler)

updater.start_polling()