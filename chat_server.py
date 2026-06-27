"""
Чат-сервер для сайта remont-zagoryanka.ru
Groq AI + уведомления в Telegram + CRM (Google Sheets)
Запуск: python3 chat_server.py
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
SHEETS_URL     = "https://script.google.com/macros/s/AKfycby54oO8wY3rzC7RWv56a_PP14BUxqTkZg6VROJ F26Ec8zYz97iWa9ihypMOH9BTuviF/exec"

SYSTEM_PROMPT = """Ты — консультант компании "Ремонт Загорянка". Отвечай коротко, по делу, только на русском языке.

Компания делает: ремонт под ключ, стены/потолки, ванная, электрика, сантехника, полы, фасад/кровля, дача/веранда, отопление.
Работаем в Загорянке и Щёлковском районе МО. Бесплатный выезд мастера. Телефон: +7 (999) 123-45-67.

ВАЖНО: Ты консультант по ремонту, не собеседник. Если пишут не по теме — вежливо верни к ремонту.

ЦЕЛЬ: собрать имя и телефон клиента для заявки.

Когда у тебя есть имя И телефон клиента — добавь в конец ответа ОТДЕЛЬНОЙ строкой:
[ЗАЯВКА: имя=Иван, телефон=+79991234567, услуга=Ванная]

Правила тега [ЗАЯВКА:]:
- Добавляй ТОЛЬКО если получил реальное имя (не "не скажу", не пустое) И реальный номер телефона (11 цифр)
- Телефон в формате +7XXXXXXXXXX
- Добавляй только ОДИН РАЗ за разговор"""


def is_valid_phone(text):
    digits = re.sub(r'\D', '', text)
    return len(digits) >= 10


def is_valid_name(text):
    t = text.strip()
    if len(t) < 2:
        return False
    if re.search(r'\d', t):
        return False
    fake = ["не скажу", "анон", "аноним", "xxx", "---", "нет"]
    if t.lower() in fake:
        return False
    return True


def send_to_sheets(name, phone, service, comment, source="чат сайта"):
    """Отправляем заявку в Google Таблицу"""
    try:
        data = {
            "name": name,
            "phone": phone,
            "service": service,
            "comment": comment,
            "source": source
        }
        resp = requests.post(SHEETS_URL, json=data, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Sheets error: {e}")
        return False


def send_telegram(name, phone, service, comment, source="чат сайта"):
    """Уведомление в Telegram"""
    text = (
        f"🔔 *Новая заявка!*\n\n"
        f"👤 *Имя:* {name}\n"
        f"📞 *Телефон:* {phone}\n"
        f"🔧 *Услуга:* {service or '—'}\n"
        f"💬 *Комментарий:* {comment or '—'}\n"
        f"📍 *Источник:* {source}"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")


def parse_order_tag(text):
    """Извлекаем данные из тега [ЗАЯВКА: ...]"""
    match = re.search(r'\[ЗАЯВКА:\s*(.+?)\]', text, re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1)
    data = {}
    for part in raw.split(','):
        if '=' in part:
            k, v = part.split('=', 1)
            data[k.strip().lower()] = v.strip()
    name  = data.get('имя', '')
    phone = data.get('телефон', '')
    if is_valid_name(name) and is_valid_phone(phone):
        return {
            "name":    name,
            "phone":   phone,
            "service": data.get('услуга', ''),
        }
    return None


@app.route('/chat', methods=['POST'])
def chat():
    body = request.get_json(force=True)
    messages = body.get('messages', [])

    # Groq API
    groq_resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            "max_tokens": 500,
            "temperature": 0.7
        },
        timeout=30
    )

    ai_text = groq_resp.json()['choices'][0]['message']['content']

    # Проверяем тег заявки
    order = parse_order_tag(ai_text)
    order_created = False

    if order:
        # Отправляем в Telegram и Google Sheets
        send_telegram(
            order['name'], order['phone'], order['service'],
            comment='', source='чат сайта'
        )
        send_to_sheets(
            order['name'], order['phone'], order['service'],
            comment='', source='чат сайта'
        )
        order_created = True

    # Убираем тег из текста который видит клиент
    clean_text = re.sub(r'\[ЗАЯВКА:[^\]]*\]', '', ai_text).strip()

    return jsonify({
        "reply": clean_text,
        "order_created": order_created
    })


@app.route('/form', methods=['POST'])
def form():
    """Эндпоинт для формы заявки внизу сайта"""
    body = request.get_json(force=True)
    name    = body.get('name', '')
    phone   = body.get('phone', '')
    service = body.get('service', '')
    comment = body.get('comment', '')

    if name and phone:
        send_telegram(name, phone, service, comment, source='форма сайта')
        send_to_sheets(name, phone, service, comment, source='форма сайта')

    return jsonify({"status": "ok"})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
