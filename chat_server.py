# -*- coding: utf-8 -*-
"""
Чат-сервер для сайта remont-zagoryanka.ru
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re
import os
import sys

os.environ["PYTHONUNBUFFERED"] = "1"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": ["Content-Type"]}})

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID      = os.environ.get("ADMIN_CHAT_ID", "")
SHEETS_URL         = os.environ.get("SHEETS_URL", "")
MODELSLAB_API_KEY  = os.environ.get("MODELSLAB_API_KEY", "")

if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY not set in environment", flush=True)
if not TELEGRAM_TOKEN:
    print("WARNING: TELEGRAM_TOKEN not set in environment", flush=True)
if not SHEETS_URL:
    print("WARNING: SHEETS_URL not set in environment", flush=True)

# === Динамические цены из Google Таблицы ===
import time

PRICES_URL = os.environ.get("PRICES_URL", SHEETS_URL)
PRICES_TTL = 300  # секунд

_prices_cache = {"data": None, "ts": 0}

DEFAULT_PRICES = [
    {"key": "remont_pod_klyuch", "category": "Ремонт под ключ",  "unit": "м²",     "price": 2700},
    {"key": "steny_potolki",     "category": "Стены и потолки",  "unit": "м²",     "price": 350},
    {"key": "vannaya",           "category": "Ванная и санузел", "unit": "услуга", "price": 35000},
    {"key": "elektrika",         "category": "Электрика",        "unit": "точка",  "price": 800},
    {"key": "santehnika",        "category": "Сантехника",       "unit": "точка",  "price": 1000},
    {"key": "poly",              "category": "Полы",             "unit": "м²",     "price": 450},
    {"key": "fasad_krovlya",     "category": "Фасад и кровля",   "unit": "м²",     "price": 600},
    {"key": "dacha",             "category": "Дача и веранда",   "unit": "м²",     "price": 1800},
    {"key": "otoplenie",         "category": "Отопление",        "unit": "точка",  "price": 1200},
]


def get_prices():
    now = time.time()
    if _prices_cache["data"] and now - _prices_cache["ts"] < PRICES_TTL:
        return _prices_cache["data"]
    try:
        if PRICES_URL:
            r = requests.get(PRICES_URL, timeout=10)
            data = r.json()
            if isinstance(data, list) and data:
                _prices_cache["data"] = data
                _prices_cache["ts"] = now
                return data
    except Exception as e:
        print(f"Prices fetch error: {e}", flush=True)
    return _prices_cache["data"] or DEFAULT_PRICES


def _format_price(value):
    return f"{int(value):,}".replace(",", " ")


def build_services_block():
    lines = []
    for p in get_prices():
        lines.append(f"- {p['category']} - от {_format_price(p['price'])} ₽/{p['unit']}")
    return "\n".join(lines)


def build_system_prompt():
    return SYSTEM_PROMPT_TEMPLATE.replace("{{УСЛУГИ_И_ЦЕНЫ}}", build_services_block())

# Модели OpenRouter
OPENROUTER_MODELS = [
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-opus-4-7",
    "openai/gpt-4o-mini",
    "openai/gpt-5.4-mini",
    "google/gemini-flash-1.5",
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]

def call_llm(messages, model="anthropic/claude-sonnet-4-6", max_tokens=500, temperature=0.65):
    """Универсальный вызов LLM - OpenRouter или Groq"""
    if model in GROQ_MODELS:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        )
    else:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://remont-zagoryanka.ru",
                "X-Title": "Remont Zagoryanka"
            },
            json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        )
    result = response.json()
    print(f"LLM call model={model} status={response.status_code}", flush=True)

    # Fallback на Groq если OpenRouter недоступен
    if "choices" not in result:
        error_code = result.get("error", {}).get("code", "")
        print(f"LLM error: {result.get('error', result)}", flush=True)
        if model not in GROQ_MODELS:
            print("Falling back to Groq...", flush=True)
            return call_llm(messages, "llama-3.3-70b-versatile", max_tokens, temperature)
        # Fallback на маленькую модель Groq
        if error_code == "rate_limit_exceeded" and model != "llama-3.1-8b-instant":
            return call_llm(messages, "llama-3.1-8b-instant", max_tokens, temperature)
        return None

    return result["choices"][0]["message"]["content"]

SYSTEM_PROMPT_TEMPLATE = """Ты - консультант компании "Ремонт Загорянка". 

