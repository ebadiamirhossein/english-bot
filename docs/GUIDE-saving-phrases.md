# Saving phrases from shows — how it works

A short guide for both of us. Two separate things: getting phrases **into the bot**, and getting cards **into Anki**.

---

## Part 1 — Getting phrases into the bot

### The easy way (no files at all)

While you're watching, if you see a phrase worth keeping, just send it to the bot in Telegram:

- **Type or paste it** with `/capture` in front:
  `/capture Could you circle back on this by Friday?`
- **Or forward** any English message straight to the bot — no command needed.

The bot explains it, pulls out the useful phrases, and adds them to your review. They come back in your morning quiz over the next weeks.

**This works today and needs no setup.** For a handful of phrases per episode it's the fastest option.

### The bulk way (a file)

If you save a lot of phrases while watching, the extensions can export them all at once.

**Trancy** (Disney+, YouTube)
1. Click the Trancy icon in your browser
2. Open your saved words / vocabulary list
3. Find **Export** and choose **CSV**
4. The file goes to your Downloads folder

**Language Reactor** (Netflix, YouTube)
1. Go to **languagereactor.com**
2. Open **Saved Items**
3. Click **Export** (top right)
4. Choose **CSV**
5. The file goes to your Downloads folder

Language Reactor has an option called **"only new items since last export"** — leave it on if you see it. It doesn't matter much (the bot skips anything it already has), but it makes the file smaller.

### Where to send the file

**Send it to the bot in Telegram**, like sending any file:
1. Open the chat with the bot
2. Tap the paperclip 📎
3. Choose **File**
4. Pick the CSV from Downloads
5. Send

The bot reads it and tells you how many phrases it added.

> **Note:** there is also a Google Drive folder set up on Amirhossein's laptop. That only works for his account — the bot can't see anyone else's Drive. **Telegram is the way that works for both of us.**

---

## Part 2 — Getting cards into Anki

Anki is optional. The bot already reviews your phrases inside Telegram, about two per day in the morning quiz. Anki is for going faster, or for reviewing outside Telegram.

### One-time setup (about 5 minutes, on a computer)

1. Install Anki from **apps.ankiweb.net**
2. Make a free account at **ankiweb.net** — this syncs your cards to your phone
3. In Anki: **Tools → Manage Note Types → Add → Add: Basic → OK**
4. Name it **English Bot**
5. Select it → **Fields**
6. Rename `Front` to **Sentence**, rename `Back` to **Answer**
7. Click **Add** → **Meaning**. Click **Add** → **Source**
8. **Save**

Optional but worth it — show the meaning on the answer side:
1. Select **English Bot** → **Cards**
2. Click **Back Template**
3. Replace everything with:

```
{{Sentence}}

<hr id=answer>

<b>{{Answer}}</b>

<div style="font-size:16px; color:#888;">{{Meaning}}</div>
<div style="font-size:14px; color:#aaa;">{{Source}}</div>
```

4. **Save**

### Every week (about 1 minute)

The bot sends a `.tsv` file every Saturday evening. You can also ask for it any time with `/anki`.

1. Tap the file in Telegram to download it
2. In Anki: **File → Import**
3. Pick the file
4. Set **Note Type** to **English Bot**
5. Check the field mapping: 1 → Sentence, 2 → Answer, 3 → Meaning, 4 → Source
6. Click **Import**
7. Click **Sync** so it reaches your phone

Steps 4 and 5 only need checking the first time — Anki remembers.

**On your phone:** AnkiDroid (Android, free) or AnkiMobile (iPhone, paid). Log in with the same AnkiWeb account and the cards appear. Import on a computer, review on your phone.

---

## Quick reference

| What you want | What to do |
|---|---|
| Save one phrase you just heard | `/capture <phrase>` or forward it |
| Save a whole session's phrases | Export CSV → send the file to the bot |
| Get Anki cards | `/anki`, or wait for Saturday |
| See what's waiting for review | `/stats` |
| See everything the bot can do | `/help` |

---

## If something goes wrong

**The bot says the file couldn't be read** — the export format may differ from what it expects. Send the CSV to Amirhossein; it's a small fix.

**Phrases imported but look wrong** — same thing. Send the file.

**Anki import puts things in the wrong fields** — check Note Type is **English Bot**, not **Basic**. Basic only has two fields, so Meaning and Source end up as tags.

**Nothing happens after sending the file** — check it's actually a `.csv`. The bot doesn't read `.txt`, `.xlsx` or Anki's own `.apkg` format.
