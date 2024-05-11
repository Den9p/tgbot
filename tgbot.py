import logging
import re
import paramiko
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path
from psycopg2 import OperationalError
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler

#region НЕ ЗАБЫТЬ
#endregion
dotenv_path = Path('.env') #Путь надо будет потом проверить
load_dotenv(dotenv_path=dotenv_path)


token = os.getenv('TOKEN')
rm_host = os.getenv('RM_HOST')
rm_port = os.getenv('RM_PORT')
rm_user = os.getenv('RM_USER')
rm_password = os.getenv('RM_PASSWORD')

db_database = os.getenv('DB_DATABASE')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
#db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')



# Подключаем логирование
logging.basicConfig(
    filename='logfile.txt', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# Функция для подключения по ssh и выполнения команды
def execute_ssh_command(command):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=rm_host, username=rm_user, password=rm_password, port=rm_port)
        stdin, stdout, stderr = ssh_client.exec_command(command)
        output = stdout.read().decode('utf-8')
        ssh_client.close()
        return output
    except Exception as e:
        logger.error(f"An error occurred while executing SSH command: {str(e)}")
        return f"An error occurred: {str(e)}"


# Функция для подключения к базе данных PostgreSQL и выполнения запроса
def execute_postgresql_query(query):
    try:
        conn = psycopg2.connect(
            dbname=db_database,
            user=db_user,
            password=db_password,
            host=rm_host,
            port=db_port
        )
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        conn.close()
        return rows
    except OperationalError as e:
        logger.error(f"An operational error occurred while executing PostgreSQL query: {str(e)}")
        return f"An operational error occurred: {str(e)}"
    except Exception as e:
        logger.error(f"An error occurred while executing PostgreSQL query: {str(e)}")
        return f"An error occurred: {str(e)}"



#region БД

#region Телефоны

# Функция для записи найденных номеров телефонов в базу данных
def savePhoneNumbers(phone_numbers):
    try:
        conn = psycopg2.connect(
            dbname=db_database,
            user=db_user,
            password=db_password,
            host=rm_host,
            port=db_port
        )
        cur = conn.cursor()
        # Создаем таблицу, если она не существует
        cur.execute("""
            CREATE TABLE IF NOT EXISTS phone_numbers (
                id SERIAL PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL
            )
        """)
        # Вставляем найденные номера телефонов в таблицу
        for number in phone_numbers:
            cur.execute("INSERT INTO phone_numbers (phone_number) VALUES (%s)", (number,))
        conn.commit()
        conn.close()
        return True, "Номера телефонов успешно записаны в базу данных."
    except Exception as e:
        return False, f"Ошибка при записи номеров телефонов в базу данных: {str(e)}"

def findPhoneNumbersCommand(update: Update, context):
    update.message.reply_text('Введите текст для поиска телефонных номеров: ')
    return 'findPhoneNumbers'

def findPhoneNumbers(update: Update, context):
    user_input = update.message.text  # Получаем текст, содержащий(или нет) номера телефонов

    phoneNumRegex = re.compile(r'(8|\+7)[-\s()]*(\d{3})[-\s()]*(\d{3})[-\s]*(\d{2})[-\s]*(\d{2})')

    phoneNumberList = phoneNumRegex.findall(user_input)  # Ищем номера телефонов

    if not phoneNumberList:  # Обрабатываем случай, когда номеров телефонов нет
        update.message.reply_text('Телефонные номера не найдены')
        return ConversationHandler.END

    phoneNumbers = ["".join(phone) for phone in phoneNumberList]  # Создаем список найденных номеров телефонов

    phoneNumbersText = "\n".join(phoneNumbers)  # Создаем текст с найденными номерами телефонов

    # Предлагаем пользователю записать найденные номера телефонов в базу данных
    update.message.reply_text(f"Найденные номера телефонов:\n{phoneNumbersText}\nХотите записать их в базу данных? (Да/Нет)")

    # Сохраняем найденные номера телефонов в контексте пользователя
    context.user_data['phoneNumbers'] = phoneNumbers

    # Переходим в состояние ожидания ответа пользователя
    return 'confirmSavePhoneNumbers'

def confirmSavePhoneNumbers(update: Update, context):
    user_response = update.message.text.lower()  # Получаем ответ пользователя

    if user_response == 'да':
        # Пытаемся записать найденные номера телефонов в базу данных
        success, message = savePhoneNumbers(context.user_data['phoneNumbers'])
        if success:
            update.message.reply_text(message)
        else:
            update.message.reply_text(message)
    elif user_response == 'нет':
        update.message.reply_text('Операция записи в базу данных отменена.')
    else:
        update.message.reply_text('Неверный ответ. Пожалуйста, введите "Да" или "Нет".')

    return ConversationHandler.END

