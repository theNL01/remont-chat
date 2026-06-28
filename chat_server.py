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
CORS(app)

GROQ_API_KEY      = "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"
TELEGRAM_TOKEN    = "8824457579:AAHx5V5azuDNW0jasIi9lPufl6HybXPqGHw"
ADMIN_CHAT_ID     = "7661738693"
SHEETS_URL        = "https://script.google.com/macros/s/AKfycby54oO8wY3rzC7RWv56a_PP14BUxqTkZg6VROJF26Ec8zYz97iWa9ihypMOH9BTuviF/exec"
REPLICATE_API_KEY = os.environ.get("REPLICATE_API_KEY", "")

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

@app.route("/visualize", methods=["POST"])
def visualize():
    try:
        data = request.json or {}
        image_b64   = data.get("image")
        style       = data.get("style", "modern")
        room        = data.get("room", "living")
        user_prompt = data.get("user_prompt", "").strip()

        if not image_b64:
            return jsonify({"error": "no image"}), 400

        style_text = STYLE_PROMPTS.get(style, STYLE_PROMPTS["modern"])
        room_text  = ROOM_PROMPTS.get(room, ROOM_PROMPTS["living"])

        prompt = f"A beautifully renovated {room_text}, {style_text}, professional interior photography, high quality, realistic"
        if user_prompt:
            prompt += f". Additional details: {user_prompt}"

        # Запускаем предсказание через Replicate (flux-kontext — редактирование по фото)
        run_resp = requests.post(
            "https://api.replicate.com/v1/models/black-forest-labs/flux-kontext-pro/predictions",
            headers={
                "Authorization": f"Bearer {REPLICATE_API_KEY}",
                "Content-Type": "application/json",
                "Prefer": "wait"
            },
            json={
                "input": {
                    "prompt": prompt,
                    "input_image": f"data:image/jpeg;base64,{image_b64}",
                    "output_format": "jpg",
                    "safety_tolerance": 2
                }
            },
            timeout=120
        )

        result = run_resp.json()
        print(f"Replicate response: {result}", flush=True)

        # Если prefer=wait не сработал — поллим
        if result.get("status") in ("starting", "processing"):
            pred_id = result.get("id")
            for _ in range(30):
                time.sleep(3)
                poll = requests.get(
                    f"https://api.replicate.com/v1/predictions/{pred_id}",
                    headers={"Authorization": f"Bearer {REPLICATE_API_KEY}"}
                ).json()
                if poll.get("status") == "succeeded":
                    result = poll
                    break
                if poll.get("status") == "failed":
                    return jsonify({"error": "generation failed"}), 500

        output = result.get("output")
        if isinstance(output, list):
            output = output[0]

        if not output:
            return jsonify({"error": "no output from model"}), 500

        return jsonify({"image_url": output})

    except Exception as e:
        print(f"Visualize error: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("Чат-сервер запущен")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