Стиль общения:
- Коротко и по делу - не более 2-3 предложений за раз
- Грамотный русский язык, вежливо и профессионально
- Никакой лишней информации которую не спрашивали
- Не перечисляй преимущества компании без запроса
- Не добавляй рекламные фразы в конце сообщений
- Говори естественно, как живой человек
- НИКОГДА не задавай более одного вопроса в одном сообщении
- НИКОГДА не используй английские слова - только русский язык
- "Стены" а не "walls", "мессенджер" а не "messenger" и т.д.

ПЕРВОЕ СООБЩЕНИЕ: Если это первое сообщение клиента - попроси его представиться. Например: "Здравствуйте! Как вас зовут?" Только после того как клиент назвал имя - отвечай на его вопрос.

ВАЖНО: Ты консультант по ремонту. Если клиент пишет не по теме - вежливо верни к теме ремонта.

О компании:
- Ремонт домов, коттеджей и дач под ключ в Загорянке и Щёлковском районе МО


География работы:
Работаем в Загорянке, Образцово и Щёлково. Если клиент из другого места - уточни адрес и скажи что уточнишь возможность выезда.

Услуги и цены:
{{УСЛУГИ_И_ЦЕНЫ}}

Контакты: +7 (999) 123-45-67, пн-сб 8:00-20:00, Загорянка, Щёлковский р-н МО.

Как вести диалог:
1. Первое сообщение → спроси имя
2. Клиент назвал имя → обратись по имени БЕЗ приветствия, ответь на вопрос и задай ТОЛЬКО ОДИН уточняющий вопрос - что именно нужно сделать. Приветствие только в самом первом сообщении.
3. Клиент рассказал детали → спроси как удобнее связаться, варианты перечисляй на отдельных строках:
   "Как вам удобнее с нами связаться?\n- Позвонить вам;\n- Перезвонить вам;\n- Написать в мессенджер (WhatsApp/Telegram/Макс);\n- Написать на email?"
4. В зависимости от выбора спроси только нужное:
   - Позвонить / Перезвонить → спроси номер телефона коротко, например: "Даша, продиктуйте ваш номер - перезвоним в удобное время."
   - Мессенджер → спроси username в этом мессенджере. Если клиент написал только название мессенджера (макс, телеграм, ватсап) - это не username, уточни: "Как вас найти в Максе? Напишите ваш номер телефона или username." Не упоминай фото этапов работ.
   - Email → спроси email адрес
5. Клиент дал контакт → скажи естественно, например: "Спасибо, с вами свяжутся в ближайшее время." или "Хорошо, ждите звонка." - и добавь тег в конце ответа

Как только клиент назвал имя и дал контакт (телефон, username или email) - ОБЯЗАТЕЛЬНО добавь в самый конец ответа тег:
[ЗАЯВКА: имя=ИМЯ, контакт=КОНТАКТ, связь=СПОСОБ_СВЯЗИ, услуга=ВИД_РАБОТ, детали=ДЕТАЛИ_РЕМОНТА]