# Вывод номеров телефонов.
# Команда: `/get_phone_numbers`
def getPhoneNumbers(update: Update, context):
    # Проверяем существование таблицы
    check_query = "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'phone_numbers');"
    table_exists = execute_postgresql_query(check_query)

    if table_exists and table_exists[0][0]:
        # Таблица существует, можно выполнить запрос для получения номеров телефонов
        query = "SELECT phone_number FROM phone_numbers;"
        result = execute_postgresql_query(query)
        if isinstance(result, list):
            if result:
                phone_numbers = "\n".join(row[0] for row in result)
                update.message.reply_text(phone_numbers)
            else:
                update.message.reply_text("Номеров телефонов не найдено.")
        else:
            update.message.reply_text("Ошибка при выполнении запроса: {}".format(result))
    else:
        update.message.reply_text("Номеров в таблице нет, воспользуйтесь /findPhoneNumbers")



#endregion

#region Emails
# Функция для записи найденных email-адресов в базу данных
def saveEmailAddresses(email_addresses):
    try:
        conn = psycopg2.connect(
            dbname=db_database,
            user=db_user,
            password=db_password,
            host=rm_host,
            port=db_port
        )
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_addresses (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL
            )
        """)
        # Вставляем найденные email-адреса в таблицу
        for email in email_addresses:
            cur.execute("INSERT INTO email_addresses (email) VALUES (%s)", (email,))
        conn.commit()
        conn.close()
        return True, "Email-адреса успешно записаны в базу данных."
    except Exception as e:
        return False, f"Ошибка при записи email-адресов в базу данных: {str(e)}"


def findEmailsCommand(update: Update, context):
    update.message.reply_text('Введите текст для поиска email-адресов: ')
    return 'findEmails'

def findEmails(update: Update, context):
    user_input = update.message.text  # Получаем текст, содержащий(или нет) email-адреса

    emailRegex = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

    emailList = emailRegex.findall(user_input)  # Ищем email-адреса

    if not emailList:  # Обрабатываем случай, когда email-адресов нет
        update.message.reply_text('Email-адреса не найдены')
        return ConversationHandler.END

    emails = '\n'.join(emailList)  # Создаем строку, в которой перечислены найденные email-адреса

    update.message.reply_text(emails)  # Отправляем сообщение пользователю

    # Предлагаем пользователю записать найденные email-адреса в базу данных
    update.message.reply_text('Хотите записать найденные email-адреса в базу данных? (Да/Нет)')

    # Сохраняем найденные email-адреса в контексте пользователя
    context.user_data['emailAddresses'] = emailList

    # Переходим в состояние ожидания ответа пользователя
    return 'confirmSaveEmails'

def confirmSaveEmails(update: Update, context):
    user_response = update.message.text.lower()  # Получаем ответ пользователя

    if user_response == 'да':
        # Пытаемся записать найденные email-адреса в базу данных
        success, message = saveEmailAddresses(context.user_data['emailAddresses'])
        if success:
            update.message.reply_text(message)
        else:
            update.message.reply_text(message)
    elif user_response == 'нет':
        update.message.reply_text('Операция записи в базу данных отменена.')
    else:
        update.message.reply_text('Неверный ответ. Пожалуйста, введите "Да" или "Нет".')

    return ConversationHandler.END

# Вывод email-адресов.
# Команда: `/get_emails`
def getEmails(update: Update, context):
    # Проверяем существование таблицы
    check_query = "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'email_addresses');"
    table_exists = execute_postgresql_query(check_query)

    if table_exists and table_exists[0][0]:
        # Таблица существует, можно выполнить запрос для получения email-адресов
        query = "SELECT email FROM email_addresses;"
        result = execute_postgresql_query(query)
        if isinstance(result, list):
            if result:
                emails = "\n".join(row[0] for row in result)
                update.message.reply_text(emails)
            else:
                update.message.reply_text("Email-адресов не найдено.")
        else:
            update.message.reply_text("Ошибка при выполнении запроса: {}".format(result))
    else:
        update.message.reply_text("EMAIL'ов нет, воспользуйтесь /findEmails")

#endregion

#Получение логов о репликации PostgreSQL.
# Команда: `/get_repl_logs`
def getReplLogs(update: Update, context):
    try:
        command = "grep 'replication' /var/log/postgresql/postgresql-15-main.log"
        output = execute_ssh_command(command)
        parts = output.split('\n')  # Разбиваем вывод на части по символу новой строки
        # Максимальная длина сообщения в Telegram
        max_message_length = 4096
        # Переменная для хранения текущего сообщения
        current_message = ''
        for part in parts:
            # Проверяем, не превышает ли текущая часть максимальную длину сообщения
            if len(current_message) + len(part) < max_message_length:
                # Если нет, добавляем ее к текущему сообщению
                current_message += part + '\n'
            else:
                # Если превышает, отправляем текущее сообщение и начинаем новое
                update.message.reply_text(current_message)
                current_message = part + '\n'
        # Отправляем последнюю часть
        if current_message:
            update.message.reply_text(current_message)
    except Exception as e:
        logger.error(f"An error occurred in getReplLogs: {str(e)}")
        update.message.reply_text(f"An error occurred: {str(e)}")


#endregion



#region Функции paramiko

def start(update: Update, context):
    user = update.effective_user
    update.message.reply_text(f'Привет {user.full_name}!')


def helpCommand(update: Update, context):
    update.message.reply_text('Help!')


# 3.1.1 О релизе.
# Команда: `/get_release`
def getRelease(update: Update, context):
    data = execute_ssh_command('lsb_release -a')
    update.message.reply_text(data)

# 3.1.2 Об архитектуры процессора, имени хоста системы и версии ядра.
# Команда: `/get_uname`
def getUname(update: Update, context):
    data = execute_ssh_command('uname -a')
    update.message.reply_text(data)

# 3.1.3 О времени работы.
# Команда: `/get_uptime`
def getUptime(update: Update, context):
    data = execute_ssh_command('uptime')
    update.message.reply_text(data)


# 3.2 Сбор информации о состоянии файловой системы.
# Команда: `/get_df`
def getDf(update: Update, context):
    data = execute_ssh_command('df -h')
    update.message.reply_text(data)

# 3.3 Сбор информации о состоянии оперативной памяти.
# Команда: `/get_free`
def getFree(update: Update, context):
    data = execute_ssh_command('free -h')
    update.message.reply_text(data)

# 3.4 Сбор информации о производительности системы.
# Команда: `/get_mpstat`
def getMpstat(update: Update, context):
    data = execute_ssh_command('mpstat')
    update.message.reply_text(data)

# 3.5 Сбор информации о работающих в данной системе пользователях.
# Команда: `/get_w`
def getUsers(update: Update, context):
    data = execute_ssh_command('w')
    update.message.reply_text(data)


# 3.6.1 Последние 10 входов в систему.
# Команда: `/get_auths`
def getLastLogins(update: Update, context):
    data = execute_ssh_command('last -n 10')
    update.message.reply_text(data)

# 3.6.2 Последние 5 критических события.
# Команда: `/get_critical`
def getLastCriticalEvents(update: Update, context):
    data = execute_ssh_command('journalctl -p crit -n 5')
    update.message.reply_text(data)

# 3.7 Сбор информации о запущенных процессах.
# Команда: `/get_ps`
def getPs(update: Update, context):
    data = execute_ssh_command('ps')
    update.message.reply_text(data)

# 3.8 Сбор информации об используемых портах.
# Команда: `/get_ss`
def getSs(update: Update, context):
    command = 'ss'
    output = execute_ssh_command(command)
    # Разбиваем вывод на части по символу новой строки
    parts = output.split('\n')
    # Максимальная длина сообщения в Telegram
    max_message_length = 4096
    # Переменная для хранения текущего сообщения
    current_message = ''
    for part in parts:
        # Проверяем, не превышает ли текущая часть максимальную длину сообщения
        if len(current_message) + len(part) < max_message_length:
            # Если нет, добавляем ее к текущему сообщению
            current_message += part + '\n'
        else:
            # Если превышает, отправляем текущее сообщение и начинаем новое
            update.message.reply_text(current_message)
            current_message = part + '\n'
    # Отправляем последнюю часть
    if current_message:
        update.message.reply_text(current_message)

# 3.9 Сбор информации об установленных пакетах.
# Команда: `/get_apt_list`
def getAptList(update: Update, context):
    # Получаем текст сообщения от пользователя
    user_input = update.message.text.strip()

    # Проверяем, если пользователь ввел команду без аргументов
    if user_input == '/get_apt_list':
        data = execute_ssh_command('apt list')
        parts = data.split('\n')  # Разбиваем вывод на части по символу новой строки
        # Максимальная длина сообщения в Telegram
        max_message_length = 4096
        # Переменная для хранения текущего сообщения
        current_message = ''
        for part in parts:
            # Проверяем, не превышает ли текущая часть максимальную длину сообщения
            if len(current_message) + len(part) < max_message_length:
                # Если нет, добавляем ее к текущему сообщению
                current_message += part + '\n'
            else:
                # Если превышает, отправляем текущее сообщение и начинаем новое
                update.message.reply_text(current_message)
                current_message = part + '\n'
        # Отправляем последнюю часть
        if current_message:
            update.message.reply_text(current_message)
    else:
        # Если пользователь ввел имя пакета, выполняем поиск информации о пакете
        package_name = user_input[len('/get_apt_list') + 1:]  # Извлекаем имя пакета из сообщения
        command = f'apt show {package_name}'
        data = execute_ssh_command(command)
        update.message.reply_text(data)

#3.10 Сбор информации о запущенных сервисах.
#Команда: `/get_services`
def getServices(update: Update, context):
    command = 'service --status-all'
    output = execute_ssh_command(command)
    parts = output.split('\n')  # Разбиваем вывод на части по символу новой строки
    # Максимальная длина сообщения в Telegram
    max_message_length = 4096
    # Переменная для хранения текущего сообщения
    current_message = ''
    for part in parts:
        # Проверяем, не превышает ли текущая часть максимальную длину сообщения
        if len(current_message) + len(part) < max_message_length:
            # Если нет, добавляем ее к текущему сообщению
            current_message += part + '\n'
        else:
            # Если превышает, отправляем текущее сообщение и начинаем новое
            update.message.reply_text(current_message)
            current_message = part + '\n'
    # Отправляем последнюю часть
    if current_message:
        update.message.reply_text(current_message)


    def echo(update: Update, context):
        update.message.reply_text(update.message.text)


def verifyPasswordCommand(update: Update, context):
    update.message.reply_text('Введите пароль для проверки сложности: ')

    return 'verifyPassword'


def verifyPassword(update: Update, context):
    user_input = update.message.text  # Получаем текст, содержащий пароль

    # Пароль должен содержать не менее восьми символов, включая хотя бы одну заглавную букву, одну строчную букву,
    # одну цифру и один специальный символ
    passwordRegex = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$')

    if passwordRegex.match(user_input):
        update.message.reply_text('Пароль сложный.')
    else:
        update.message.reply_text('Пароль простой.')

    return ConversationHandler.END






#endregion





def main():
    updater = Updater(token, use_context=True)

    # Получаем диспетчер для регистрации обработчиков
    dp = updater.dispatcher

    # Обработчик диалога для поиска телефонных номеров
    convHandlerFindPhoneNumbers = ConversationHandler(
        entry_points=[CommandHandler('findPhoneNumbers', findPhoneNumbersCommand)],
        states={
            'findPhoneNumbers': [MessageHandler(Filters.text & ~Filters.command, findPhoneNumbers)],
            'confirmSavePhoneNumbers': [MessageHandler(Filters.text & ~Filters.command, confirmSavePhoneNumbers)],
        },
        fallbacks=[]
    )

    # Обработчик диалога для поиска email-адресов
    convHandlerFindEmails = ConversationHandler(
        entry_points=[CommandHandler('findEmails', findEmailsCommand)],
        states={
            'findEmails': [MessageHandler(Filters.text & ~Filters.command, findEmails)],
            'confirmSaveEmails': [MessageHandler(Filters.text & ~Filters.command, confirmSaveEmails)],
        },
        fallbacks=[]
    )

    # Обработчик диалога для проверки сложности пароля
    convHandlerVerifyPassword = ConversationHandler(
        entry_points=[CommandHandler('verify_password', verifyPasswordCommand)],
        states={
            'verifyPassword': [MessageHandler(Filters.text & ~Filters.command, verifyPassword)],
        },
        fallbacks=[]
    )

    # Регистрируем обработчики команд
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", helpCommand))
    dp.add_handler(convHandlerFindPhoneNumbers)
    dp.add_handler(convHandlerFindEmails)
    dp.add_handler(convHandlerVerifyPassword)
    dp.add_handler(CommandHandler("get_release", getRelease))
    dp.add_handler(CommandHandler("get_uname", getUname))
    dp.add_handler(CommandHandler("get_uptime", getUptime))
    dp.add_handler(CommandHandler("get_df", getDf))
    dp.add_handler(CommandHandler("get_free", getFree))
    dp.add_handler(CommandHandler("get_mpstat", getMpstat))
    dp.add_handler(CommandHandler("get_w", getUsers))
    dp.add_handler(CommandHandler("get_auths", getLastLogins))
    dp.add_handler(CommandHandler("get_critical", getLastCriticalEvents))
    dp.add_handler(CommandHandler("get_ps", getPs))
    dp.add_handler(CommandHandler("get_ss", getSs))
    dp.add_handler(CommandHandler("get_apt_list", getAptList))
    dp.add_handler(CommandHandler("get_services", getServices))
    dp.add_handler(CommandHandler("get_repl_logs", getReplLogs))
    dp.add_handler(CommandHandler("get_emails", getEmails))
    dp.add_handler(CommandHandler("get_phone_numbers", getPhoneNumbers))
    # Регистрируем обработчик текстовых сообщений
    #dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    # Запускаем бота
    updater.start_polling()

    # Останавливаем бота при нажатии Ctrl+C
    updater.idle()


if __name__ == '__main__':
    main()




