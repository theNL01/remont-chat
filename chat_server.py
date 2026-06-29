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

GROQ_API_KEY      = "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"
TELEGRAM_TOKEN    = "8824457579:AAHx5V5azuDNW0jasIi9lPufl6HybXPqGHw"
ADMIN_CHAT_ID     = "7661738693"
SHEETS_URL        = "https://script.google.com/macros/s/AKfycby54oO8wY3rzC7RWv56a_PP14BUxqTkZg6VROJF26Ec8zYz97iWa9ihypMOH9BTuviF/exec"
MODELSLAB_API_KEY = os.environ.get("MODELSLAB_API_KEY", "")

SYSTEM_PROMPT = """Ты — консультант компании "Ремонт Загорянка". 

Стиль общения:
- Коротко и по делу — не более 2-3 предложений за раз
- Грамотный русский язык, вежливо и профессионально
- Никакой лишней информации которую не спрашивали
- Не перечисляй преимущества компании без запроса
- Не добавляй рекламные фразы в конце сообщений
- Говори естественно, как живой человек
- НИКОГДА не задавай более одного вопроса в одном сообщении
- НИКОГДА не используй английские слова — только русский язык
- "Стены" а не "walls", "мессенджер" а не "messenger" и т.д.

ПЕРВОЕ СООБЩЕНИЕ: Если это первое сообщение клиента — попроси его представиться. Например: "Здравствуйте! Как вас зовут?" Только после того как клиент назвал имя — отвечай на его вопрос.

ВАЖНО: Ты консультант по ремонту. Если клиент пишет не по теме — вежливо верни к теме ремонта.

О компании:
- Ремонт домов, коттеджей и дач под ключ в Загорянке и Щёлковском районе МО


География работы:
Работаем в Загорянке, Образцово и Щёлково. Если клиент из другого места — уточни адрес и скажи что уточнишь возможность выезда.

Услуги и цены:
- Ремонт под ключ — от 2 700 ₽/м²
- Стены и потолки — от 350 ₽/м²
- Ванная и санузел — от 35 000 ₽
- Электрика — от 800 ₽/точка
- Сантехника — от 1 000 ₽/точка
- Полы — от 450 ₽/м²
- Фасад и кровля — от 600 ₽/м²
- Дача и веранда — от 1 800 ₽/м²
- Отопление — от 1 200 ₽/точка

Контакты: +7 (999) 123-45-67, пн–сб 8:00–20:00, Загорянка, Щёлковский р-н МО.

Как вести диалог:
1. Первое сообщение → спроси имя
2. Клиент назвал имя → обратись по имени БЕЗ приветствия, ответь на вопрос и задай ТОЛЬКО ОДИН уточняющий вопрос — что именно нужно сделать. Приветствие только в самом первом сообщении.
3. Клиент рассказал детали → спроси как удобнее связаться, варианты перечисляй на отдельных строках:
   "Как вам удобнее с нами связаться?\n— Позвонить вам;\n— Перезвонить вам;\n— Написать в мессенджер (WhatsApp/Telegram/Макс);\n— Написать на email?"
4. В зависимости от выбора спроси только нужное:
   - Позвонить / Перезвонить → спроси номер телефона коротко, например: "Даша, продиктуйте ваш номер — перезвоним в удобное время."
   - Мессенджер → спроси username в этом мессенджере. Если клиент написал только название мессенджера (макс, телеграм, ватсап) — это не username, уточни: "Как вас найти в Максе? Напишите ваш номер телефона или username." Не упоминай фото этапов работ.
   - Email → спроси email адрес
5. Клиент дал контакт → скажи естественно, например: "Спасибо, с вами свяжутся в ближайшее время." или "Хорошо, ждите звонка." — и добавь тег в конце ответа

Как только клиент назвал имя и дал контакт (телефон, username или email) — ОБЯЗАТЕЛЬНО добавь в самый конец ответа тег:
[ЗАЯВКА: имя=ИМЯ, контакт=КОНТАКТ, связь=СПОСОБ_СВЯЗИ, услуга=ВИД_РАБОТ, детали=ДЕТАЛИ_РЕМОНТА]

Способ связи необязателен — если не указан пиши "не указан".
Услуга — вид работ из нашего прайса (например: "Ванная и санузел", "Полы", "Ремонт под ключ"). Детали — площадь, сроки, особенности. Если не рассказал — оставь пустым.
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


INTERVIEW_PROMPT = """Ты — AI-консультант по планированию ремонта компании "Ремонт Загорянка".

Веди интервью как живой человек — кратко, естественно, без лишних слов.