Способ связи необязателен - если не указан пиши "не указан".
Услуга - вид работ из нашего прайса (например: "Ванная и санузел", "Полы", "Ремонт под ключ"). Детали - площадь, сроки, особенности. Если не рассказал - оставь пустым.
Тег должен быть в самом конце, на отдельной строке.
Не ставь тег если нет имени или контакта. Не придумывай данные."""


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    })


def send_to_sheets(name, contact, service_or_connection, source="чат сайта", is_chat=False, comment_override=None):
    try:
        phone_safe = contact.lstrip("+")
        if comment_override is not None:
            comment = comment_override
            service = service_or_connection
        elif is_chat:
            comment = f"Способ связи: {service_or_connection}" if service_or_connection and service_or_connection != "не указан" else ""
            service = ""
        else:
            comment = ""
            service = service_or_connection
        requests.post(SHEETS_URL, json={
            "name": name,
            "phone": phone_safe,
            "service": service,
            "comment": comment,
            "source": source
        }, timeout=10)
    except Exception as e:
        print(f"Sheets error: {e}")


def is_valid_phone(contact):
    digits = re.sub(r'\D', '', contact)
    return len(digits) >= 10


def is_valid_email(contact):
    return bool(re.search(r'@', contact))


def is_valid_contact(contact):
    if not contact:
        return False
    fake = ["макс", "телеграм", "telegram", "whatsapp", "ватсап", "max", "вк", "vk"]
    if contact.lower().strip() in fake:
        return False
    return is_valid_phone(contact) or is_valid_email(contact) or (len(contact) >= 4 and contact.startswith("@"))


def is_valid_name(name):
    if not name or len(name) < 3:
        return False
    fake = ["имя", "name", "телефон", "phone", "клиент", "человек"]
    if name.lower().strip() in fake:
        return False
    if not re.search(r'[а-яёА-ЯЁa-zA-Z]{3,}', name):
        return False
    return True


def format_history(messages):
    lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"👤 {content}")
        elif role == "assistant":
            # Убираем тег если есть
            clean = re.sub(r'\[ЗАЯВКА:.*?\]', '', content).strip()
            if clean:
                lines.append(f"🤖 {clean}")
    return "\n".join(lines)


INTERVIEW_PROMPT = """Ты - AI-консультант по планированию ремонта компании "Ремонт Загорянка".

Веди интервью как живой человек - кратко, естественно, без лишних слов.

СТРОГО ЗАПРЕЩЕНО - за нарушение штраф:
- Любые восклицания и комплименты в начале ответа: "Отлично!", "Замечательно!", "Хорошо!", "Понятно!", "Дом - это прекрасный объект", "Загорянка - отличное место", "115 метров - это просторно" и ВСЁ подобное
- Давать оценку ответу клиента ("хороший старт", "интересный выбор" и т.п.)
- Писать демагогию и общие фразы
- Спрашивать точный адрес
- Задавать больше одного вопроса за раз
- Использовать любые нерусские символы: английские слова, китайские иероглифы, любые другие алфавиты или письменности. Только кириллица, цифры и стандартная пунктуация (точка, запятая, тире, вопросительный и восклицательный знаки).

КАК НАДО отвечать (примеры):
Клиент: "дом" → Бот: "Какая площадь?"
Клиент: "загорянка" → Бот: "Какая площадь дома?"
Клиент: "115" → Бот: "В каком состоянии сейчас - черновая отделка или уже жилое?"
Клиент: "черновой" → Бот: "Какие помещения планируете ремонтировать?"

КАК НЕ НАДО:
Клиент: "дом" → Бот: "Дом - это прекрасный объект! Расскажите где он находится?" ← ЗАПРЕЩЕНО
Клиент: "115" → Бот: "115 метров - это просторно! Теперь давайте..." ← ЗАПРЕЩЕНО

Собери по порядку (в разговоре, не анкетой):
1. Тип объекта (дом, квартира, дача, веранда)
2. Сколько комнат в объекте (для веранды не спрашивай) - ОДИН вопрос
3. Если объект - дом или дача: сколько этажей - ОТДЕЛЬНЫЙ вопрос после ответа на комнаты
4. Какие из комнат планируется отремонтировать
4. Если квартира - спроси есть ли в доме грузовой лифт. Объясни коротко зачем: это нужно чтобы понять как будем выносить мусор после демонтажа и завозить материалы. Если грузового лифта нет - спроси на каком этаже квартира. Для дома, дачи или веранды этот вопрос не задавай.
5. Площадь - объясни что она нужна для расчёта количества материалов и составления сметы. Если клиент не знает площадь всей квартиры/дома - подскажи что её можно найти в квитанции ЖКХ или в документах на квартиру. Если клиент ремонтирует только отдельную комнату и не знает её площадь - объясни как замерить самостоятельно: измерить длину и ширину комнаты в метрах рулеткой и перемножить (например 4м x 3м = 12 кв.м). Если клиент совсем не может указать площадь - предложи бесплатный выезд мастера на замер.
6. Текущее состояние - черновая отделка или жилое (уже есть отделка, мебель)
7. Какие пожелания по ремонту — что хотите изменить или обновить? Пусть клиент расскажет своими словами. Только после его ответа уточни конкретные виды работ если нужно. Не перечисляй список работ сразу.
8. ОБЯЗАТЕЛЬНО попроси фото каждого помещения которое будет ремонтироваться. Объясни клиенту что без фото невозможно понять реальный объём работ: что придётся демонтировать, что вынести, какая планировка, есть ли скрытые проблемы. Без фото не переходи к следующему пункту - мягко но настойчиво напомни если клиент пропускает.
9. Стиль - предложи прислать референсы или фото примеров которые нравятся
10. Бюджет
11. Сроки - если объект квартира, обязательно упомяни что шумные работы в квартирах разрешены только с 9:00 до 19:00 в будни, в выходные действует тихий час. Это влияет на общий срок ремонта.
12. Планировка или замеры - попроси прислать если есть

