import logging
from telegram import Update
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
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
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

# Инициализация планировщика
scheduler = BackgroundScheduler()
scheduler.start()

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Привет! Я бот для планирования семейных задач. Используй /addtask чтобы добавить задачу.')

# Команда /addtask
async def add_task(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Введите описание задачи:')
    return TASK_DESCRIPTION

# Получение описания задачи
async def task_description(update: Update, context: CallbackContext) -> int:
    context.user_data['task_description'] = update.message.text
    await update.message.reply_text('Введите имя исполнителя:')
    return ASSIGNEE

# Получение имени исполнителя
async def assignee(update: Update, context: CallbackContext) -> int:
    context.user_data['assignee'] = update.message.text
    await update.message.reply_text('Укажите дедлайн в формате ДД:ММ:ГГГГ:')
    return DEADLINE

# Получение дедлайна
async def deadline(update: Update, context: CallbackContext) -> int:
    deadline_text = update.message.text
    try:
        # Проверяем, что дедлайн введен в правильном формате
        deadline_date = datetime.strptime(deadline_text, '%d:%m:%Y')
        context.user_data['deadline'] = deadline_date.strftime('%d:%m:%Y')  # Сохраняем в формате строки
        await update.message.reply_text('Введите время напоминания (в формате ЧЧ:ММ, 24-часовой формат):')
        return REMINDER
    except ValueError:
        await update.message.reply_text('Неправильный формат дедлайна. Пожалуйста, укажите дедлайн в формате ДД:ММ:ГГГГ.')
        return DEADLINE

# Функция для отправки напоминания
async def send_reminder(context: CallbackContext):
    job = context.job
    chat_id = job.kwargs.get('chat_id')  # Получаем chat_id из job.kwargs
    await context.bot.send_message(chat_id=chat_id, text=f'Напоминание: {job.name}')

# Функция для планирования напоминания
def schedule_reminder(task_id: str, task_description: str, reminder_time: str, chat_id: int, context: CallbackContext):
    try:
        # Парсим время напоминания
        reminder_hour, reminder_minute = map(int, reminder_time.split(':'))
        
        # Получаем текущую дату и время по Москве
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        # Создаем объект datetime для напоминания
        reminder_datetime = now.replace(hour=reminder_hour, minute=reminder_minute, second=0, microsecond=0)
        
        # Если время напоминания уже прошло сегодня, планируем на следующий день
        if reminder_datetime < now:
            reminder_datetime += timedelta(days=1)
        
        # Планируем напоминание
        scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(reminder_datetime),
            args=[context],
            id=task_id,
            name=task_description,
            replace_existing=True,
            kwargs={'chat_id': chat_id}  # Передаем chat_id через kwargs
        )
    except Exception as e:
        logger.error(f'Ошибка при планировании напоминания: {e}')

# Получение времени напоминания и сохранение задачи
async def reminder(update: Update, context: CallbackContext) -> int:
    reminder_time = update.message.text
    try:
        # Парсим время напоминания
        reminder_hour, reminder_minute = map(int, reminder_time.split(':'))
        
        # Проверяем, что время введено корректно (24-часовой формат)
        if not (0 <= reminder_hour < 24 and 0 <= reminder_minute < 60):
            raise ValueError("Неправильное время. Используйте 24-часовой формат (ЧЧ:ММ).")
        
        # Сохранение задачи в MongoDB
        task = {
            'description': context.user_data['task_description'],
            'assignee': context.user_data['assignee'],
            'deadline': context.user_data['deadline'],
            'reminder': reminder_time,
            'status': 'pending'
        }
        result = tasks_collection.insert_one(task)
        task_id = str(result.inserted_id)  # Получаем _id задачи

        # Планируем напоминание
        schedule_reminder(task_id, context.user_data['task_description'], reminder_time, update.message.chat_id, context)

        await update.message.reply_text(f'Задача успешно добавлена! ID задачи: {task_id}')
        return ConversationHandler.END
    except ValueError as e:
        await update.message.reply_text(f'Ошибка: {e} Пожалуйста, укажите время в формате ЧЧ:ММ (24-часовой формат).')
        return REMINDER
    except Exception as e:
        await update.message.reply_text(f'Произошла ошибка: {e}')
        return REMINDER

# Команда /tasks
async def list_tasks(update: Update, context: CallbackContext) -> None:
    tasks = tasks_collection.find({'status': 'pending'})
    task_count = tasks_collection.count_documents({'status': 'pending'})  # Используем count_documents вместо count
    
    if task_count == 0:
        await update.message.reply_text('Нет активных задач.')
    else:
        for task in tasks:
            await update.message.reply_text(
                f"ID задачи: {task['_id']}\n"
                f"Задача: {task['description']}\n"
                f"Исполнитель: {task['assignee']}\n"
                f"Дедлайн: {task['deadline']}\n"
                f"Напоминание: {task['reminder']}"
            )


# Команда /done
async def mark_done(update: Update, context: CallbackContext) -> None:
    try:
        task_id = context.args[0]  # Получаем ID задачи из аргументов команды
        
        # Преобразуем строку в ObjectId
        task_object_id = ObjectId(task_id)
        
        # Ищем задачу по _id и обновляем её статус
        result = tasks_collection.update_one({'_id': task_object_id}, {'$set': {'status': 'completed'}})
        
        if result.modified_count > 0:
            # Удаляем запланированное напоминание, если задача выполнена
            scheduler.remove_job(task_id)
            await update.message.reply_text(f'Задача с ID "{task_id}" выполнена!')
        else:
            await update.message.reply_text('Задача не найдена.')
    except IndexError:
        await update.message.reply_text('Пожалуйста, укажите ID задачи. Например: /done <ID задачи>')
    except Exception as e:
        await update.message.reply_text(f'Произошла ошибка: {e}')

# Обработка ошибок
async def error(update: Update, context: CallbackContext) -> None:
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция
def main() -> None:
    # Используем токен из файла tokens.py
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
        fallbacks=[],
    )

    application.add_handler(conv_handler)

    # Обработка ошибок
    application.add_error_handler(error)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()