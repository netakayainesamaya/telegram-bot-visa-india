import json
import os
import logging
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, CallbackQuery, InputFile
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile, ContentType
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from datetime import datetime
from aiogram.fsm.middleware import BaseMiddleware
from aiogram.filters import Command, StateFilter
from dotenv import load_dotenv
from flask import Flask, request
from threading import Thread
import asyncio
import signal
import requests
import sys

load_dotenv()  # Загрузка переменных из файла .env

# Создаем событие для завершения работы Flask-сервера
shutdown_event = asyncio.Event()

app = Flask(__name__)

@app.route('/')
def hello():
    return "Bot is running"

# @app.route('/shutdown', methods=['POST'])
# def shutdown():
#     func = request.environ.get('werkzeug.server.shutdown')
#     if func is None:
#         raise RuntimeError('Not running with the Werkzeug Server')
#     func()
#     return 'Shutting down...'

# Bot token
API_TOKEN = os.getenv('BOT_TOKEN')  # Insert token from @BotFather here

# Group ID for forwarding messages
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID'))  # replace your chat_id

# Logging setup
logging.basicConfig(level=logging.INFO)

# Initializing the bot, router for handling commands, and dispatcher
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
router = Router()
dp = Dispatcher(storage=storage)

# Функция для завершения работы
async def shutdown():
    print("Shutting down...")
    try:
        # Попробуем корректно завершить поллинг
        await dp.stop_polling()
    except RuntimeError as e:
        if str(e) == "Polling is not started":
            print("Polling was already stopped.")
    # Закрытие сессии бота
    await bot.session.close()
    print("Shutdown complete.")

# Defining bot states (numbered according to the steps/questions)
class VisaForm(StatesGroup):
    citizenship_method = State()  # 1. Citizenship method selection
    previous_citizenship = State()  # 2. Previous citizenship
    two_years_question = State()  # 2.2 Question about residing in the country for two years
    current_country = State()  # 3. Current country
    registration_country = State()  # 4. Registration country
    registration_city = State()  # 5. Registration city
    registration_region = State()  # 6. Registration region
    registration_street = State()  # 7. Registration street and house number
    contact_phone = State()  # 8. Contact phone
    father_full_name = State()  # 9. Father's full name
    father_nationality = State()  # 10. Father's nationality
    father_birth_place = State()  # 11. Father's birth place
    mother_full_name = State()  # 12. Mother's full name
    mother_nationality = State()  # 13. Mother's nationality
    mother_birth_place = State()  # 14. Mother's birth place
    marital_status = State()  # 15. Marital status
    spouse_full_name = State()  # 15.3 Spouse's full name
    spouse_nationality = State()  # 15.3 Spouse's nationalit
    spouse_previous_citizenship = State()  # 15.4 Spouse's previous citizenship
    spouse_residence_city = State()  # 15.4 Spouse's residence city
    expected_arrival_date = State()  # 16. Expected arrival date
    expected_arrival_city = State()  # 17. Expected arrival city
    visible_marks = State()  # 18. Visible identification marks
    visible_marks_description = State()  # 18.1 Description of visible identification marks
    education_level = State()  # 19. Education level
    other_education_input = State()  # 19.1 Other education level
    activity_type = State()  # 20. Type of activity
    company_name = State()  # 21. Company name
    job_position = State()  # 22. Job position
    company_address = State()  # 23. Company address
    visited_india = State()  # 24. Visited India
    had_visa = State()  # 25. Had visa to India
    visa_type = State()  # 25.1 Visa type (Electronic or sticker)
    visa_issue_city = State()  # 25.1.1 Visa issue city
    visa_number = State()  # 25.2 Visa number
    visa_issue_date = State()  # 25.3 Visa issue date
    countries_visited = State()  # 26. Countries visited in the last 10 years
    saarc_visited = State()  # 27. SAARC countries visited
    saarc_country_name = State()  # 27.1 SAARC country name
    saarc_visit_year = State()  # 27.2 SAARC country visit year
    contact_person = State()  # 28. Contact person
    photo_upload = State()  # 29. Photo upload
    passport_upload = State()  # 30. Passport upload
    additional_passport = State()  # 31. Additional passport question
    passport_2_upload = State()  # 31.2 Second passport upload
    second_passport_question = State()  # 31.1 Second passport question

# Function to save user data to a JSON file
def save_user_data(user_id, data):
    if os.path.exists('user_data.json'):
        with open('user_data.json', 'r', encoding='utf-8') as file:
            users = json.load(file)
    else:
        users = {}

    users[str(user_id)] = data

    with open('user_data.json', 'w', encoding='utf-8') as file:
        json.dump(users, file, indent=4, ensure_ascii=False)

# Function to get user data from a JSON file
def get_user_data(user_id):
    if os.path.exists('user_data.json'):
        with open('user_data.json', 'r', encoding='utf-8') as file:
            users = json.load(file)
            return users.get(str(user_id), {})
    return {}


# Function for forwarding messages to a group if the user sent a text instead of the desired response
async def forward_message_to_group(user_message: types.Message, expected_answer_type: str):
    forward_text = (f"Ошибка пользователя!\n"
                    f"Ожидалось: {expected_answer_type},\n"
                    f"Получен текст: {user_message.text}\n"
                    f"Пользователь: {user_message.from_user.full_name} ({user_message.from_user.id})")
    
    # Forward the message to the group
    await bot.send_message(GROUP_CHAT_ID, forward_text)

#1. Welcome and button operation

