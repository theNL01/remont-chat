"""
Чат-сервер для сайта remont-zagoryanka.ru
Запуск: /opt/python/python-3.8.8/bin/python3 chat_server.py
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)

GROQ_API_KEY    = "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"
TELEGRAM_TOKEN  = "8824457579:AAHx5V5azuDNW0jasIi9lPufl6HybXPqGHw"
ADMIN_CHAT_ID   = "7661738693"

SYSTEM_PROMPT = """Ты — вежливый помощник-консультант компании "Ремонт Загорянка".
Отвечай коротко, по делу, на русском языке.

О компании:
- Ремонт домов, коттеджей и дач под ключ в Загорянке и Щёлковском районе МО
- Работаем официально, договор, гарантия 2 года
- Бесплатный выезд мастера и смета
- Цена фиксируется в договоре и не меняется
- Фото каждого этапа работ в мессенджер
- После ремонта убираем мусор

Услуги и цены:
- Ремонт под ключ — от 2 700 ₽/м²
- Стены и потолки (штукатурка, покраска, обои, гипсокартон) — от 350 ₽/м²
- Ванная и санузел (плитка, сантехника, тёплый пол) — от 35 000 ₽
- Электрика (проводка, щитки, розетки) — от 800 ₽/точка
- Сантехника (трубы, котлы, бойлеры) — от 1 000 ₽/точка
- Полы (стяжка, ламинат, паркет, плитка) — от 450 ₽/м²
- Фасад и кровля — от 600 ₽/м²
- Дача и веранда (террасы, беседки, навесы) — от 1 800 ₽/м²
- Отопление (радиаторы, тёплые полы, котлы) — от 1 200 ₽/точка

Контакты:
- Телефон: +7 (999) 123-45-67
- Работаем пн–сб 8:00–20:00
- Адрес: Загорянка, Щёлковский р-н, Московская область

Как работаем:
1. Заявка → 2. Бесплатный выезд → 3. Договор с фиксированной ценой → 4. Ремонт и сдача по акту

Когда клиент хочет оставить заявку или спрашивает о конкретном ремонте — попроси имя и телефон.
Когда получишь имя и телефон клиента — напиши в конце своего ответа специальный тег:
[ЗАЯВКА: имя=ИМЯ, телефон=ТЕЛЕФОН]

Не придумывай цены и сроки которых нет выше. Если не знаешь — предложи позвонить."""


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    })


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])

    # Добавляем системный промпт
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # Запрос к Groq
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.1-8b-instant",
            "messages": full_messages,
            "max_tokens": 500,
            "temperature": 0.7
        }
    )

    result = response.json()
    reply = result["choices"][0]["message"]["content"]

    # Проверяем есть ли заявка в ответе
    if "[ЗАЯВКА:" in reply:
        try:
            tag_start = reply.index("[ЗАЯВКА:")
            tag_end = reply.index("]", tag_start)
            tag = reply[tag_start:tag_end+1]

            name = ""
            phone = ""
            if "имя=" in tag:
                name = tag.split("имя=")[1].split(",")[0].strip()
            if "телефон=" in tag:
                phone = tag.split("телефон=")[1].split("]")[0].strip()

            send_telegram(
                f"🔔 *Новая заявка с сайта!*\n\n"
                f"👤 *Имя:* {name}\n"
                f"📞 *Телефон:* {phone}\n\n"
                f"⏰ Перезвонить в течение 30 минут!"
            )

            # Убираем тег из ответа клиенту
            reply = reply[:tag_start].strip()
        except Exception:
            pass

    return jsonify({"reply": reply})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("Чат-сервер запущен на порту 5000")
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
