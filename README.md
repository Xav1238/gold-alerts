# Gold (XAUUSD) news alert bot: free setup

Checks gold-relevant news every ~5 minutes, has Gemini judge each headline (bullish / bearish / neutral for gold), and sends the verdict to your iPhone via Telegram. It also warns you ~30 minutes before high-impact USD events (CPI, NFP, FOMC). It never trades. You decide in the MT5 app.

Cost: $0. Alerts arrive minutes after the news, not seconds. Not financial advice.

## Setup (about 15 minutes)

### 1. Telegram bot
1. In Telegram, open **@BotFather** and send `/newbot`. Pick a name. Copy the **bot token**.
2. Open your new bot and send it any message (e.g. "hi").
3. In a browser, open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`. Find `"chat":{"id":123456789` . That number is your **chat id**.

### 2. Free API keys
- **Gemini** (judges headlines): https://aistudio.google.com/apikey
- **Finnhub** (extra news source): https://finnhub.io, then register and copy the key. Optional: the bot also works from free RSS feeds alone.

### 3. GitHub
1. Create a free GitHub account, then a new **public** repository (public repos get unlimited free Actions minutes). Don't put any keys in the code.
2. Upload every file in this folder, including `.github/workflows/alerts.yml`. On the GitHub website use **Add file > Create new file** and type `.github/workflows/alerts.yml` as the name to create that folder path.
3. Go to **Settings > Secrets and variables > Actions > New repository secret** and add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GEMINI_API_KEY`
   - `FINNHUB_API_KEY` (optional)
4. Open the **Actions** tab, enable workflows, choose **gold-alerts**, then **Run workflow**. The first run sends "Gold alert bot is live". After that it runs about every 5 minutes.

## Optional settings
Add under **Settings > Secrets and variables > Actions > Variables**:

| Variable | Default | Meaning |
|---|---|---|
| `MIN_CONFIDENCE` | `medium` | `low`, `medium` or `high`. Raise it for fewer alerts |
| `QUIET_HOURS` | off | e.g. `23-6`: overnight, only high-confidence news alerts |
| `CAL_LEAD_MIN` | `30` | Minutes of warning before big events |
| `CAL_COUNTRIES` | `USD` | e.g. `USD,EUR` |
| `MAX_AGE_MIN` | `90` | Ignore news older than this |
| `JUDGE_PROVIDER` | `gemini` | `gemini`, `claude` (paid, needs `ANTHROPIC_API_KEY`), or `keywords` (no AI) |

## Good to know
- GitHub's schedule is "best effort": runs can be a few minutes late, and GitHub pauses scheduled workflows in a repo with no activity for 60 days. Press **Run workflow** to wake it.
- If the AI call fails (quota, outage), the bot falls back to a simple keyword judge so alerts keep coming.
- News feeds are listed at the top of `sources.py`. If one stops working, edit or remove it.
- Test locally: `pip install -r requirements.txt` then `python main.py --dry-run`.
- Want seconds instead of minutes? Move it to a small always-on VPS and swap in a paid real-time feed. Only `sources.py` changes.