Принимай фото - одно слово благодарности и следующий вопрос.

Только русский язык.

Когда собрано достаточно (минимум: тип объекта, площадь, виды работ) - подведи итог одним абзацем и добавь тег:
[ПРОЕКТ: object=ТИП_ОБЪЕКТА, area=ПЛОЩАДЬ, condition=СОСТОЯНИЕ, works=ВИДЫ_РАБОТ, style=СТИЛЬ, budget=БЮДЖЕТ, timeline=СРОКИ]

В конце каждого ответа (кроме финального с тегом) добавляй:
[ВАРИАНТЫ: вариант1 | вариант2 | вариант3]

Варианты - 2-5 слов, конкретно под заданный вопрос. ПРОВЕРЯЙ грамматику - никаких опечаток и обрезанных слов ("прислю" → "пришлю позже", "описать" → "опишу словами").

Для вопроса про помещения предлагай варианты под тип объекта:
- квартира: кухня | ванная и санузел | гостиная | спальня | прихожая | вся квартира целиком
- дом: кухня | ванная | гостиная | спальня | весь дом целиком
- дача: комнаты | кухня | веранда | весь домик
- веранда: вся веранда | часть веранды"""


@app.route("/interview", methods=["POST", "OPTIONS"])
def interview():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data = request.json or {}
    messages = data.get("messages", [])
    name = data.get("name", "")
    is_first = data.get("is_first", False)
    model = data.get("model", "anthropic/claude-sonnet-4-6")

    # Whitelist допустимых моделей
    allowed_models = GROQ_MODELS + OPENROUTER_MODELS
    if model not in allowed_models:
        model = "anthropic/claude-sonnet-4-6"

    system = INTERVIEW_PROMPT
    if name:
        system += f"\n\nИмя клиента: {name}. Первое сообщение должно быть EXACTLY: 'Привет, {name}! Я AI-консультант по планированию ремонта.' - затем с новой строки сразу первый вопрос про тип объекта. Ничего лишнего."

    if is_first:
        messages = []

    full_messages = [{"role": "system", "content": system}] + messages

    reply = call_llm(full_messages, model=model, max_tokens=500, temperature=0.65)

    if not reply:
        return jsonify({"reply": "Сервис временно недоступен.", "variants": []})

    # Страховка: убираем китайские, японские, корейские и прочие нерусские символы
    reply = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+', '', reply)

    # Парсим варианты
    variants = []
    if "[ВАРИАНТЫ:" in reply:
        try:
            v_start = reply.index("[ВАРИАНТЫ:")
            v_end = reply.index("]", v_start)
            v_str = reply[v_start+10:v_end].strip()
            variants = [v.strip() for v in v_str.split("|") if v.strip()]
            reply = reply[:v_start].strip()
        except Exception:
            pass

    # Парсим проект
    project = None
    if "[ПРОЕКТ:" in reply:
        try:
            p_start = reply.index("[ПРОЕКТ:")
            p_end = reply.index("]", p_start)
            p_str = reply[p_start+8:p_end].strip()
            project = {}
            for part in p_str.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    project[k.strip()] = v.strip()
            reply = reply[:p_start].strip()
        except Exception:
            pass

    return jsonify({"reply": reply, "variants": variants, "project": project})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])

    full_messages = [{"role": "system", "content": build_system_prompt()}] + messages

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": full_messages,
            "max_tokens": 400,
            "temperature": 0.5
        }
    )

    result = response.json()
    print(f"Groq response status: {response.status_code}", flush=True)
    if "choices" not in result:
        error_code = result.get("error", {}).get("code", "")
        if error_code == "rate_limit_exceeded":
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": full_messages, "max_tokens": 400, "temperature": 0.5}
            )
            result = response.json()
    if "choices" not in result:
        error_msg = result.get("error", {}).get("message", "неизвестная ошибка")
        print(f"Groq error: {error_msg}", flush=True)
        return jsonify({"reply": "Извините, сервис временно недоступен. Позвоните нам: +7 (999) 123-45-67"})
    reply = result["choices"][0]["message"]["content"]

    if "[ЗАЯВКА:" in reply:
        try:
            tag_start = reply.index("[ЗАЯВКА:")
            tag_end = reply.index("]", tag_start)
            tag = reply[tag_start:tag_end+1]

            name = ""
            contact = ""
            connection = ""
            details = ""
            service_chat = ""

            if "имя=" in tag:
                name = tag.split("имя=")[1].split(",")[0].strip()
            if "контакт=" in tag:
                contact = tag.split("контакт=")[1].split(",")[0].strip()
            if "связь=" in tag:
                connection = tag.split("связь=")[1].split(",")[0].split("]")[0].strip()
            if "услуга=" in tag:
                service_chat = tag.split("услуга=")[1].split(",")[0].split("]")[0].strip()
            if "детали=" in tag:
                details = tag.split("детали=")[1].split("]")[0].strip()

            if is_valid_name(name) and is_valid_contact(contact):
                history = format_history(messages)
                conn_line = f"\n💬 *Способ связи:* {connection}" if connection and connection not in ["не указан", ""] else ""
                details_line = f"\n🔧 *Детали:* {details}" if details else ""
                send_telegram(
                    f"🔔 *Новая заявка с сайта!*\n\n"
                    f"👤 *Имя:* {name}\n"
                    f"📞 *Контакт:* {contact}"
                    f"{conn_line}"
                    f"{details_line}\n\n"
                    f"📋 *Переписка:*\n{history}\n\n"
                    f"⏰ Связаться в течение 30 минут!"
                )
                conn_str = f"Способ связи: {connection}" if connection and connection != "не указан" else ""
                comment = f"{conn_str}. {details}".strip(". ") if details else conn_str
                send_to_sheets(name, contact, service_chat, source="чат сайта", is_chat=False, comment_override=comment)

            reply = reply[:tag_start].strip()
        except Exception:
            pass

    return jsonify({"reply": reply})


PLANNER_PROMPT = """Ты - AI-ассистент по ремонту в приложении "Планировщик ремонта Загорянка".

