from telegram.ext import Updater, CommandHandler
import logging
import db
import os

TOKEN = os.environ.get('BOT_TOKEN', None)
if TOKEN is None:
    raise Exception('No Token!')

updater = Updater(token=TOKEN)
dispatcher = updater.dispatcher

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def meditate(bot, update):
    db.get_or_create_user(update.message.from_user)
    db.increase_streak_of(update.message.from_user.id)
    
    bot.send_message(chat_id=update.message.chat_id, text="You have meditated today!")

def stats(bot, update):
    db.get_or_create_user(update.message.from_user)
    streak = db.get_streak_of(update.message.from_user.id)
    bot.send_message(chat_id=update.message.chat_id, text=f"Your streak is {streak}!")

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