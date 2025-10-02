import requests
from bs4 import BeautifulSoup
import time
import os
import sys
from flask import Flask
import threading

URL = "https://www.dell.com/pt-br/shop/cty/pdp/spd/alienware-aurora-ac16250-gaming-laptop/brpac16250ubtohsrf_x#customization-anchor"
HEADERS = {
    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept":
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "7000"))


def parse_price(price_str):
    try:
        clean_price = price_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(clean_price)
    except (ValueError, AttributeError):
        return None


def send_telegram(msg):
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={
                "chat_id": CHAT_ID,
                "text": msg
            },
            timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem Telegram: {e}")


def get_price():
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        price = soup.find("span", {"class": "cf-dell-price"})
        if price:
            return price.get_text(strip=True)

        all_prices = soup.find_all("span",
                                   string=lambda text: text and "R$" in text)
        if all_prices:
            return all_prices[0].get_text(strip=True)

        return None
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar preço: {e}")
        return None


def monitor(interval=3600):
    last_price = None
    while True:
        price_str = get_price()
        if price_str:
            price_value = parse_price(price_str)
            if price_value and price_value < PRICE_THRESHOLD:
                if price_str != last_price:
                    msg = f"🚨 ALERTA DE PREÇO! Alienware Aurora abaixo de R$ {PRICE_THRESHOLD:,.2f}!\n💻 Preço atual: {price_str}\n🔗 {URL}"
                    send_telegram(msg)
                    last_price = price_str
            elif price_value:
                if last_price is None:
                    msg = f"📊 Preço atual do Alienware Aurora: {price_str}\n(Alertas serão enviados apenas se cair abaixo de R$ {PRICE_THRESHOLD:,.2f})"
                    send_telegram(msg)
                last_price = price_str
        else:
            send_telegram("⚠️ Não consegui encontrar o preço na página!")
        time.sleep(interval)


# --- Flask para Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot de monitoramento de preços está rodando no Render!"

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("Erro: BOT_TOKEN e CHAT_ID devem estar configurados nas variáveis de ambiente!")
        sys.exit(1)

    send_telegram(f"🤖 Bot de monitoramento iniciado!\n💰 Limite de alerta: R$ {PRICE_THRESHOLD:,.2f}")

    # Flask em paralelo
    threading.Thread(target=run).start()

    # Loop de monitoramento
    monitor(3600)  # checa a cada 1 hora
