import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    ConversationHandler,
    MessageHandler,
    filters,
)
from pymongo import MongoClient
from bson.objectid import ObjectId
from mongo_config import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION_NAME
from tokens import token as tkn
from datetime import datetime
import pytz

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Подключение к MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
tasks_collection = db[MONGO_COLLECTION_NAME]

# Состояния для ConversationHandler
TASK_DESCRIPTION, ASSIGNEE, DEADLINE, REMINDER = range(4)

# Команда /start с кнопками
async def start(update: Update, context: CallbackContext) -> None:
    reply_keyboard = [['/addtask', '/tasks'], ['/done']]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    await update.message.reply_text(
        'Привет! Я бот для планирования семейных задач. Выберите команду:',
        reply_markup=markup
    )

# Команда /addtask
async def add_task(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Отмена']]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    await update.message.reply_text('Введите описание задачи:', reply_markup=markup)
    return TASK_DESCRIPTION

# Получение описания задачи
async def task_description(update: Update, context: CallbackContext) -> int:
    context.user_data['task_description'] = update.message.text
    reply_keyboard = [['Отмена']]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    await update.message.reply_text('Введите имя исполнителя:', reply_markup=markup)
    return ASSIGNEE

# Получение имени исполнителя
async def assignee(update: Update, context: CallbackContext) -> int:
    context.user_data['assignee'] = update.message.text
    reply_keyboard = [['Отмена']]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    await update.message.reply_text('Укажите дедлайн в формате ДД:ММ:ГГГГ:', reply_markup=markup)
    return DEADLINE

# Получение дедлайна
async def deadline(update: Update, context: CallbackContext) -> int:
    deadline_text = update.message.text
    try:
        deadline_date = datetime.strptime(deadline_text, '%d:%m:%Y')
        context.user_data['deadline'] = deadline_date.strftime('%d:%m:%Y')
        reply_keyboard = [['Отмена']]
        markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        await update.message.reply_text('Введите время напоминания (в формате ЧЧ:ММ, 24-часовой формат):', reply_markup=markup)
        return REMINDER
    except ValueError:
        await update.message.reply_text('Неправильный формат дедлайна. Пожалуйста, укажите дедлайн в формате ДД:ММ:ГГГГ.')
        return DEADLINE

# Получение времени напоминания и сохранение задачи
async def reminder(update: Update, context: CallbackContext) -> int:
    reminder_time = update.message.text
    try:
        reminder_hour, reminder_minute = map(int, reminder_time.split(':'))
        
        if not (0 <= reminder_hour < 24 and 0 <= reminder_minute < 60):
            raise ValueError("Неправильное время. Используйте 24-часовой формат (ЧЧ:ММ).")
        
        task = {
            'description': context.user_data['task_description'],
            'assignee': context.user_data['assignee'],
            'deadline': context.user_data['deadline'],
            'reminder': reminder_time,
            'status': 'pending',
            'chat_id': update.message.chat_id
        }
        result = tasks_collection.insert_one(task)
        task_id = str(result.inserted_id)

        reply_keyboard = [['/addtask', '/tasks']]
        markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        await update.message.reply_text(f'Задача успешно добавлена! ID задачи: {task_id}', reply_markup=markup)
        return ConversationHandler.END
    except ValueError as e:
        await update.message.reply_text(f'Ошибка: {e} Пожалуйста, укажите время в формате ЧЧ:ММ (24-часовой формат).')
        return REMINDER
    except Exception as e:
        await update.message.reply_text(f'Произошла ошибка: {e}')
        return REMINDER

# Команда /tasks с кнопками
async def list_tasks(update: Update, context: CallbackContext) -> None:
    tasks = tasks_collection.find({'status': 'pending'})
    task_count = tasks_collection.count_documents({'status': 'pending'})
    
    if task_count == 0:
        await update.message.reply_text('Нет активных задач.')
    else:
        reply_keyboard = [['/addtask', '/done']]
        markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        for task in tasks:
            await update.message.reply_text(
                f"ID задачи: {task['_id']}\n"
                f"Задача: {task['description']}\n"
                f"Исполнитель: {task['assignee']}\n"
                f"Дедлайн: {task['deadline']}\n"
                f"Напоминание: {task['reminder']}",
                reply_markup=markup
            )

# Команда /done с кнопками
async def mark_done(update: Update, context: CallbackContext) -> None:
    try:
        task_id = context.args[0]
        task_object_id = ObjectId(task_id)
        result = tasks_collection.update_one({'_id': task_object_id}, {'$set': {'status': 'completed'}})
        
        if result.modified_count > 0:
            reply_keyboard = [['/addtask', '/tasks']]
            markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
            await update.message.reply_text(f'Задача с ID "{task_id}" выполнена!', reply_markup=markup)
        else:
            await update.message.reply_text('Задача не найдена.')
    except IndexError:
        await update.message.reply_text('Пожалуйста, укажите ID задачи. Например: /done <ID задачи>')
    except Exception as e:
        await update.message.reply_text(f'Произошла ошибка: {e}')

# Обработчик команды "Отмена"
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Действие отменено.')
    return ConversationHandler.END

# Функция для проверки напоминаний
async def check_reminders(context: CallbackContext):
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz)
    current_time = now.strftime('%H:%M')

    tasks = tasks_collection.find({'reminder': current_time, 'status': 'pending'})
    
    for task in tasks:
        try:
            await context.bot.send_message(
                chat_id=task['chat_id'],
                text=f'Задача: {task["description"]}, Исполнитель: {task["assignee"]}'
            )
        except Exception as e:
            logger.error(f'Ошибка при отправке напоминания: {e}')

# Обработка ошибок
async def error(update: Update, context: CallbackContext) -> None:
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция
def main() -> None:
    application = Application.builder().token(tkn).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tasks", list_tasks))
    application.add_handler(CommandHandler("done", mark_done))

    # ConversationHandler для добавления задачи
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('addtask', add_task)],
        states={
            TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_description)],
            ASSIGNEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, assignee)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, deadline)],
            REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    # Обработка ошибок
    application.add_error_handler(error)

    # Запуск фоновой задачи для проверки напоминаний
    application.job_queue.run_repeating(check_reminders, interval=60.0, first=10.0)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()