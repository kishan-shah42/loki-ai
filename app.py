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

EMA_PROMPT = """You are an expert crypto trading analyst. Analyze this chart using the 9/15 EMA strategy:

STRATEGY RULES:
1. EMA 9 and EMA 15 - Check if candles are touching and using them as support (uptrend) or resistance (downtrend)
2. Trend + Market Structure - Identify higher highs/higher lows (uptrend) or lower highs/lower lows (downtrend)
3. Volume - Check if volume confirms the move
4. RSI + Bollinger Bands - Use as secondary confirmation only
5. Angle - Look for minimum 30 degree inclination or declination

PROVIDE YOUR ANALYSIS IN THIS FORMAT:
📊 TRADE REVIEW — EMA 9/15 STRATEGY
━━━━━━━━━━━━━━━
📈 Trend: [Bullish/Bearish/Sideways]
🏗️ Market Structure: [Higher Highs & Higher Lows / Lower Highs & Lower Lows]
📉 EMA 9/15: [Candle touching EMA as support/resistance? Yes/No]
📐 Angle: [Meets 30 degree requirement? Yes/No]
📦 Volume: [Confirms move? Yes/No]
🔍 RSI/Bollinger: [Secondary confirmation]

⚡ TRADE SETUP
━━━━━━━━━━━━━━━
Entry Zone: [level]
Stop Loss: [level]
Take Profit: [level]
Risk-Reward: [ratio]

🎯 SCORE: [X/10]
✅ RECOMMENDATION: [Take Trade / Wait / Avoid]
💬 REASONING: [2-3 sentences]"""

SMC_PROMPT = """You are an expert crypto trading analyst specializing in Smart Money Concepts (SMC). Analyze this chart:

STRATEGY RULES:
1. Market Structure - Identify Break of Structure (BOS) and Change of Character (CHOCH)
2. Order Blocks - Identify bullish or bearish order blocks
3. Fair Value Gaps (FVG) - Identify any unfilled gaps
4. Liquidity - Identify liquidity pools above highs or below lows
5. Premium/Discount zones - Is price in premium or discount?

PROVIDE YOUR ANALYSIS IN THIS FORMAT:
📊 TRADE REVIEW — SMC STRATEGY
━━━━━━━━━━━━━━━
📈 Market Structure: [BOS/CHOCH — Bullish or Bearish]
🏦 Order Block: [Identified? Location?]
⚡ Fair Value Gap: [Present? Yes/No — Location]
💧 Liquidity: [Where is liquidity resting?]
📍 Zone: [Premium / Discount / Equilibrium]

⚡ TRADE SETUP
━━━━━━━━━━━━━━━
Entry Zone: [level]
Stop Loss: [level]
Take Profit: [level]
Risk-Reward: [ratio]

🎯 SCORE: [X/10]
✅ RECOMMENDATION: [Take Trade / Wait / Avoid]
💬 REASONING: [2-3 sentences]"""

SR_PROMPT = """You are an expert crypto trading analyst specializing in Support and Resistance trading. Analyze this chart:

STRATEGY RULES:
1. Key Support Levels - Identify strong support zones where price bounced before
2. Key Resistance Levels - Identify strong resistance zones where price rejected before
3. Trend - Overall trend direction
4. Breakout or Rejection - Is price breaking out or rejecting from a key level?
5. Volume - Does volume confirm the move?

PROVIDE YOUR ANALYSIS IN THIS FORMAT:
📊 TRADE REVIEW — SUPPORT & RESISTANCE STRATEGY
━━━━━━━━━━━━━━━
📈 Trend: [Bullish/Bearish/Sideways]
🟢 Key Support: [level]
🔴 Key Resistance: [level]
💥 Breakout/Rejection: [Breaking out / Rejecting / Consolidating]
📦 Volume: [Confirms move? Yes/No]

⚡ TRADE SETUP
━━━━━━━━━━━━━━━
Entry Zone: [level]
Stop Loss: [level]
Take Profit: [level]
Risk-Reward: [ratio]

🎯 SCORE: [X/10]
✅ RECOMMENDATION: [Take Trade / Wait / Avoid]
💬 REASONING: [2-3 sentences]"""

PROMPTS = {
    "ema": EMA_PROMPT,
    "smc": SMC_PROMPT,
    "sr": SR_PROMPT
}

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
        mode = request.form.get("mode", "ema")
        custom_prompt = request.form.get("custom_prompt", "")

        if not image_file:
            return jsonify({"reply": "No chart image received."})

        if mode == "custom" and custom_prompt:
            analysis_prompt = custom_prompt
        else:
            analysis_prompt = PROMPTS.get(mode, EMA_PROMPT)

        image_data = base64.b64encode(image_file.read()).decode("utf-8")
        mime_type = image_file.mimetype

        response = client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
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
                            "text": analysis_prompt + "\n\nIMPORTANT: Output ONLY the formatted analysis. No step-by-step thinking. No 'The final answer is'. No boxes. Just the clean formatted result."
                        }
                    ]
                }
            ]
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"Analysis failed: {str(e)}"})

@app.route("/generate-prompt", methods=["POST"])
def generate_prompt():
    try:
        strategy = request.json.get("strategy")
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert trading analyst. Convert the user's trading strategy into a chart analysis prompt.

The prompt you generate MUST instruct the AI to:
1. Analyze the chart directly without explaining steps
2. Output ONLY in this clean format:

📊 TRADE REVIEW — [Strategy Name]
━━━━━━━━━━━━━━━
[Key analysis points based on the strategy]

⚡ TRADE SETUP
━━━━━━━━━━━━━━━
Entry Zone: [level]
Stop Loss: [level]
Take Profit: [level]
Risk-Reward: [ratio]

🎯 SCORE: [X/10]
✅ RECOMMENDATION: [Take Trade / Wait / Avoid]
💬 REASONING: [2-3 sentences maximum]

The prompt must strictly say: Do not show your thinking process. Do not number your steps. Output only the formatted result above."""
                },
                {
                    "role": "user",
                    "content": f"Convert this trading strategy into a chart analysis prompt: {strategy}"
                }
            ]
        )
        generated = response.choices[0].message.content
        return jsonify({"prompt": generated})
    except Exception as e:
        return jsonify({"prompt": f"Error: {str(e)}"})
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)