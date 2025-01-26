# bot.py
import logging
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters
from handlers import (
    start, add_task, task_description, assignee, deadline, reminder, list_tasks, mark_done, cancel
)
from database import tasks_collection
from reminders import check_reminders
from config import TOKEN
from states import TASK_DESCRIPTION, ASSIGNEE, DEADLINE, REMINDER  # Импорт констант из states.py

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def start_bot():
    print("Модуль bot.py загружен!")
    print("Функция start_bot вызвана!")

    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

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

# Обработка ошибок
async def error(update, context):
    logger.warning(f'Update {update} caused error {context.error}')