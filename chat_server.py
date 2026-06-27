"""
Чат-сервер для сайта remont-zagoryanka.ru
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re
import os

app = Flask(__name__)
CORS(app)

GROQ_API_KEY   = "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"
TELEGRAM_TOKEN = "8824457579:AAHx5V5azuDNW0jasIi9lPufl6HybXPqGHw"
ADMIN_CHAT_ID  = "7661738693"
SHEETS_URL     = "https://script.google.com/macros/s/AKfycby54oO8wY3rzC7RWv56a_PP14BUxqTkZg6VROJF26Ec8zYz97iWa9ihypMOH9BTuviF/exec"

SYSTEM_PROMPT = """Ты — консультант компании "Ремонт Загорянка". 

Стиль общения:
- Коротко и по делу — не более 2-3 предложений за раз
- Грамотный русский язык, вежливо и профессионально
- Никакой лишней информации которую не спрашивали
- Не перечисляй преимущества компании без запроса
- Не добавляй рекламные фразы в конце сообщений
- Говори естественно, как живой человек
- НИКОГДА не используй английские слова — только русский язык
- "Стены" а не "walls", "мессенджер" а не "messenger" и т.д.

ПЕРВОЕ СООБЩЕНИЕ: Если это первое сообщение клиента — попроси его представиться. Например: "Здравствуйте! Как вас зовут?" Только после того как клиент назвал имя — отвечай на его вопрос.

ВАЖНО: Ты консультант по ремонту. Если клиент пишет не по теме — вежливо верни к теме ремонта.

О компании:
- Ремонт домов, коттеджей и дач под ключ в Загорянке и Щёлковском районе МО
- Фото каждого этапа работ в мессенджер

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
2. Клиент назвал имя → поздоровайся по имени, ответь на вопрос
3. Клиент заинтересован → спроси как удобнее связаться:
   "Как вам удобнее с нами связаться?\n📞 Позвонить вам\n📲 Перезвонить вам\n💬 Написать в мессенджер (WhatsApp/Telegram/Макс)\n✉️ Написать на email"
4. В зависимости от выбора спроси только нужное:
   - Позвонить / Перезвонить → спроси номер телефона коротко, например: "Даша, продиктуйте ваш номер — перезвоним в удобное время."
   - Мессенджер → спроси username в этом мессенджере. Если клиент написал только название мессенджера (макс, телеграм, ватсап) — это не username, уточни: "Как вас найти в Максе? Напишите ваш номер телефона или username."
   - Email → спроси email адрес
5. Клиент дал контакт → скажи естественно, например: "Спасибо, с вами свяжутся в ближайшее время." или "Хорошо, ждите звонка." — и добавь тег в конце ответа

Как только клиент назвал имя и дал контакт (телефон, username или email) — ОБЯЗАТЕЛЬНО добавь в самый конец ответа тег:
[ЗАЯВКА: имя=ИМЯ, контакт=КОНТАКТ, связь=СПОСОБ_СВЯЗИ]

Способ связи необязателен — если не указан пиши "не указан".
Тег должен быть в самом конце, на отдельной строке.
Не ставь тег если нет имени или контакта. Не придумывай данные."""


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    })


def send_to_sheets(name, contact, connection, source="чат сайта"):
    try:
        # Убираем + чтобы Google Sheets не воспринимал как формулу
        phone_safe = contact.lstrip("+")
        requests.post(SHEETS_URL, json={
            "name": name,
            "phone": phone_safe,
            "service": "",
            "comment": f"Способ связи: {connection}" if connection and connection != "не указан" else "",
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
    reply = result["choices"][0]["message"]["content"]

    if "[ЗАЯВКА:" in reply:
        try:
            tag_start = reply.index("[ЗАЯВКА:")
            tag_end = reply.index("]", tag_start)
            tag = reply[tag_start:tag_end+1]

            name = ""
            contact = ""
            connection = ""

            if "имя=" in tag:
                name = tag.split("имя=")[1].split(",")[0].strip()
            if "контакт=" in tag:
                contact = tag.split("контакт=")[1].split(",")[0].strip()
            if "связь=" in tag:
                connection = tag.split("связь=")[1].split("]")[0].strip()

            if is_valid_name(name) and is_valid_contact(contact):
                history = format_history(messages)
                conn_line = f"\n💬 *Способ связи:* {connection}" if connection and connection not in ["не указан", ""] else ""
                send_telegram(
                    f"🔔 *Новая заявка с сайта!*\n\n"
                    f"👤 *Имя:* {name}\n"
                    f"📞 *Контакт:* {contact}"
                    f"{conn_line}\n\n"
                    f"📋 *Переписка:*\n{history}\n\n"
                    f"⏰ Связаться в течение 30 минут!"
                )
                send_to_sheets(name, contact, connection, source="чат сайта")

            reply = reply[:tag_start].strip()
        except Exception:
            pass

    return jsonify({"reply": reply})


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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("Чат-сервер запущен")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
