from flask import Flask, render_template, request, jsonify
from groq import Groq
import os
import requests
import base64
import hashlib
import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import date, datetime, timedelta

from supabase import create_client
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

messages = [
    {"role": "system", "content": "You are Loki, a crypto trading assistant. Be concise, clear, and direct. Keep responses short and simple — 2 to 4 sentences max unless detailed explanation is needed. No dramatic language. No motivational speech. Talk like a knowledgeable friend, not a poet. When live data is provided in [Live Data: ...] format, always use that exact price. Never use training data for prices."}
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

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_reset_email(to_email, reset_link):
    try:
        body = f"""Hi,

We received a request to reset your Loki AI password.

Click the link below to set a new password. This link expires in 1 hour:
{reset_link}

If you didn't request this, you can safely ignore this email — your password will stay the same.

— Loki AI"""

        msg = MIMEText(body)
        msg["Subject"] = "Reset your Loki AI password"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Failed to send reset email: {e}")
        return False

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

@app.route("/risk-analysis", methods=["POST"])
def risk_analysis():
    try:
        direction = request.form.get("direction")
        entry = float(request.form.get("entry"))
        current = float(request.form.get("current"))
        stop_loss = float(request.form.get("stop_loss"))
        take_profit = float(request.form.get("take_profit"))
        capital = request.form.get("capital")
        image_file = request.files.get("chart")

        # Calculate key metrics
        if direction == "long":
            pnl = current - entry
            risk = entry - stop_loss
            reward = take_profit - entry
            remaining_reward = take_profit - current
            remaining_risk = current - stop_loss
        else:
            pnl = entry - current
            risk = stop_loss - entry
            reward = entry - take_profit
            remaining_reward = current - take_profit
            remaining_risk = stop_loss - current

        pnl_pct = (pnl / entry) * 100
        rr_ratio = round(reward / risk, 2) if risk != 0 else 0
        remaining_rr = round(remaining_reward / remaining_risk, 2) if remaining_risk != 0 else 0

        capital_text = ""
        if capital:
            capital = float(capital)
            risk_amount = (risk / entry) * capital
            risk_pct = (risk_amount / capital) * 100
            capital_text = f"Capital at Risk: ${risk_amount:,.2f} ({round(risk_pct, 2)}%)"

        status = "In Profit ✅" if pnl > 0 else "In Loss ❌" if pnl < 0 else "Breakeven ⚖️"

        data_summary = f"""
TRADE DATA:
Direction: {direction.upper()}
Entry Price: {entry}
Current Price: {current}
Stop Loss: {stop_loss}
Take Profit: {take_profit}
Current P&L: {round(pnl, 2)} ({round(pnl_pct, 2)}%)
Status: {status}
Original Risk/Reward: 1:{rr_ratio}
Remaining Risk/Reward: 1:{remaining_rr}
{capital_text}
"""

        prompt = f"""You are a professional risk manager using Van Tharp position management rules and Turtle Trading principles.

Analyze this trade and give a clear recommendation:

{data_summary}

RULES TO APPLY:
1. Never risk more than 2% of capital per trade
2. Move stop loss to breakeven once trade is 1R in profit
3. Cut losers fast if risk/reward has deteriorated
4. Let winners run if trend is still valid
5. Never average down on a losing trade

OUTPUT ONLY IN THIS FORMAT:
📊 RISK ANALYSIS REPORT
━━━━━━━━━━━━━━━
📍 Position Status: {status}
💰 Current P&L: {round(pnl, 2)} ({round(pnl_pct, 2)}%)
⚖️ Original Risk/Reward: 1:{rr_ratio}
📉 Remaining Risk/Reward: 1:{remaining_rr}
{f"⚠️ {capital_text}" if capital_text else ""}

🎯 RECOMMENDATION
━━━━━━━━━━━━━━━
Action: [Hold / Exit Now / Move Stop to Breakeven / Take Partial Profit]
Stop Loss Advice: [What to do with stop loss]
💬 Reasoning: [2-3 sentences based on the rules above]

Do not show thinking. Output only the formatted result above."""

        if image_file:
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
                                "image_url": {"url": f"data:{mime_type};base64,{image_data}"}
                            },
                            {"type": "text", "text": prompt + "\n\nAlso analyze the chart image to confirm if the trade is still visually valid based on current price action."}
                        ]
                    }
                ]
            )
        else:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a professional risk manager."},
                    {"role": "user", "content": prompt}
                ]
            )

        reply = response.choices[0].message.content
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Analysis failed: {str(e)}"})

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

