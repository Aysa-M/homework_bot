import json
import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}
handler_CP1251 = logging.FileHandler(filename='cp1251.log')
handler_UTF8 = logging.FileHandler(filename='program.log', encoding='utf-8')
logging.basicConfig(
    level=logging.DEBUG,
    handlers=(handler_UTF8, handler_CP1251),
    format=('%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - '
            '%(lineno)s - %(message)s'))

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)
logger.setLevel(logging.INFO)
logger.setLevel(logging.ERROR)
logger.setLevel(logging.CRITICAL)

handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - '
                              '%(funcName)s - %(lineno)s - %(message)s')
handler.setFormatter(formatter)


def send_message(bot, message):
    """.
    Отправляет сообщение в Telegram чат, определяемый переменной окружения
    TELEGRAM_CHAT_ID. Принимает на вход два параметра: экземпляр класса Bot и
    строку с текстом сообщения.
    """
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.info('Отправка сообщения в Telegram прошла удачно.')
    except Exception as error:
        logging.error(f'Ошибка при отправке пользователю: {error}')


def get_api_answer(current_timestamp):
    """.
    Осуществляет запрос к эндпоинту API-сервиса. В качестве параметра
    функция получает временную метку. В случае успешного запроса должна
    вернуть ответ API, преобразовав его из формата JSON к типам данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response_from_api = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=params)
    except Exception as error:
        logging.error(f'Ошибка запроса к API адресу: {error}')
    if response_from_api.status_code != HTTPStatus.OK:
        logging.error(
            f'Ошибка ответа от API адреса: {response_from_api.status_code}'
        )
        raise Exception(
            f'Ошибка ответа от API адреса: {response_from_api.status_code}'
        )
    try:
        response = response_from_api.json()
    except json.JSONDecodeError as error:
        logging.error(
            f'Ответ от API адреса не преобразован в json(): {error}.'
        )
    return response


def check_response(response):
    """.
    Проверяет ответ API на корректность. В качестве параметра функция получает
    ответ API, приведенный к типам данных Python. Если ответ API соответствует
    ожиданиям, то функция должна вернуть список домашних работ
    (он может быть и пустым), доступный в ответе API по ключу 'homeworks'.
    """
    if type(response) is not dict:
        logging.error('Тип данных ответа от API адреса не dict.')
        raise TypeError('Тип данных ответа от API адреса не dict.')
    try:
        homeworks_list = response['homeworks']
    except KeyError:
        logging.error('В ответе API отсутствует ожидаемый ключ "homeworks".')
    try:
        homework = homeworks_list[0]
    except IndexError:
        logging.error('Список работ на проверке пуст.')
    return homework


def parse_status(homework):
    """
    Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха, функция возвращает подготовленную для
    отправки в Telegram строку, содержащую один из вердиктов словаря
    HOMEWORK_STATUSES.
    """
    if 'homework_name' not in homework:
        logging.error('В ответе API отсутствует '
                      'ожидаемый ключ "homework_name".')
        raise KeyError('В ответе API отсутствует '
                       'ожидаемый ключ "homework_name".')
    if 'status' not in homework:
        logging.error('В ответе API отсутствует ожидаемый ключ "status".')
        raise KeyError('В ответе API отсутствует ожидаемый ключ "status".')
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_STATUSES.keys():
        logging.error('Обнаружен недокументированный статус домашней '
                      'работы в ответе API.')
        raise KeyError('Обнаружен недокументированный статус домашней работы '
                       'в ответе API.')
    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """.
    Проверяет доступность переменных окружения, которые необходимы для работы
    программы.
    Если отсутствует хотя бы одна переменная окружения — функция должна
    вернуть False, иначе — True.
    """
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    if all(tokens):
        return True
    else:
        return False


def main():
    """.
    Основная логика работы бота. Все остальные функции должны
    запускаться из неё.
    Последовательность действий должна быть примерно такой:
    Сделать запрос к API.
    Проверить ответ.
    Если есть обновления — получить статус работы из обновления и отправить
    сообщение в Telegram. Подождать некоторое время и сделать новый запрос.
    """
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    previous_status = ''
    initial_error = ''
    tokens_approved = check_tokens()
    if not tokens_approved:
        logger.critical('Обязательная(ые) переменная(ые) окружения .env '
                        'недоступна(ы).')
        raise ValueError('Обязательная(ые) переменная(ые) окружения .env '
                         'недоступна(ы).')
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_date')
            homework = check_response(response)
            message = parse_status(homework)
            if message != previous_status:
                send_message(bot, message)
            time.sleep(RETRY_TIME)
        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logging.error(error_message)
            if error != initial_error:
                send_message(bot, error_message)
            initial_error = error
            time.sleep(RETRY_TIME)
        else:
            response = get_api_answer(current_timestamp)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