Пользователь уже зарегистрирован - не спрашивай имя и контакты, не предлагай оставить заявку.

Твоя задача - помогать с планированием ремонта:
- Объяснять этапы и очерёдность работ
- Честно рассказывать про материалы, их плюсы и минусы, реальные цены
- Помогать оценить сроки и бюджет без прикрас
- Давать советы по выбору стиля и планировки
- Отвечать на технические вопросы по строительству и отделке

Стиль: честно и по делу, 3-5 предложений. ТОЛЬКО русский язык - никаких английских слов, даже технических терминов. "Стандарт" а не "standard", "эконом" а не "economy", "отопление" а не "heating". Без рекламных фраз.
Если спрашивают про выезд мастера или договор - скажи что это можно оформить на remont-zagoryanka.ru.

ВАЖНО: В конце КАЖДОГО ответа добавляй блок с тремя вариантами следующего вопроса в таком формате:
[ВАРИАНТЫ: вариант1 | вариант2 | вариант3]

Варианты должны быть короткими (3-7 слов), логично продолжать тему разговора и помогать пользователю глубже разобраться в вопросе. Не повторяй уже обсуждённые темы."""


@app.route("/planner-chat", methods=["POST"])
def planner_chat():
    data = request.json or {}
    messages = data.get("messages", [])
    name = data.get("name", "")

    system = PLANNER_PROMPT
    if name:
        system += f"\n\nИмя пользователя: {name}. Обращайся по имени естественно, не в каждом сообщении."

    full_messages = [{"role": "system", "content": system}] + messages

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": full_messages,
            "max_tokens": 400,
            "temperature": 0.6
        }
    )

    result = response.json()
    if "choices" not in result:
        error_code = result.get("error", {}).get("code", "")
        if error_code == "rate_limit_exceeded":
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": full_messages, "max_tokens": 400, "temperature": 0.6}
            )
            result = response.json()
    if "choices" not in result:
        return jsonify({"reply": "Сервис временно недоступен.", "variants": []})
    reply = result["choices"][0]["message"]["content"]

    variants = []
    if "[ВАРИАНТЫ:" in reply:
        try:
            v_start = reply.index("[ВАРИАНТЫ:")
            v_end = reply.index("]", v_start)
            v_str = reply[v_start+10:v_end].strip()
            variants = [v.strip() for v in v_str.split("|") if v.strip()]
            reply = reply[:v_start].strip()
        except Exception:
            pass

    return jsonify({"reply": reply, "variants": variants})


@app.route("/form", methods=["POST"])
def form():
    data = request.json or {}
    name    = data.get("name", "")
    phone   = data.get("phone", "")
    service = data.get("service", "")
    comment = data.get("comment", "")
    if name and phone:
        send_telegram(
            f"🔔 *Новая заявка с сайта (форма)!*\n\n"
            f"👤 *Имя:* {name}\n"
            f"📞 *Телефон:* {phone}\n"
            f"🔧 *Услуга:* {service or '-'}\n"
            f"💬 *Комментарий:* {comment or '-'}"
        )
        send_to_sheets(name, phone, service, source="форма сайта")
    return jsonify({"status": "ok"})


COLOR_PROMPTS = {
    "light":    "light and airy color palette, white and beige tones, bright and open feel",
    "dark":     "dark and moody color palette, deep charcoal and black tones, dramatic atmosphere",
    "warm":     "warm color palette, honey, terracotta and amber tones, cozy and inviting",
    "cool":     "cool color palette, light blue, grey and white tones, calm and serene",
    "natural":  "natural color palette, sage green, earthy and organic tones, biophilic design",
    "contrast": "high contrast black and white palette, bold graphic look, striking and modern",
}

STYLE_PROMPTS = {
    "modern":  "modern minimalist interior design, clean lines, neutral colors, contemporary furniture",
    "scandi":  "scandinavian interior design, light wood, white walls, cozy minimalist nordic style",
    "classic": "classic elegant interior design, traditional furniture, warm tones, decorative moldings",
    "loft":    "loft industrial interior design, exposed brick, metal accents, open space, dark tones",
}

ROOM_PROMPTS = {
    "kitchen": "kitchen",
    "bath":    "bathroom",
    "living":  "living room",
    "bedroom": "bedroom",
    "hall":    "hallway entrance",
    "dacha":   "country house interior",
}

import base64
import time

def send_telegram_generation(before_b64, after_bytes, user_prompt):
    """Отправляем фото до/после в Telegram при каждой генерации"""
    try:
        from datetime import datetime
        import base64 as b64lib
        caption = (
            f"🎨 *Новая AI-визуализация*\n\n"
            f"💬 *Запрос клиента:* {user_prompt or '-'}\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        # Отправляем фото ДО
        before_bytes = b64lib.b64decode(before_b64)
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": ADMIN_CHAT_ID, "caption": "📸 *До ремонта*", "parse_mode": "Markdown"},
            files={"photo": ("before.jpg", before_bytes, "image/jpeg")},
            timeout=15
        )
        # Отправляем фото ПОСЛЕ
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": ADMIN_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": ("after.jpg", after_bytes, "image/jpeg")},
            timeout=15
        )
    except Exception as e:
        print(f"Telegram generation notify error: {e}", flush=True)



@app.route("/visualize", methods=["POST", "OPTIONS"])
def visualize():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    try:
        data = request.json or {}
        image_b64   = data.get("image")
        user_prompt = data.get("user_prompt", "").strip()

        if not image_b64:
            return jsonify({"error": "no image"}), 400

        if not user_prompt:
            user_prompt = "modern interior design, bright and cozy"

        prompt = f"{user_prompt}. Professional interior photography, high quality, photorealistic result."

        negative_prompt = "ugly, blurry, low quality, distorted, deformed, bad anatomy, watermark, text, people, person"

        # Передаём фото напрямую как base64
        # Передаём base64 напрямую
        gen_resp = requests.post(
            "https://modelslab.com/api/v6/interior/make",
            headers={"Content-Type": "application/json"},
            json={
                "key": MODELSLAB_API_KEY,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "init_image": image_b64,
                "base64": True,
                "strength": 0.8,
                "guidance_scale": 10,
                "num_inference_steps": 51,
                "temp": False,
                "seed": 0
            },
            timeout=120
        )
        result = gen_resp.json()
        print(f"ModelsLab room_decorator response: {result}", flush=True)

        # Сохраняем future_links из первого ответа - там CDN URL без .base64
        initial_future_links = result.get("future_links", [])
        if isinstance(initial_future_links, dict):
            initial_future_links = list(initial_future_links.values())

        # Если processing - поллим fetch API
        if result.get("status") == "processing":
            fetch_url = result.get("fetch_result")
            if fetch_url:
                for _ in range(20):
                    time.sleep(4)
                    poll = requests.post(
                        fetch_url,
                        headers={"Content-Type": "application/json"},
                        json={"key": MODELSLAB_API_KEY},
                        timeout=30
                    ).json()
                    print(f"ModelsLab poll: {poll}", flush=True)
                    if poll.get("status") == "success":
                        result = poll
                        break

        # Собираем все ссылки
        all_links = []
        for src in [result.get("output"), result.get("future_links"), result.get("proxy_links"), initial_future_links]:
            if isinstance(src, list):
                all_links.extend(src)
            elif isinstance(src, str):
                all_links.append(src)

        print(f"All links: {all_links}", flush=True)

        for link in all_links:
            if not link or not isinstance(link, str):
                continue
            # Если это .base64 URL - скачиваем и декодируем
            if link.endswith('.base64'):
                try:
                    r = requests.get(link, timeout=30)
                    print(f"Base64 fetch status: {r.status_code}, content length: {len(r.text)}", flush=True)
                    b64_content = r.text.strip()
                    if len(b64_content) > 100:
                        import base64 as b64lib
                        img_bytes = b64lib.b64decode(b64_content)
                        # Отправляем в Telegram асинхронно
                        import threading
                        threading.Thread(
                            target=send_telegram_generation,
                            args=(image_b64, img_bytes, user_prompt),
                            daemon=True
                        ).start()
                        from flask import Response
                        return Response(img_bytes, mimetype='image/jpeg', headers={
                            'Access-Control-Allow-Origin': '*',
                            'Content-Disposition': 'inline'
                        })
                    else:
                        print(f"Base64 content too short: {b64_content}", flush=True)
                except Exception as e:
                    print(f"Failed to fetch base64: {e}", flush=True)
                    continue
            else:
                return jsonify({"image_url": link})

        return jsonify({"error": "no output", "detail": result}), 500

    except Exception as e:
        print(f"Visualize error: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    name   = data.get("name", "")
    email  = data.get("email", "")
    source = data.get("source", "сайт")
    if name and email:
        send_telegram(
            f"🆕 *Новая регистрация!*\n\n"
            f"👤 *Имя:* {name}\n"
            f"📧 *Email:* {email}\n"
            f"📍 *Источник:* {source}"
        )
        try:
            requests.post(SHEETS_URL, json={
                "type": "register",
                "name": name,
                "email": email,
                "source": source
            }, timeout=10)
        except Exception as e:
            print(f"Sheets register error: {e}")
    return jsonify({"status": "ok"})


@app.route("/prices", methods=["GET"])
def prices_endpoint():
    return jsonify(get_prices())


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("Чат-сервер запущен")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
