# STACY XMD

Instagram assistant bot: AI DM replies, comment replies, story reply/mention handling, spam hiding,
keyword rules, human handoff. Python (FastAPI) + Groq + Supabase, ready for Vercel.

## Features
- **AI DM replies** via Groq, with per-user conversation memory in Supabase
- **Comment replies**: AI public replies, keyword rules, optional private DM to commenters
- **Story replies and story mentions** answered automatically (Instagram has no API to "view" stories)
- **Keyword rules** you edit live in Supabase or via the admin API (no redeploy)
- **Human handoff**: user says "human" and the bot goes quiet for them until you resume
- **Opt-out**: user sends STOP / START
- **Spam filter**: hides comments with links or blocked words
- **Rate limiting**, **webhook de-duplication**, **signature verification**
- **Admin API**: stats, global pause/resume, users, rules, manual send, token refresh

## 1. Supabase
Create a project, open SQL Editor, run `supabase/schema.sql`. Copy the Project URL and the
**service_role** key into `.env`.

## 2. Groq
Create a key at console.groq.com/keys and put it in `.env` as `GROQ_API_KEY`.

## 3. Meta / Instagram
1. Switch your Instagram to a Professional (Business or Creator) account.
2. developers.facebook.com > Create app > add **Instagram** > "API setup with Instagram login".
3. Add your account, generate an access token, and copy `IG_USER_ID`, `IG_ACCESS_TOKEN`, and the
   app secret (App settings > Basic) into `.env`. Invent any `IG_VERIFY_TOKEN`.
4. Permissions: `instagram_business_basic`, `instagram_business_manage_messages`,
   `instagram_business_manage_comments`. Your own account works in development mode without App Review.

## 4. Deploy to Vercel
```bash
npm i -g vercel
vercel link
bash scripts/push_env.sh      # sends your .env values to Vercel
vercel --prod
```
(Or add the variables by hand in Vercel > Project > Settings > Environment Variables.)

## 5. Connect the webhook
In the Meta app: Instagram > Webhooks
- Callback URL: `https://YOUR-PROJECT.vercel.app/webhook`
- Verify token: your `IG_VERIFY_TOKEN`
- Subscribe to: `messages`, `comments` (and `messaging_seen` if you like)

Check `https://YOUR-PROJECT.vercel.app/health` to confirm all three services show as configured.

## Admin API
Send header `X-Admin-Token: <ADMIN_TOKEN>`.

| Method | Path | What |
|---|---|---|
| GET | /admin/stats | counts and pause state |
| POST | /admin/pause, /admin/resume | global kill switch |
| GET | /admin/users | recent users |
| POST | /admin/users/{id}/{pause\|resume\|block\|unblock} | per user |
| GET | /admin/conversations/{id} | chat history |
| POST | /admin/send | `{"user_id","text"}` send a manual DM |
| GET/POST | /admin/rules | list / add `{"trigger","reply","dm_reply","match_type","scope"}` |
| DELETE | /admin/rules/{id} | remove a rule |
| POST | /admin/refresh-token | refresh the 60-day Instagram token (then update it on Vercel) |

## Local run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
# expose it with: ngrok http 8000  (use the https URL as the webhook callback)
```

## Notes
- Instagram only lets you DM someone within 24 hours of their last message.
- Vercel functions stop after the response, so the webhook finishes its work before returning 200
  (Groq is fast; `maxDuration` is 30s in `vercel.json`).
- Never commit `.env` (it is in `.gitignore`).
- Disclose automation: the default welcome message already says it is an automated assistant.
