from tokens import token as tkn
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
from mongo_config import MONGO_COLLECTION_NAME, MONGO_DB_NAME, MONGO_URI

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Подключение к MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
tasks_collection = db[MONGO_COLLECTION_NAME]

# Состояния для ConversationHandler
TASK_DESCRIPTION, ASSIGNEE, REMINDER = range(3)

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
    await update.message.reply_text('Введите время напоминания (в формате ЧЧ:ММ):')
    return REMINDER

# Получение времени напоминания и сохранение задачи
async def reminder(update: Update, context: CallbackContext) -> int:
    context.user_data['reminder'] = update.message.text

    # Сохранение задачи в MongoDB
    task = {
        'description': context.user_data['task_description'],
        'assignee': context.user_data['assignee'],
        'reminder': context.user_data['reminder'],
        'status': 'pending'
    }
    tasks_collection.insert_one(task)

    await update.message.reply_text('Задача успешно добавлена!')
    return ConversationHandler.END

# Команда /tasks
async def list_tasks(update: Update, context: CallbackContext) -> None:
    tasks = tasks_collection.find({'status': 'pending'})
    if tasks.count() == 0:
        await update.message.reply_text('Нет активных задач.')
    else:
        for task in tasks:
            await update.message.reply_text(f"Задача: {task['description']}\nИсполнитель: {task['assignee']}\nНапоминание: {task['reminder']}")

# Команда /done
async def mark_done(update: Update, context: CallbackContext) -> None:
    task_description = ' '.join(context.args)
    result = tasks_collection.update_one({'description': task_description}, {'$set': {'status': 'completed'}})
    if result.modified_count > 0:
        await update.message.reply_text(f'Задача "{task_description}" выполнена!')
    else:
        await update.message.reply_text('Задача не найдена.')

# Обработка ошибок
async def error(update: Update, context: CallbackContext) -> None:
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция
def main() -> None:
    # Вставь сюда свой токен
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