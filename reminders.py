from datetime import datetime
import pytz
from database import tasks_collection
import logging

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_reminders(context):
    """
    Функция для проверки и отправки напоминаний.
    """
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz)
    current_time = now.strftime('%H:%M')

    # Ищем задачи, у которых время напоминания совпадает с текущим временем
    tasks = tasks_collection.find({'reminder': current_time, 'status': 'pending'})
    
    for task in tasks:
        try:
            await context.bot.send_message(
                chat_id=task['chat_id'],
                text=f'Напоминание! Задача: {task["description"]}, Исполнитель: {task["assignee"]}'
            )
        except Exception as e:
            logger.error(f'Ошибка при отправке напоминания: {e}')