# 1.1 Welcome message and operation of the “Start survey” and “Contact support” buttons
@dp.message(F.text == "/start")
async def start_command(message: types.Message, state: FSMContext):
    # Welcome message
    user_name = message.from_user.first_name
    welcome_text = (f"Добро пожаловать, {user_name} 👋\n"
                    "Я бот 🤖 - \"VisaApplicationBot\" 🇮🇳\n"
                    "Вместе мы сформируем твою заявку на получение визы в Индию 🤝\n"
                    "Начать опрос или связаться с поддержкой можно по кнопкам ниже 👇")
    
    # Buttons "Start survey" and "Contact support"
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать опрос")],
            [KeyboardButton(text="Связаться с поддержкой")]
        ],
        resize_keyboard=True
    )

    await message.answer(welcome_text, reply_markup=markup)
    await state.set_state("main_menu")  # Go to main menu

# 1.2 The user clicks on "Start survey"
@dp.message(F.text == "Начать опрос", StateFilter("main_menu"))
async def start_survey(message: types.Message, state: FSMContext):
    # Hiding the buttons after the survey starts
    await message.answer("Опрос начинается...", reply_markup=ReplyKeyboardRemove())

    # Go to the first survey question
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="По рождению")],
            [KeyboardButton(text="Иное")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите способ, которым Вы получили гражданство:", reply_markup=markup)
    await state.set_state(VisaForm.citizenship_method)  # Set the state of the first question

# 1.3 Handling clicks on the "Contact support" button
@dp.message(F.text == "Связаться с поддержкой", StateFilter("main_menu"))
async def contact_support(message: types.Message):
    # We inform the user of the contact contact
    support_contact = "@netakayia"
    await message.answer(f"Свяжитесь с поддержкой по этому адресу: {support_contact}")

# 1.4 If the user enters text before clicking "Start Survey" or "Contact Support"
@dp.message(StateFilter("main_menu"))
async def handle_message_before_start_survey(message: types.Message):
    # We inform you that the user must click one of the buttons
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать опрос")],
            [KeyboardButton(text="Связаться с поддержкой")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите одну из кнопок: 'Начать опрос' или 'Связаться с поддержкой'.", reply_markup=markup)

# 2. Processing the selected citizenship method
@dp.message(VisaForm.citizenship_method)
async def process_citizenship_method(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    answer = message.text

    # Check if the answer is one of the provided options
    if answer not in ["По рождению", "Иное"]:
        # Forward a message to the group if the user entered text instead of clicking a button
        await forward_message_to_group(message, "Кнопка выбора гражданства")
        
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="По рождению")],
                    [KeyboardButton(text="Иное")]
                ],
                resize_keyboard=True
            )
        )
        return  # Stop execution to allow the user to select the correct option

    # Logic for processing the correct answer
    logging.info(f"Выбранный способ получения гражданства: {answer}")

    user_data = get_user_data(user_id)

    if answer == 'По рождению':
        user_data.pop('previous_citizenship', None)  # Remove previous answers
        user_data.pop('two_years_question', None)
    elif answer == 'Иное':
        user_data.pop('current_country', None)

    user_data['citizenship_method'] = answer
    save_user_data(user_id, user_data)

    # 2.1. Proceed without a message, remove the keyboard
    if answer == 'По рождению':
        await message.answer("Напишите страну, где Вы сейчас находитесь:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(VisaForm.current_country)
    else:
        await message.answer("Укажите предыдущее гражданство:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(VisaForm.previous_citizenship)

# Additional questions if "Other" is selected
@dp.message(VisaForm.previous_citizenship)
async def process_previous_citizenship(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    previous_citizenship = message.text

    user_data = get_user_data(user_id)
    user_data['previous_citizenship'] = previous_citizenship
    save_user_data(user_id, user_data)

    two_years_markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )

    await message.answer("Прожили ли Вы в стране 2 года после получения нового гражданства?", reply_markup=two_years_markup)
    await state.set_state(VisaForm.two_years_question)

# 2.2. Processing the question about living for two years
@dp.message(VisaForm.two_years_question)
async def process_two_years_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    two_years_question = message.text

    # Check if the answer is one of the provided options
    if two_years_question not in ["Да", "Нет"]:
        # Forward a message to the group if the user entered text instead of clicking a button
        await forward_message_to_group(message, "Кнопка ответа на вопрос о проживании 2 года")
        
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Да")],
                    [KeyboardButton(text="Нет")]
                ],
                resize_keyboard=True
            )
        )
        return  # Stop processing if text was entered instead of the correct answer

    # Logic for processing the correct answer
    user_data = get_user_data(user_id)
    user_data['two_years_question'] = two_years_question
    save_user_data(user_id, user_data)

    # Remove buttons and move to the next question
    await message.answer("Напишите страну, где Вы сейчас находитесь:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(VisaForm.current_country)

# 3. Processing the current country of residence
@dp.message(VisaForm.current_country)
async def process_current_country(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    current_country = message.text

    user_data = get_user_data(user_id)
    user_data['current_country'] = current_country
    save_user_data(user_id, user_data)

    # 4. Ask for the registration country
    await message.answer("Теперь укажите вашу страну регистрации (прописки):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(VisaForm.registration_country)

# 5. Request for city/town
@dp.message(VisaForm.registration_country)
async def process_registration_country(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    registration_country = message.text

    user_data = get_user_data(user_id)
    user_data['registration_country'] = registration_country
    save_user_data(user_id, user_data)

    await message.answer("Укажите ваш город или село:")
    await state.set_state(VisaForm.registration_city)

# 6. Request for region/district
@dp.message(VisaForm.registration_city)
async def process_registration_city(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    registration_city = message.text

    user_data = get_user_data(user_id)
    user_data['registration_city'] = registration_city
    save_user_data(user_id, user_data)

    await message.answer("Укажите вашу область или район:")
    await state.set_state(VisaForm.registration_region)

# 7. Request for house number and street
@dp.message(VisaForm.registration_region)
async def process_registration_region(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    registration_region = message.text

    user_data = get_user_data(user_id)
    user_data['registration_region'] = registration_region
    save_user_data(user_id, user_data)

    await message.answer("Укажите номер дома и улицу:")
    await state.set_state(VisaForm.registration_street)

# Processing house number and street
@dp.message(VisaForm.registration_street)
async def process_registration_street(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    registration_street = message.text

    user_data = get_user_data(user_id)
    user_data['registration_street'] = registration_street
    save_user_data(user_id, user_data)

    # 8. Request for contact phone number
    await message.answer("Укажите ваш контактный номер телефона (с кодом страны):")
    await state.set_state(VisaForm.contact_phone)

# 9. Processing contact phone number and questions about family: Father's full name
@dp.message(VisaForm.contact_phone)
async def process_contact_phone(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    contact_phone = message.text

    user_data = get_user_data(user_id)
    user_data['contact_phone'] = contact_phone
    save_user_data(user_id, user_data)

    await message.answer("Укажите полное ФИО вашего отца:")
    await state.set_state(VisaForm.father_full_name)

# 10. Questions about family: Father's nationality
@dp.message(VisaForm.father_full_name)
async def process_father_full_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    father_full_name = message.text

    user_data = get_user_data(user_id)
    user_data['father_full_name'] = father_full_name
    save_user_data(user_id, user_data)

    await message.answer("Укажите национальность вашего отца:")
    await state.set_state(VisaForm.father_nationality)

# 11. Questions about family: Father's birth place
@dp.message(VisaForm.father_nationality)
async def process_father_nationality(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    father_nationality = message.text

    user_data = get_user_data(user_id)
    user_data['father_nationality'] = father_nationality
    save_user_data(user_id, user_data)

    await message.answer("Укажите город или село, где родился ваш отец:")
    await state.set_state(VisaForm.father_birth_place)

# 12. Questions about family: Mother's full name
@dp.message(VisaForm.father_birth_place)
async def process_father_birth_place(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    father_birth_place = message.text

    user_data = get_user_data(user_id)
    user_data['father_birth_place'] = father_birth_place
    save_user_data(user_id, user_data)

    await message.answer("Укажите полное ФИО вашей матери:")
    await state.set_state(VisaForm.mother_full_name)

# 13. Questions about mother: Nationality, Birthplace
@dp.message(VisaForm.mother_full_name)
async def process_mother_full_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    mother_full_name = message.text

    user_data = get_user_data(user_id)
    user_data['mother_full_name'] = mother_full_name
    save_user_data(user_id, user_data)

    await message.answer("Укажите национальность вашей матери:")
    await state.set_state(VisaForm.mother_nationality)

# 14. Questions about mother: Birthplace
@dp.message(VisaForm.mother_nationality)
async def process_mother_nationality(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    mother_nationality = message.text

    user_data = get_user_data(user_id)
    user_data['mother_nationality'] = mother_nationality
    save_user_data(user_id, user_data)

    await message.answer("Укажите город или село, где родилась ваша мать:")
    await state.set_state(VisaForm.mother_birth_place)

@dp.message(VisaForm.mother_birth_place)
async def process_mother_birth_place(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    mother_birth_place = message.text

    user_data = get_user_data(user_id)
    user_data['mother_birth_place'] = mother_birth_place
    save_user_data(user_id, user_data)

    # 15. Question about marital status
    marital_status_markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Женат/Замужем")],
            [KeyboardButton(text="Не женат/Не замужем")]
        ],
        resize_keyboard=True
    )

    await message.answer("Ваше семейное положение:", reply_markup=marital_status_markup)
    await state.set_state(VisaForm.marital_status)

# 15.1. Processing marital status
@dp.message(VisaForm.marital_status)
async def process_marital_status(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    marital_status = message.text

    # Check if the answer is one of the provided options
    if marital_status not in ["Женат/Замужем", "Не женат/Не замужем"]:
        # Forwarding a message to the group
        await forward_message_to_group(message, "Ожидалось нажатие на кнопку (семейное положение)")
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Женат/Замужем")],
                    [KeyboardButton(text="Не женат/Не замужем")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Save and continue
    user_data = get_user_data(user_id)
    user_data['marital_status'] = marital_status
    save_user_data(user_id, user_data)

    # Remove the keyboard after the answer
    await message.answer("Выберите следующий вариант:", reply_markup=ReplyKeyboardRemove())

    # 15.3 Processing the full name of the spouse
    if marital_status == "Женат/Замужем":
        await message.answer("Укажите полное ФИО вашего супруга/супруги:")
        await state.set_state(VisaForm.spouse_full_name)
    else:
        # Move to the question with the calendar for selecting the arrival date if unmarried
        await message.answer("Выберите ожидаемую дату вашего прибытия в Индию:", reply_markup=await SimpleCalendar().start_calendar())
        await state.set_state(VisaForm.expected_arrival_date)
        
# 15.3 Spouse's nationality
@dp.message(VisaForm.spouse_full_name)
async def process_spouse_full_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    spouse_full_name = message.text

    user_data = get_user_data(user_id)
    user_data['spouse_full_name'] = spouse_full_name
    save_user_data(user_id, user_data)

    await message.answer("Укажите национальность вашего супруга/супруги:")
    await state.set_state(VisaForm.spouse_nationality)

# Processing spouse's nationality
@dp.message(VisaForm.spouse_nationality)
async def process_spouse_nationality(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    spouse_nationality = message.text

    user_data = get_user_data(user_id)
    user_data['spouse_nationality'] = spouse_nationality
    save_user_data(user_id, user_data)

    # 15.4 Spouse's previous citizenship question
    previous_citizenship_markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )

    await message.answer("Имеется ли у вашего супруга/супруги предыдущее гражданство?", reply_markup=previous_citizenship_markup)
    await state.set_state(VisaForm.spouse_previous_citizenship)

# Processing the previous citizenship of the spouse
@dp.message(VisaForm.spouse_previous_citizenship)
async def process_spouse_previous_citizenship(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    spouse_previous_citizenship = message.text

    # Check if the answer is one of the provided options
    if spouse_previous_citizenship not in ["Да", "Нет"]:
        await forward_message_to_group(message, "Ожидалось нажатие на кнопку (предыдущее гражданство супруга)")
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Да")],
                    [KeyboardButton(text="Нет")]
                ],
                resize_keyboard=True
            )
        )
        return

    user_data = get_user_data(user_id)
    user_data['spouse_previous_citizenship'] = spouse_previous_citizenship
    save_user_data(user_id, user_data)

    # 15.4 Remove buttons and move to the next question
    await message.answer("Укажите город/село проживания вашего супруга/супруги:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(VisaForm.spouse_residence_city)

# Processing the spouse's city/town of residence
@dp.message(F.text, VisaForm.spouse_residence_city)
async def process_spouse_residence_city(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    spouse_residence_city = message.text

    user_data = get_user_data(user_id)
    user_data['spouse_residence_city'] = spouse_residence_city
    save_user_data(user_id, user_data)

    # 16. Invoke the calendar to select the expected arrival date in India
    await message.answer("Выберите ожидаемую дату вашего прибытия в Индию:", reply_markup=await SimpleCalendar().start_calendar())
    await state.set_state(VisaForm.expected_arrival_date)

# 16. Processing the calendar selection for the expected arrival date
@router.callback_query(SimpleCalendarCallback.filter(), VisaForm.expected_arrival_date)
async def process_arrival_date_calendar(callback_query: CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext):
    # Get the result through process_selection
    selected, selected_date = await SimpleCalendar().process_selection(callback_query, callback_data)

    if selected:
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        user_data['expected_arrival_date'] = selected_date.strftime("%d/%m/%Y")
        save_user_data(user_id, user_data)

        await callback_query.message.answer(f"Вы выбрали {selected_date.strftime('%d/%m/%Y')}.")
        
        # 17. Move to the question about the city of arrival
        await callback_query.message.answer("Укажите ожидаемый город прибытия в Индию:")
        await state.set_state(VisaForm.expected_arrival_city)
        await callback_query.answer()  # We complete the callback

# 16. Ignore text messages when calendar selection is required
@dp.message(VisaForm.expected_arrival_date)
async def ignore_text_input(message: types.Message):
    await forward_message_to_group(message, "Ожидалось использование календаря (дата прибытия)")
    await message.answer("Пожалуйста, выберите дату с помощью календаря.")

# 17. Processing the city of arrival
@router.message(VisaForm.expected_arrival_city)
async def process_expected_arrival_city(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    expected_arrival_city = message.text

    user_data = get_user_data(user_id)
    user_data['expected_arrival_city'] = expected_arrival_city
    save_user_data(user_id, user_data)

    # 18. Move to the question about visible identification marks
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Есть"), KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )

    # 18. Visible identification marks
    await message.answer("Есть ли у Вас видимые опознавательные знаки (шрамы, пирсинг, тату и др.)?", reply_markup=markup)
    await state.set_state(VisaForm.visible_marks)

# 18. Processing the response on visible identification marks
@router.message(VisaForm.visible_marks, F.text.in_({"Есть", "Нет"}))
async def process_visible_marks(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text == "Есть":
        # If "Yes" is selected, request a description and remove the keyboard
        await message.answer("Пожалуйста, укажите, какие видимые опознавательные знаки у Вас есть.", reply_markup=ReplyKeyboardRemove())
        await state.set_state(VisaForm.visible_marks_description)
    else:
        # If "No" is selected, move directly to the education level question
        await ask_education_level(message, state)

# If the user enters text instead of the visible character selection button
@router.message(VisaForm.visible_marks)
async def invalid_visible_marks_input(message: types.Message):
    # Forward message to group
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (видимые опознавательные знаки)")

    # We remind you to select an option from the proposed buttons
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Есть"), KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.", reply_markup=markup)

# Processing descriptions of identification marks
@router.message(VisaForm.visible_marks_description)
async def process_visible_marks_description(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    visible_marks_description = message.text

    user_data = get_user_data(user_id)
    user_data['visible_marks_description'] = visible_marks_description
    save_user_data(user_id, user_data)

    # 19. Moving to the next question about education level
    await ask_education_level(message, state)

# 19. Asking for education level
async def ask_education_level(message: types.Message, state: FSMContext):
    # Keyboard with education level options
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Высшее")],
            [KeyboardButton(text="Второе высшее")],
            [KeyboardButton(text="Без образования")],
            [KeyboardButton(text="Школьное образование")],
            [KeyboardButton(text="Ребёнок")],
            [KeyboardButton(text="Аспирант")],
            [KeyboardButton(text="Другое")]
        ],
        resize_keyboard=True
    )
    await message.answer("Степень образования:", reply_markup=markup)
    await state.set_state(VisaForm.education_level)

# 19. Processing education level with validation that the option is selected from the buttons
@router.message(VisaForm.education_level, F.text.in_({
    "Высшее", "Второе высшее", "Без образования", "Школьное образование", "Ребёнок", "Аспирант", "Другое"
}))
async def process_education_level(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    education_level = message.text

    # Save the education level data
    user_data = get_user_data(user_id)
    user_data['education_level'] = education_level
    save_user_data(user_id, user_data)

    if education_level == "Другое":
        # 19.1 If "Other" is selected, ask for additional input
        await message.answer("Укажите свой вариант:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(VisaForm.other_education_input)
    else:
        # Move to the next question directly
        await ask_activity_type(message, state)

# If the user enters text instead of selecting a button for education level
@router.message(VisaForm.education_level)
async def invalid_education_level_input(message: types.Message):
    # Forward message to group
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (уровень образования)")

    # Remind the user to choose an option from the provided buttons
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Высшее")],
            [KeyboardButton(text="Второе высшее")],
            [KeyboardButton(text="Без образования")],
            [KeyboardButton(text="Школьное образование")],
            [KeyboardButton(text="Ребёнок")],
            [KeyboardButton(text="Аспирант")],
            [KeyboardButton(text="Другое")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.", reply_markup=markup)

# 19.1 Processing text input for "Other" education level
@router.message(VisaForm.other_education_input)
async def process_other_education_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    other_education = message.text

    user_data = get_user_data(user_id)
    user_data['education_level'] = other_education
    save_user_data(user_id, user_data)

    # Move to the next question and remove the keyboard
    await ask_activity_type(message, state)

# 20. Request for the main type of activity
async def ask_activity_type(message: types.Message, state: FSMContext):
    await message.answer("Какой у Вас вид основной деятельности? (например, инженер, врач и т.д.)", reply_markup=ReplyKeyboardRemove())
    await state.set_state(VisaForm.company_name)

# 21. Processing the company name
@router.message(VisaForm.company_name)
async def process_company_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    company_name = message.text

    user_data = get_user_data(user_id)
    user_data['company_name'] = company_name
    save_user_data(user_id, user_data)

    await message.answer("Пожалуйста, укажите Вашу должность.")
    await state.set_state(VisaForm.job_position)

# 22. Processing the job position
@router.message(VisaForm.job_position)
async def process_job_position(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    job_position = message.text

    user_data = get_user_data(user_id)
    user_data['job_position'] = job_position
    save_user_data(user_id, user_data)

    await message.answer("Пожалуйста, укажите адрес компании или частного предпринимательства.")
    await state.set_state(VisaForm.company_address)

# 23. Processing the company address
@router.message(VisaForm.company_address)
async def process_company_address(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    company_address = message.text

    user_data = get_user_data(user_id)
    user_data['company_address'] = company_address
    save_user_data(user_id, user_data)

    # Move to the next question (24): "Have you ever visited India before?"
    await ask_visited_india(message, state)

# 24. "Have you ever visited India before?"
async def ask_visited_india(message: types.Message, state: FSMContext):
    # Display buttons "Yes" and "No"
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Вы когда-либо посещали Индию ранее?", reply_markup=markup)
    await state.set_state(VisaForm.visited_india)

# Processing the response for question 24
@router.message(VisaForm.visited_india, F.text.in_({"Да", "Нет"}))
async def process_visited_india(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    visited_india = message.text

    # Save the response about visiting India
    user_data = get_user_data(user_id)
    user_data['visited_india'] = visited_india
    save_user_data(user_id, user_data)

    # Move to question 25
    await ask_had_visa(message, state)

# If the user enters text instead of selecting a button for question 24
@router.message(VisaForm.visited_india)
async def invalid_visited_india_input(message: types.Message):
    # Пересылаем сообщение в группу
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (посещали ли Индию)")

    # Remind the user to select a button
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.", reply_markup=markup)

# 25. "Have you ever been issued a visa to India?"
async def ask_had_visa(message: types.Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Была ли у Вас когда-нибудь оформлена виза в Индию?", reply_markup=markup)
    await state.set_state(VisaForm.had_visa)

# Processing the response to question 25
@router.message(VisaForm.had_visa, F.text.in_({"Да", "Нет"}))
async def process_had_visa(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    had_visa = message.text

    # Save the response about the visa
    user_data = get_user_data(user_id)
    user_data['had_visa'] = had_visa
    save_user_data(user_id, user_data)

    # Remove the keyboard after the selection
    await message.answer(f"Вы выбрали: {had_visa}", reply_markup=ReplyKeyboardRemove())

    if had_visa == "Нет":
        # If no visa, move directly to question 26
        await ask_countries_visited(message, state)
    else:
        # If visa was issued, move to additional visa-related questions
        await ask_visa_type(message, state)

# If the user enters text instead of selecting a button for question 25
@router.message(VisaForm.had_visa)
async def invalid_had_visa_input(message: types.Message):
    # Пересылаем сообщение в группу
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (была ли виза в Индию)")
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.", reply_markup=markup)

# 25. Additional visa-related questions

# 25.1. "Electronic visa or sticker?"
async def ask_visa_type(message: types.Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Электронная виза"), KeyboardButton(text="Вклейка в паспорт")]
        ],
        resize_keyboard=True
    )
    await message.answer("У Вас была электронная виза или вклейка в паспорт?", reply_markup=markup)
    await state.set_state(VisaForm.visa_type)

# 25.1 Processing the response to the visa type question
@router.message(VisaForm.visa_type, F.text.in_({"Электронная виза", "Вклейка в паспорт"}))
async def process_visa_type(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    visa_type = message.text

    # Save the response about the visa type
    user_data = get_user_data(user_id)
    user_data['visa_type'] = visa_type
    save_user_data(user_id, user_data)

    # Remove the keyboard after the selection
    await message.answer(f"Вы выбрали: {visa_type}", reply_markup=ReplyKeyboardRemove())

    if visa_type == "Электронная виза":
        # If electronic, move to the next question about the visa number
        await ask_visa_number(message, state)
    else:
        # If sticker visa, ask for the visa issue city
        await ask_visa_issue_city(message, state)

# 25.1. If the user enters text instead of selecting a button for the visa type question
@router.message(VisaForm.visa_type)
async def invalid_visa_type_input(message: types.Message):
    # Forwarding a message to the group
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (тип визы)")

    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Электронная виза"), KeyboardButton(text="Вклейка в паспорт")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.", reply_markup=markup)

# 25.1.1 "Visa issue city" (if "Sticker visa" was selected)
async def ask_visa_issue_city(message: types.Message, state: FSMContext):
    await message.answer("Укажите место выдачи визы:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(VisaForm.visa_issue_city)

# 25.1.1 Processing the response to the visa issue city question
@router.message(VisaForm.visa_issue_city)
async def process_visa_issue_city(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    visa_issue_city = message.text

    # Save the visa issue city
    user_data = get_user_data(user_id)
    user_data['visa_issue_city'] = visa_issue_city
    save_user_data(user_id, user_data)

    # Move to the next question about the visa number
    await ask_visa_number(message, state)

# 25.2 "Please specify the visa number"
async def ask_visa_number(message: types.Message, state: FSMContext):
    await message.answer("Укажите номер визы:")
    await state.set_state(VisaForm.visa_number)

# 25.2 Processing the visa number
@router.message(VisaForm.visa_number)
async def process_visa_number(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    visa_number = message.text

    # Save the visa number
    user_data = get_user_data(user_id)
    user_data['visa_number'] = visa_number
    save_user_data(user_id, user_data)

    # Move to the next question about the visa issue date
    await ask_visa_issue_date(message, state)

# 25.3 "Please specify the visa issue date"
async def ask_visa_issue_date(message: types.Message, state: FSMContext):
    await message.answer("Укажите дату выдачи визы (для электронной укажите дату на штампе в паспорте по прилёту):", 
                         reply_markup=await SimpleCalendar().start_calendar())
    await state.set_state(VisaForm.visa_issue_date)

# 25.3 Processing the selection of a date on the calendar for the visa issue date
@router.callback_query(SimpleCalendarCallback.filter(), VisaForm.visa_issue_date)
async def process_calendar_visa_issue_date(callback_query: CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext):
    selected, selected_date = await SimpleCalendar().process_selection(callback_query, callback_data)
    if selected:
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        user_data['visa_issue_date'] = selected_date.strftime("%d/%m/%Y")
        save_user_data(user_id, user_data)

        # Notify the user that the date has been selected
        await callback_query.message.answer(f"Вы выбрали дату: {selected_date.strftime('%d/%m/%Y')}")
        
        # Move to question 26: "Countries you have visited in the last 10 years"
        await ask_countries_visited(callback_query.message, state)
        await callback_query.answer()

# 25.3 Ignore text messages when a date selection from the calendar is required
@router.message(VisaForm.visa_issue_date)
async def ignore_text_input_visa_issue(message: types.Message):
    # Forwarding a message to the group
    await forward_message_to_group(message, "Ожидалось нажатие на календарь (дата выдачи визы)")

    await message.answer("Пожалуйста, выберите дату с помощью календаря.")

# 26. "Countries you have visited in the last 10 years"
async def ask_countries_visited(message: types.Message, state: FSMContext):
    await message.answer("Страны, которые Вы посетили за последние 10 лет:")
    await state.set_state(VisaForm.countries_visited)

# 26. Processing the response for question 26
@router.message(VisaForm.countries_visited)
async def process_countries_visited(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    countries_visited = message.text

    # Save the list of countries visited
    user_data = get_user_data(user_id)
    user_data['countries_visited'] = countries_visited
    save_user_data(user_id, user_data)

    # Move to question 27 after processing the response
    await ask_saarc_countries(message, state)

# 26. If the user enters text instead of selecting a button for question 26
@router.message(VisaForm.countries_visited)
async def invalid_countries_visited_input(message: types.Message):
    # Forwarding a message to the group
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (посещённые страны)")

    await message.answer("Пожалуйста, выберите один из предложенных вариантов.")

# 27. "Have you ever visited SAARC countries?"
async def ask_saarc_countries(message: types.Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Посещали ли вы когда-либо страны СААРК? Страны СААРК: Индия, Бангладеш, Пакистан, Непал, Шри-Ланка, Мальдивская Республика, Афганистан.", reply_markup=markup)
    await state.set_state(VisaForm.saarc_visited)

# Processing the response to question 27
@router.message(VisaForm.saarc_visited, F.text.in_({"Да", "Нет"}))
async def process_saarc_visited(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    saarc_visited = message.text

    # Save the response about visiting SAARC countries
    user_data = get_user_data(user_id)
    user_data['saarc_visited'] = saarc_visited
    save_user_data(user_id, user_data)

    # Remove the keyboard after the selection
    await message.answer(f"Вы выбрали: {saarc_visited}", reply_markup=ReplyKeyboardRemove())

    if saarc_visited == "Да":
        # If "Yes" is selected, ask additional questions
        await ask_saarc_country_name(message, state)
    else:
        # If "No", move to question 28
        await ask_contact_person(message, state)

# If the user enters text instead of selecting a button for question 27
@router.message(VisaForm.saarc_visited)
async def invalid_saarc_visited_input(message: types.Message):
    # Пересылаем сообщение в группу
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (страны СААРК)")

    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.", reply_markup=markup)

# 27.1. "Name one of the SAARC countries" (if "Yes" was selected)
async def ask_saarc_country_name(message: types.Message, state: FSMContext):
    await message.answer("Название одной из стран СААРК, которые вы посетили:")
    await state.set_state(VisaForm.saarc_country_name)

# 27.1 Processing the name of the SAARC country
@router.message(VisaForm.saarc_country_name)
async def process_saarc_country_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    saarc_country_name = message.text

    user_data = get_user_data(user_id)
    user_data['saarc_country_name'] = saarc_country_name
    save_user_data(user_id, user_data)

    # 27.2 Move to the next question about the year of visit
    await ask_saarc_visit_year(message, state)

# 27.2 Function to generate a keyboard with years
def generate_year_keyboard():
    current_year = datetime.datetime.now().year  # Current year
    start_year = current_year - 20  # Show years starting from 20 years ago

    # List of buttons with years
    keyboard = []
    for year in range(start_year, current_year + 1):
        keyboard.append([InlineKeyboardButton(text=str(year), callback_data=f"year:{year}")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# 27.2 "Year of visit" (only the year)
async def ask_saarc_visit_year(message: types.Message, state: FSMContext):
    # Showing a custom keyboard for selecting the year
    await message.answer("Укажите год посещения:", reply_markup=generate_year_keyboard())
    await state.set_state(VisaForm.saarc_visit_year)

# 27.2 Processing the selection of the year
@router.callback_query(lambda call: call.data.startswith("year:"), VisaForm.saarc_visit_year)
async def process_saarc_visit_year(callback_query: CallbackQuery, state: FSMContext):
    # Extract the selected year from callback_data
    selected_year = int(callback_query.data.split(":")[1])

    user_id = callback_query.from_user.id
    user_data = get_user_data(user_id)
    user_data['saarc_visit_year'] = selected_year
    save_user_data(user_id, user_data)

    # Notify the user about the selected year and remove the keyboard
    await callback_query.message.answer(f"Вы выбрали год: {selected_year}", reply_markup=ReplyKeyboardRemove())
    
    # Move to the next question 28 (e.g., contact person)
    await ask_contact_person(callback_query.message, state)
    await callback_query.answer()  # Завершаем callback

# If the user tries to enter text, ignore the response and ask to select a year
@router.message(VisaForm.saarc_visit_year)
async def invalid_year_input(message: types.Message):
    # We forward the message to the group, since it was expected that the year would be selected via buttons
    await forward_message_to_group(message, "Ожидалось нажатие на год посещения СААРК")

    # Remind the user to select one of the proposed years
    await message.answer("Пожалуйста, выберите один из предложенных годов, нажав на кнопку.")

# 28. "Contact person (any phone number in your country)"
async def ask_contact_person(message: types.Message, state: FSMContext):
    await message.answer("Контактное лицо (любой номер телефона в Вашей стране):")
    await state.set_state(VisaForm.contact_person)

# 28. Processing the contact person
@router.message(VisaForm.contact_person)
async def process_contact_person(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    contact_person = message.text

    user_data = get_user_data(user_id)
    user_data['contact_person'] = contact_person
    save_user_data(user_id, user_data)

    # 29. Move to the photo question
    await ask_photo(message, state)

# 29. "Please send your photo"
async def ask_photo(message: types.Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Образец фото")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, отправьте фото на белом или светлом фоне. Вы можете посмотреть образец фото, нажав на кнопку ниже.", reply_markup=markup)
    await state.set_state(VisaForm.photo_upload)

# 29.1. Processing the "Sample Photo" button click
@router.message(VisaForm.photo_upload, F.text == "Образец фото")
async def send_sample_photo(message: types.Message):
    # Specify the path to the sample image
    photo_path = 'photo.example.jpg'  # Ensure the file exists at this path

    # Check if the file exists
    if os.path.exists(photo_path):
        # Use FSInputFile to send the photo
        photo = FSInputFile(photo_path)

        # Send the photo in the chat, allowing the user to download it if needed
        await message.answer_photo(photo=photo, caption="Вот образец фото. Вы можете скачать его при необходимости.")
    else:
        await message.answer("Образец фото не найден. Пожалуйста, проверьте путь к файлу.")

# 29.2. Processing the uploaded photo
@router.message(VisaForm.photo_upload, F.content_type.in_({"photo", "document"}))
async def process_uploaded_photo(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Create a folder with the user's ID
    user_dir = f"files/{user_id}"
    os.makedirs(user_dir, exist_ok=True)

    if message.photo:  # If it's a photo
        photo = message.photo[-1]  # Select the largest size photo
        file_id = photo.file_id
        file = await bot.get_file(file_id)
        file_path = f'{user_dir}/photo.jpg'  # Save the photo as 'photo.jpg' in the user's folder
        
        await bot.download_file(file.file_path, file_path)
        await message.answer("Спасибо! Фото успешно загружено.", reply_markup=ReplyKeyboardRemove())
    
    elif message.document and message.document.mime_type.startswith('image/'):  # If it's an image document
        document = message.document
        file_id = document.file_id
        file = await bot.get_file(file_id)
        file_path = f'{user_dir}/photo.jpg'  # Save the document as 'photo.jpg' in the user's folder
        
        await bot.download_file(file.file_path, file_path)
        await message.answer("Спасибо! Фото успешно загружено.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("Пожалуйста, отправьте фото в формате изображения.")

    # 30. Move to the next question
    await ask_passport_photo(message, state)

# 29.2. If the user sends text instead of a photo
@router.message(VisaForm.photo_upload)
async def invalid_photo_upload(message: types.Message):
    # Forwarding the message to the group, as a photo was expected to be sent
    await forward_message_to_group(message, "Ожидалось отправка фото")

    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Образец фото")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, отправьте фото, как файл. Нажмите на кнопку, чтобы посмотреть образец.", reply_markup=markup)

# 30. "Please send a scanned copy of your passport in PDF format, or a high-quality photo."
async def ask_passport_photo(message: types.Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Образец паспорта")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пришлите отсканированную копию Вашего паспорта в pdf формате, либо фото в хорошем качестве. Образец можно просмотреть ниже:", reply_markup=markup)
    await state.set_state(VisaForm.passport_upload)

# 30.1. Processing the "Sample Passport" button click
@router.message(VisaForm.passport_upload, F.text == "Образец паспорта")
async def send_passport_sample(message: types.Message):
    # Specify the path to the passport sample image
    sample_path = 'passport.example.jpg'  # Ensure the file exists at this path

    if os.path.exists(sample_path):
        photo = FSInputFile(sample_path)
        await message.answer_photo(photo=photo, caption="Вот образец паспорта.")
    else:
        await message.answer("Образец паспорта не найден. Пожалуйста, проверьте путь к файлу.")

# 30.2. Processing the uploaded passport
@router.message(VisaForm.passport_upload, F.document | F.photo)  # Use filter for photos and documents
async def process_uploaded_passport(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Create a folder with the user's ID
    user_dir = f"files/{user_id}"
    os.makedirs(user_dir, exist_ok=True)

    if message.document and message.document.mime_type == 'application/pdf':  # If a PDF is sent
        document = message.document
        file_id = document.file_id
        file = await bot.get_file(file_id)
        file_path = f'{user_dir}/passport.pdf'  # Save the document as 'passport.pdf' in the user's folder
        
        await bot.download_file(file.file_path, file_path)
        await message.answer("Спасибо! Паспорт успешно загружен.")
    elif message.photo:  # If a photo is sent
        photo = message.photo[-1]  # Select the largest size photo
        file_id = photo.file_id
        file = await bot.get_file(file_id)
        file_path = f'{user_dir}/passport.jpg'  # Save the photo as 'passport.jpg' in the user's folder
        
        await bot.download_file(file.file_path, file_path)
        await message.answer("Спасибо! Паспорт успешно загружен.")
    else:
        await message.answer("Пожалуйста, отправьте паспорт в формате PDF или фото.")

    # 31. Move to the next question
    await ask_additional_passport_question(message, state)

# 30.2. If the user sends text instead of a passport document or photo
@router.message(VisaForm.passport_upload)
async def invalid_passport_upload(message: types.Message):
    # Пересылаем сообщение в группу, так как ожидалась отправка паспорта
    await forward_message_to_group(message, "Ожидалось отправка паспорта")

    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Образец паспорта")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, отправьте документ или фото паспорта, как файл.", reply_markup=markup)

# 31. "Do you have any other valid passport?"
async def ask_additional_passport_question(message: types.Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Есть ли у Вас еще один действующий паспорт?", reply_markup=markup)
    await state.set_state(VisaForm.additional_passport)

# 31.1 Processing the answer to the question about the second passport
@router.message(VisaForm.additional_passport, F.text.in_({"Да", "Нет"}))
async def process_additional_passport_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    answer = message.text
    
    # Remove the keyboard after the response
    await message.answer(f"Вы выбрали: {answer}", reply_markup=ReplyKeyboardRemove())
    
    if answer == "Нет":
        await message.answer("Спасибо! Ваши данные успешно записаны 🙂", reply_markup=ReplyKeyboardRemove())
        # End the process if the user doesn't have a second passport
        await state.clear()  # Clear the state as data collection is complete
    else:
        # If the answer is "Yes", ask for the upload of the second passport
        await ask_second_passport(message, state)

# 31.1 If the user enters text instead of selecting a button for the second passport
@router.message(VisaForm.additional_passport)
async def invalid_additional_passport_input(message: types.Message):
    # We forward the message to the group because a button click was expected
    await forward_message_to_group(message, "Ожидалось нажатие на кнопку (второй паспорт)")

    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Пожалуйста, выберите один из предложенных вариантов, нажав на кнопку.", reply_markup=markup)

# 31.2 "Please upload a photo of the second passport"
async def ask_second_passport(message: types.Message, state: FSMContext):
    await message.answer("Пожалуйста, отправьте фото или скан копию второго паспорта.")
    await state.set_state(VisaForm.passport_2_upload)

# 31.2 Processing the upload of the second passport
@router.message(VisaForm.passport_2_upload, F.content_type.in_({"photo", "document"}))
async def process_second_passport(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Create a folder with the user's ID if it doesn't exist
    user_dir = f"files/{user_id}"
    os.makedirs(user_dir, exist_ok=True)

    if message.photo:  # If it's a photo
        photo = message.photo[-1]  # Select the largest size photo
        file_id = photo.file_id
        file = await bot.get_file(file_id)
        file_path = f'{user_dir}/passport-2.jpg'  # Save the photo as 'passport-2.jpg' in the user's folder
        
        await bot.download_file(file.file_path, file_path)
        await message.answer("Спасибо! Второй паспорт успешно загружен.")
    
    elif message.document and message.document.mime_type.startswith('image/'):  # If it's an image document
        document = message.document
        file_id = document.file_id
        file = await bot.get_file(file_id)
        file_path = f'{user_dir}/passport-2.jpg'  # Save the document as 'passport-2.jpg' in the user's folder
        
        await bot.download_file(file.file_path, file_path)
        await message.answer("Спасибо! Второй паспорт успешно загружен.")
    else:
        await message.answer("Пожалуйста, отправьте паспорт в формате изображения или документа.")

    # Completion of the process
    await message.answer("Ваши данные успешно записаны 🙂", reply_markup=ReplyKeyboardRemove())
    await state.clear()  # Clear the state after completion

# 31.2 If the user sends text instead of the second passport
@router.message(VisaForm.passport_2_upload)
async def invalid_passport_2_upload(message: types.Message):
    # Forwarding the message to the group because a file was expected to be sent
    await forward_message_to_group(message, "Ожидалась отправка второго паспорта")

    await message.answer("Пожалуйста, отправьте фото или скан копию второго паспорта в формате изображения или документа.")

# Flask-приложение для Render
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)

@app.route('/shutdown_flask', methods=['POST'])
def shutdown_flask():
    print("Flask server shutting down...")
    # Не вызываем shutdown через werkzeug
    return 'Flask server shutting down...'

# Асинхронная функция для старта бота
async def main():
    dp.include_router(router)  # Используем твою структуру
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown()  # Корректное завершение работы

# Функция для запуска бота и сервера
def run():
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True  # Указываем, что это демон-поток
    flask_thread.start()

    loop = asyncio.get_event_loop()
    task = loop.create_task(main())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, shutting down...")
        task.cancel()  # Отменить задачу поллинга
        loop.run_until_complete(shutdown())  # Запуск shutdown
        print("Shutdown complete.")
        # Явно завершаем программу
        sys.exit(0)

if __name__ == '__main__':
    run()