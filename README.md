# 🏆 Points & Leaderboard Telegram Bot

A fully automated, button-driven group management bot:
- Every member starts with **1000 points** ⭐
- Abusive / blacklisted words automatically **deduct points** 🚫 (message deleted, warning posted)
- **`/leaderboard`** posts a live, auto-generated image widget of the current standings 📊
- **Monthly automatic reset**: on the 1st of every month the bot announces the top 3 and
  their rewards, then resets everyone's points 🎁
- **Everything is controlled by the group owner** through inline buttons — no external
  dashboard, no typing complicated commands.

---

## 1. Create the bot with BotFather

1. Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
2. Copy the token it gives you (looks like `123456789:AA...`).
3. Send BotFather `/setprivacy` → choose your bot → **Disable** (this lets the bot read
   group messages so it can scan for blacklisted words).

## 2. Add the bot to your group

1. Add the bot to your group.
2. Promote it to **Administrator** with at least:
   - Delete messages
   - Restrict/ban members (only needed if you enable auto-mute-at-zero)
3. As the group **creator**, send `/admin` in the group (or `/panel` in a private
   chat with the bot) to open the control panel.

> Only the Telegram **group creator** gets admin-panel access — this matches the
> "everything stays in the owner's hands" requirement. Regular admins can't change
> settings, only the creator can.

## 3. Configure locally (optional, for testing)

```bash
pip install -r requirements.txt
cp .env.example .env      # then edit .env and paste your BOT_TOKEN
python3 main.py
```

## 4. Deploy on Wispbyte (wispbyte.com)

1. Sign up / log in at wispbyte.com and create a new server.
2. When choosing the Docker image, pick the **Python** image.
3. Open the file manager and upload every file in this project, keeping the folder
   structure (`handlers/`, `assets/`, `main.py`, `requirements.txt`, etc.).
4. Go to the **Startup** tab:
   - Set the startup file to `main.py`.
   - Add your Python packages (Wispbyte auto-installs from `requirements.txt`, but you
     can also list them manually in the "Additional Python Packages" field if needed).
   - Add an environment **variable**: `BOT_TOKEN` = *your token from BotFather*.
     (Do **not** upload your `.env` file — use Wispbyte's Variables field instead.)
5. Start the server from the **Console** tab and check the logs — you should see
   `Bot starting (polling mode)...`.
6. Free Wispbyte servers need a client-panel login at least once a month or they get
   archived — just log in occasionally to keep it active.

---

## Commands

### Everyone (inside the group)
| Command | What it does |
|---|---|
| `/start` | Registers you with starting points |
| `/leaderboard` | Sends the live leaderboard image widget |
| `/mypoints` or `/rank` | Shows your points & rank |
| `/rules` | Shows point rules & current rewards |
| `/rewards` | Lists configured rewards |

### Owner only (group creator)
| Command | What it does |
|---|---|
| `/admin` | Opens the full button panel directly in the group |
| `/panel` | (in DM with the bot) Opens the panel — pick from all groups you own |
| `/addpoints`, `/removepoints`, `/setpoints` | Reply to a member's message + amount |
| `/addblacklist word1 word2 ...` | Add blacklisted words |
| `/removeblacklist word1 word2 ...` | Remove blacklisted words |
| `/blacklist` | List current blacklisted words |
| `/setreward 1 $10 Gift Card` | Set the reward for a given rank |
| `/resetmonth` | Manually trigger the monthly reset & winner announcement |

### Admin Panel buttons (via `/admin` or `/panel`)
- 🚫 **Blacklist Words** — add / remove / list
- ⭐ **Points** — add / remove / set exact points for any member (by @username)
- 🎁 **Rewards** — set the reward text for 1st / 2nd / 3rd place
- ⚙️ **Settings** — starting points, penalty per violation, auto-delete toggle,
  auto-mute-at-zero toggle
- 📊 **View Leaderboard** — sends the widget image on demand
- 🔄 **Reset Leaderboard Now** — manual reset with confirmation step

---

## How it works under the hood

- **Storage**: a single SQLite file (`bot_data.db`) — no external database needed.
- **Leaderboard image**: rendered live with Pillow (rounded cards, gold/silver/bronze
  rank badges, member avatars pulled from Telegram profile photos, initials fallback).
- **Monthly reset**: a background job (`run_monthly`) fires on day 1 of every month and
  runs the same logic as `/resetmonth`, across every group the bot is in.

## Notes & things you may want to extend later
- Currently one flat penalty per offending message (not per bad word) — easy to change
  in `handlers/moderation.py` if you'd rather stack penalties.
- "Monetization" wasn't specified in detail — if you want paid tiers, sponsored
  messages, or a shop where points can be redeemed, that's a good next feature to add.