СТРОГО ЗАПРЕЩЕНО — за нарушение штраф:
- Любые восклицания и комплименты в начале ответа: "Отлично!", "Замечательно!", "Хорошо!", "Понятно!", "Дом — это прекрасный объект", "Загорянка — отличное место", "115 метров — это просторно" и ВСЁ подобное
- Давать оценку ответу клиента ("хороший старт", "интересный выбор" и т.п.)
- Писать демагогию и общие фразы
- Спрашивать точный адрес
- Задавать больше одного вопроса за раз
- Использовать английские слова

КАК НАДО отвечать (примеры):
Клиент: "дом" → Бот: "Какая площадь?"
Клиент: "загорянка" → Бот: "Какая площадь дома?"
Клиент: "115" → Бот: "В каком состоянии сейчас — черновая отделка, жилое или после сноса?"
Клиент: "черновой" → Бот: "Какие помещения планируете ремонтировать?"

КАК НЕ НАДО:
Клиент: "дом" → Бот: "Дом — это прекрасный объект! Расскажите где он находится?" ← ЗАПРЕЩЕНО
Клиент: "115" → Бот: "115 метров — это просторно! Теперь давайте..." ← ЗАПРЕЩЕНО

Собери по порядку (в разговоре, не анкетой):
1. Тип объекта (дом, квартира, дача, веранда)
2. Если квартира — есть ли грузовой лифт
3. Площадь
4. Текущее состояние
5. Какие помещения и работы нужны
6. ОБЯЗАТЕЛЬНО попроси фото каждого помещения которое будет ремонтироваться. Объясни клиенту что без фото невозможно понять реальный объём работ: что придётся демонтировать, что вынести, какая планировка, есть ли скрытые проблемы. Без фото не переходи к следующему пункту — мягко но настойчиво напомни если клиент пропускает.
7. Стиль — предложи прислать референсы или фото примеров которые нравятся
8. Бюджет
9. Сроки
10. Планировка или замеры — попроси прислать если есть

Принимай фото — одно слово благодарности и следующий вопрос.

Только русский язык.

Когда собрано достаточно (минимум: тип объекта, площадь, виды работ) — подведи итог одним абзацем и добавь тег:
[ПРОЕКТ: object=ТИП_ОБЪЕКТА, area=ПЛОЩАДЬ, condition=СОСТОЯНИЕ, works=ВИДЫ_РАБОТ, style=СТИЛЬ, budget=БЮДЖЕТ, timeline=СРОКИ]

В конце каждого ответа (кроме финального с тегом) добавляй:
[ВАРИАНТЫ: вариант1 | вариант2 | вариант3]

Варианты — 2-5 слов, конкретно под заданный вопрос."""


@app.route("/interview", methods=["POST", "OPTIONS"])
def interview():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data = request.json or {}
    messages = data.get("messages", [])
    name = data.get("name", "")
    is_first = data.get("is_first", False)

    system = INTERVIEW_PROMPT
    if name:
        system += f"\n\nИмя клиента: {name}. В первом сообщении поприветствуй его по имени тепло и представься как AI-консультант по планированию ремонта. Затем сразу начни с первого вопроса."

    if is_first:
        messages = []

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
            "max_tokens": 500,
            "temperature": 0.65
        }
    )

    result = response.json()
    if "choices" not in result:
        return jsonify({"reply": "Сервис временно недоступен.", "variants": []})

    reply = result["choices"][0]["message"]["content"]

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

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

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
    print(f"Groq response: {result}", flush=True)
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


PLANNER_PROMPT = """Ты — AI-ассистент по ремонту в приложении "Планировщик ремонта Загорянка".

Пользователь уже зарегистрирован — не спрашивай имя и контакты, не предлагай оставить заявку.

Твоя задача — помогать с планированием ремонта:
- Объяснять этапы и очерёдность работ
- Честно рассказывать про материалы, их плюсы и минусы, реальные цены
- Помогать оценить сроки и бюджет без прикрас
- Давать советы по выбору стиля и планировки
- Отвечать на технические вопросы по строительству и отделке

Стиль: честно и по делу, 3-5 предложений. ТОЛЬКО русский язык — никаких английских слов, даже технических терминов. "Стандарт" а не "standard", "эконом" а не "economy", "отопление" а не "heating". Без рекламных фраз.
Если спрашивают про выезд мастера или договор — скажи что это можно оформить на remont-zagoryanka.ru.

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
            f"🔧 *Услуга:* {service or '—'}\n"
            f"💬 *Комментарий:* {comment or '—'}"
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
            f"💬 *Запрос клиента:* {user_prompt or '—'}\n"
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

        # Сохраняем future_links из первого ответа — там CDN URL без .base64
        initial_future_links = result.get("future_links", [])
        if isinstance(initial_future_links, dict):
            initial_future_links = list(initial_future_links.values())

        # Если processing — поллим fetch API
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
            # Если это .base64 URL — скачиваем и декодируем
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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("Чат-сервер запущен")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
