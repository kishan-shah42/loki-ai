from flask import Flask, render_template, request, jsonify
from groq import Groq
import os
import requests
import base64

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

messages = [
    {"role": "system", "content": "You are Loki, a crypto expert assistant. You have access to real live crypto prices through a live data feed. When live data is provided to you in the format [Live Data: ...], you MUST use that exact price in your response. Never use your training data for prices. Always quote the exact price from the live data provided."}
]

TRADE_ANALYSIS_PROMPT = """You are an expert crypto trading analyst. Analyze this chart using the following strategy:

STRATEGY RULES:
1. EMA 9 and EMA 15 - Check if candles are touching and using them as support (uptrend) or resistance (downtrend)
2. Trend + Market Structure - Identify if market is making higher highs/higher lows (uptrend) or lower highs/lower lows (downtrend)
3. Volume - Check if volume confirms the move
4. RSI + Bollinger Bands - Use as secondary confirmation only
5. Angle - Look for minimum 30 degree inclination (uptrend) or declination (downtrend)

PROVIDE YOUR ANALYSIS IN THIS FORMAT:
📊 TRADE REVIEW
━━━━━━━━━━━━━━━
📈 Trend: [Bullish/Bearish/Sideways]
🏗️ Market Structure: [Higher Highs & Higher Lows / Lower Highs & Lower Lows]
📉 EMA 9/15: [Candle touching EMA as support? Yes/No]
📐 Angle: [Meets 30 degree requirement? Yes/No]
📦 Volume: [Confirms move? Yes/No]
🔍 RSI/Bollinger: [Secondary confirmation]

⚡ TRADE SETUP
━━━━━━━━━━━━━━━
Entry Zone: [price level or description]
Stop Loss: [below/above which level]
Take Profit: [target level]
Risk-Reward: [ratio]

🎯 SCORE: [X/10]

✅ RECOMMENDATION: [Take Trade / Wait / Avoid]

💬 REASONING: [2-3 sentences explaining the decision]"""

def get_crypto_price(coin):
    try:
        symbol_map = {
            "bitcoin": "XXBTZUSD",
            "ethereum": "XETHZUSD",
            "solana": "SOLUSD",
            "binancecoin": "BNBUSD",
            "ripple": "XXRPZUSD",
            "dogecoin": "XDGUSD"
        }
        symbol = symbol_map.get(coin)
        if not symbol:
            return None
        url = f"https://api.kraken.com/0/public/Ticker?pair={symbol}"
        response = requests.get(url, timeout=10)
        data = response.json()
        result = data["result"]
        pair_key = list(result.keys())[0]
        price = float(result[pair_key]["c"][0])
        high = float(result[pair_key]["h"][1])
        low = float(result[pair_key]["l"][1])
        return f"{coin.upper()} price: ${price:,.2f} USD | 24h High: ${high:,.2f} | 24h Low: ${low:,.2f}"
    except Exception as e:
        return f"Error: {str(e)}"

def detect_crypto(message):
    coins = {
        "bitcoin": "bitcoin",
        "btc": "bitcoin",
        "ethereum": "ethereum",
        "eth": "ethereum",
        "solana": "solana",
        "sol": "solana",
        "bnb": "binancecoin",
        "xrp": "ripple",
        "dogecoin": "dogecoin",
        "doge": "dogecoin"
    }
    message_lower = message.lower()
    for keyword, coin_id in coins.items():
        if keyword in message_lower:
            return coin_id
    return None

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    global messages
    user_input = request.json.get("message")
    coin = detect_crypto(user_input)
    if coin:
        price_data = get_crypto_price(coin)
        if price_data:
            user_input = f"{user_input}\n\n[Live Data: {price_data}]"
    messages.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages
    )
    reply = response.choices[0].message.content
    messages.append({"role": "assistant", "content": reply})
    if len(messages) > 20:
        messages = [messages[0]] + messages[-19:]
    return jsonify({"reply": reply})

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        image_file = request.files.get("chart")
        if not image_file:
            return jsonify({"reply": "No chart image received."})
        image_data = base64.b64encode(image_file.read()).decode("utf-8")
        mime_type = image_file.mimetype
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            }
                        },
                        {
                            "type": "text",
                            "text": TRADE_ANALYSIS_PROMPT
                        }
                    ]
                }
            ]
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"Analysis failed: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)