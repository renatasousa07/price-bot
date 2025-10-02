import requests
from bs4 import BeautifulSoup
import time
import os
import sys
from flask import Flask
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ===================== CONFIGURAÇÕES =====================
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

# Variáveis obrigatórias (defina no painel do Render)
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Configuráveis (opcionais via Environment Variables)
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "7000"))     # limite de alerta
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "3600"))    # segundos entre checagens (padrão = 1 hora)
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "7"))     # hora do relatório diário (07)
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")            # timezone para o relatório diário
# =========================================================

def parse_price(price_str):
    try:
        clean_price = price_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(clean_price)
    except (ValueError, AttributeError):
        return None


def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN ou CHAT_ID não configurados — não será enviado Telegram.")
        return
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": CHAT_ID, "text": msg},
            timeout=15
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem Telegram: {e}")


def get_price():
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Tentativa principal (classe que já usamos)
        price = soup.find("span", {"class": "cf-dell-price"})
        if price:
            return price.get_text(strip=True)

        # Fallback: procurar qualquer span contendo "R$"
        all_prices = soup.find_all("span", string=lambda text: text and "R$" in text)
        if all_prices:
            return all_prices[0].get_text(strip=True)

        return None
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar preço: {e}")
        return None


def monitor(interval=3600):
    """Loop principal: checa preço com intervalo definido e envia alertas."""
    print(f"[monitor] iniciando com intervalo {interval} segundos.")
    last_price = None
    while True:
        try:
            price_str = get_price()
            now_utc = datetime.utcnow()
            print(f"[monitor] {now_utc.isoformat()} - preço obtido: {price_str}")

            if price_str:
                price_value = parse_price(price_str)
                # Alerta caso preço esteja abaixo do limite e diferente do último enviado
                if price_value and price_value < PRICE_THRESHOLD:
                    if price_str != last_price:
                        msg = (f"🚨 ALERTA DE PREÇO! Alienware Aurora abaixo de R$ {PRICE_THRESHOLD:,.2f}!\n"
                               f"💻 Preço atual: {price_str}\n🔗 {URL}")
                        send_telegram(msg)
                        last_price = price_str
                # Envia informação inicial uma vez (evita spam)
                elif price_value:
                    if last_price is None:
                        msg = (f"📊 Preço atual do Alienware Aurora: {price_str}\n"
                               f"(Alertas serão enviados apenas se cair abaixo de R$ {PRICE_THRESHOLD:,.2f})")
                        send_telegram(msg)
                    last_price = price_str
            else:
                send_telegram("⚠️ Não consegui encontrar o preço na página!")

        except Exception as e:
            # captura erros inesperados dentro do loop sem parar o bot
            print(f"[monitor] exceção: {e}")

        time.sleep(interval)


def daily_report(hour=7, tz_name="America/Sao_Paulo"):
    """
    Função que aguarda até a próxima ocorrência do horário 'hour' no timezone especificado
    e envia um relatório diário com o preço atual. Executa em loop (uma vez por dia).
    """
    tz = ZoneInfo(tz_name)
    print(f"[daily_report] rodando no timezone {tz_name}, relatório diário às {hour}:00")
    while True:
        try:
            now = datetime.now(tz)
            # define próximo alvo às 'hour':00:00
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target + timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            print(f"[daily_report] próximo relatório em {target.isoformat()} (aguardando {int(wait_seconds)}s)")
            # dormir até o horário alvo
            time.sleep(wait_seconds)

            # Ao acordar, pega o preço e envia
            price_str = get_price()
            when_str = target.strftime("%Y-%m-%d %H:%M")
            if price_str:
                send_telegram(f"☀️ Relatório diário ({when_str} {tz_name}):\n💻 Preço atual: {price_str}\n🔗 {URL}")
            else:
                send_telegram(f"⚠️ Relatório diário ({when_str} {tz_name}): não consegui buscar o preço hoje.")
        except Exception as e:
            print(f"[daily_report] exceção: {e}")
            # espera um minuto antes de tentar novamente, para evitar loop rápido de erros
            time.sleep(60)


# --- Flask para Render (mantém URL pública) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot de monitoramento de preços está rodando no Render!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)


if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("Erro: BOT_TOKEN e CHAT_ID devem estar configurados nas variáveis de ambiente!")
        sys.exit(1)

    send_telegram(f"🤖 Bot de monitoramento iniciado!\n💰 Limite de alerta: R$ {PRICE_THRESHOLD:,.2f}")
    # inicia Flask numa thread separada para expor a URL pública
    threading.Thread(target=run_flask, daemon=True).start()

    # inicia a tarefa diária (07:00 America/Sao_Paulo) em thread separada
    threading.Thread(target=daily_report, args=(int(os.getenv("DAILY_REPORT_HOUR", DAILY_REPORT_HOUR)), TIMEZONE), daemon=True).start()

    # inicia o monitor principal (loop bloqueante)
    monitor(int(os.getenv("MONITOR_INTERVAL", MONITOR_INTERVAL)))