@app.route("/signup", methods=["POST"])
def signup():
    try:
        data = request.json
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email and password required"})

        existing = supabase.table("users").select("*").eq("email", email).execute()
        if existing.data:
            return jsonify({"error": "Email already exists"})

        password_hash = hash_password(password)
        supabase.table("users").insert({
            "email": email,
            "password_hash": password_hash
        }).execute()

        return jsonify({"success": True, "email": email})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.json
        email = data.get("email")
        password = data.get("password")

        password_hash = hash_password(password)
        result = supabase.table("users").select("*").eq("email", email).eq("password_hash", password_hash).execute()

        if not result.data:
            return jsonify({"error": "Invalid email or password"})

        user = result.data[0]
        return jsonify({
            "success": True,
            "email": user["email"],
            "is_pro": user["is_pro"],
            "analyses_today": user["analyses_today"]
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/check-limit", methods=["POST"])
def check_limit():
    try:
        email = request.json.get("email")
        result = supabase.table("users").select("*").eq("email", email).execute()

        if not result.data:
            return jsonify({"error": "User not found"})

        user = result.data[0]

        today = str(date.today())

        if user["last_reset"] != today:
            supabase.table("users").update({
                "analyses_today": 0,
                "last_reset": today
            }).eq("email", email).execute()
            user["analyses_today"] = 0

        if user["is_pro"]:
            return jsonify({"allowed": True, "is_pro": True})

        if user["analyses_today"] >= 3:
            return jsonify({"allowed": False, "analyses_today": user["analyses_today"]})

        supabase.table("users").update({
            "analyses_today": user["analyses_today"] + 1
        }).eq("email", email).execute()

        return jsonify({"allowed": True, "analyses_today": user["analyses_today"] + 1})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/request-pro", methods=["POST"])
def request_pro():
    try:
        email = request.json.get("email")
        if not email:
            return jsonify({"error": "Email required"})

        supabase.table("users").update({
            "pro_requested": True
        }).eq("email", email).execute()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        email = request.json.get("email")
        if not email:
            return jsonify({"error": "Email required"})

        result = supabase.table("users").select("*").eq("email", email).execute()

        # Don't reveal whether the email exists or not — just say "success" either way.
        # This is a normal security practice so people can't use this to check
        # which emails have accounts.
        if not result.data:
            return jsonify({"success": True})

        token = secrets.token_urlsafe(32)
        expiry = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        supabase.table("users").update({
            "reset_token": token,
            "reset_token_expiry": expiry
        }).eq("email", email).execute()

        reset_link = f"{request.host_url}reset-password?token={token}"
        send_reset_email(email, reset_link)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/reset-password", methods=["GET"])
def reset_password_page():
    token = request.args.get("token", "")
    return render_template("reset_password.html", token=token)

@app.route("/reset-password", methods=["POST"])
def reset_password_submit():
    try:
        token = request.json.get("token")
        new_password = request.json.get("new_password")

        if not token or not new_password:
            return jsonify({"error": "Missing token or password"})

        if len(new_password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"})

        result = supabase.table("users").select("*").eq("reset_token", token).execute()
        if not result.data:
            return jsonify({"error": "This reset link is invalid or has already been used."})

        user = result.data[0]

        expiry_dt = datetime.fromisoformat(user["reset_token_expiry"])
        if expiry_dt.tzinfo is not None:
            expiry_dt = expiry_dt.replace(tzinfo=None)

        if datetime.utcnow() > expiry_dt:
            return jsonify({"error": "This reset link has expired. Please request a new one."})

        new_hash = hash_password(new_password)
        supabase.table("users").update({
            "password_hash": new_hash,
            "reset_token": None,
            "reset_token_expiry": None
        }).eq("email", user["email"]).execute()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)