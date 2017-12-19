from telegram.ext import Updater, CommandHandler
import parsedatetime as pdt
from datetime import datetime
import json
import os.path
import sys
import traceback
from random import random

class Message(object):
    def __init__(self, message=None, finish_time=None, data=None, is_schedulable=None, bot=None):
        if message is not None and finish_time is not None:
            self.message = message
            self.finish_time = finish_time
            self.id = int(random() * 1000)
            self.is_schedulable = is_schedulable
        elif data is not None:
            self.load_from_json(data)
        else:
            raise Exception("Wrong Message constructor context")

    def __repr__(self):
        schedulable_string = ""
        if self.is_schedulable:
            schedulable_string = "Через сколько:   {eta}\n".format(
                eta=str(self.finish_time - datetime.now())
            )
        return "Когда:                   {finish_time}\n{schedulable_string}Сообщение:        {message}\nИдентификатор: {id}".format(
            finish_time=self.finish_time.strftime("%Y-%m-%d %H:%M:%S"),
            schedulable_string=schedulable_string,
            message=self.message,
            id=self.id
        )

    def dump_to_json(self):
        return {
            'eta': self.finish_time.strftime("%s"),
            'message': self.message,
            'id': self.id,
            'is_schedulable': self.is_schedulable
        }

    def load_from_json(self, data):
        self.message = data['message']
        self.finish_time = datetime.fromtimestamp(int(data['eta']))
        self.id = int(data['id'])
        self.is_schedulable = int(data['is_schedulable'])


def alarm(bot, job):
    (timer_message_controller, message_collection, message) = job.context
    message_collection.delete_message(message)


class TimerMessageController(object):
    def __init__(self, bot, chat_id, job_queue):
        self.bot = bot
        self.chat_id = chat_id
        self.job_queue = job_queue
        self.jobs = {}

    def send_message(self, message, status):
        self.bot.send_message(self.chat_id, text='---- {status} ---- \n{message}'.format(status=status, message=message))

    def send_notification(self, notification):
        self.bot.send_message(self.chat_id, notification)

    def set_alarm(self, message_collection, message, silent=None):
        if message.is_schedulable:
            if message.finish_time <= datetime.now():
                message_collection.delete_message(message)
            else:
                due = (message.finish_time - datetime.now()).seconds
                self.jobs[message.id] = self.job_queue.run_once(alarm, due, context=(self, message_collection, message))
        if not silent:
            self.send_message(message, "Добавлено")

    def cancel_alarm(self, message):
        if message.id in self.jobs:
            self.jobs[message.id].schedule_removal()
            del self.jobs[message.id]
        self.send_message(message, "Завершено")


class MessageCollection(object):
    def __init__(self, store_name, timer_message_controller):
        self.store_name = store_name
        self.timer_message_controller = timer_message_controller
        self.message_dict = {}
        self.load_messages()

    def get_filename(self):
        return "/tmp/chat_info_{store_name}".format(store_name=self.store_name)

    def load_messages(self):
        if os.path.isfile(self.get_filename()):
            with open(self.get_filename(), 'r') as f:
                read_count = 0
                for line in f.read().split('\n'):
                    if not line:
                        break
                    self.add_message(Message(data=json.loads(line)), silent=True)
                    read_count += 1
            print("Done reading {read_count} from {filename}".format(read_count=read_count, filename=self.get_filename()))

    def dump_messages(self):
        with open(self.get_filename(), 'w') as f:
            for message in sorted(self.message_dict.values(), key=lambda x: x.finish_time):
                f.write(json.dumps(message.dump_to_json()) + "\n")
        print("Done writing to {filename}".format(filename=self.get_filename()))

    def add_message(self, message, silent=None):
        self.message_dict[message.id] = message
        self.timer_message_controller.set_alarm(self, message, silent)
        self.dump_messages()

    def delete_message_by_id(self, message_id):
        if message_id in self.message_dict:
            self.delete_message(self.message_dict[message_id])

    def delete_message(self, message):
        if message.id in self.message_dict:
            del self.message_dict[message.id]
        self.timer_message_controller.cancel_alarm(message)
        self.dump_messages()

    def output_all_messages(self):
        if len(self.message_dict) == 0:
            self.timer_message_controller.send_notification("Нет дел")
        for message in sorted(self.message_dict.values(), key=lambda x: x.finish_time):
            self.timer_message_controller.send_message(message, "В списке")


def start(bot, update):
    update.message.reply_text('Привет! Ты можешь пользоваться командами "/хочу", "/напомни", "/отмени", "/удали", "/сделал", "/список", "/дела"')

def init_chat_data(update, chat_data, bot, job_queue):
    chat_id = update.message.chat_id
    if 'message_collection' not in chat_data:
        chat_data['message_collection'] = MessageCollection(chat_id, TimerMessageController(bot, chat_id, job_queue))

def handle_exception(update):
    exc_type, exc_value, exc_traceback = sys.exc_info()
    traceback.print_tb(exc_traceback, limit=10, file=sys.stdout)
    update.message.reply_text(traceback.format_exception(exc_type, exc_value,
                                                         exc_traceback))

def register_event(bot, update, args, job_queue, chat_data):
    print("Start register_event")
    try:
        init_chat_data(update, chat_data, bot, job_queue)
        string = " ".join(args)
        c = pdt.Constants("ru_RU")
        p = pdt.Calendar(c)
        finish_time, status = p.parseDT(string)
        chat_data['message_collection'].add_message(Message(message=string,
            finish_time=finish_time, is_schedulable=(status > 0),
            bot=bot), silent=False)
    except:
        handle_exception(update)

def cancel_event(bot, update, args, job_queue, chat_data):
    print("Start cancel_event")
    try:
        init_chat_data(update, chat_data, bot, job_queue)
        for message_id in args:
            chat_data['message_collection'].delete_message_by_id(int(message_id))
    except:
        handle_exception(update)

def show_events(bot, update, args, job_queue, chat_data):
    print("Start show_events")
    try:
        init_chat_data(update, chat_data, bot, job_queue)
        chat_data['message_collection'].output_all_messages()
    except:
        handle_exception(update)

if __name__ == '__main__':
    updater = Updater("428153204:AAHNuH7Gwfl5zEBdyhgEfO-zwXjkh-XyUcY")
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    for word in ("хочу", "напомни"):
        dp.add_handler(CommandHandler(word, register_event, pass_args=True, pass_job_queue=True, pass_chat_data=True))
    for word in ("сделал", "отмени", "удали"):
        dp.add_handler(CommandHandler(word, cancel_event, pass_args=True, pass_job_queue=True, pass_chat_data=True))
    for word in ("список", "дела"):
        dp.add_handler(CommandHandler(word, show_events, pass_args=True, pass_job_queue=True, pass_chat_data=True))
    updater.start_polling()
    updater.idle()
