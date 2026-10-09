"""For what: the likely purpose of an AI request, and how sure the gateway is.

Four sources, always recorded with the result so nothing inferred is ever shown as fact:

* **declared** — the person or their tool said so: an `X-Swangz-Purpose` header (and optionally
  `X-Swangz-Project`) on a gateway request, or the purpose picked in Studio. Taken as given.
* **derived** — the tool itself says it: a coding agent is software development, a voice service is
  audio production. True of the tool, not necessarily of this one request.
* **inferred** — simple, explainable rules over the typed prompt: each purpose has keywords (editable
  in the console), the purpose with clearly more distinct matches wins, and the matched words are kept
  as the evidence. No model is asked, nothing leaves the gateway, and it can be switched off
  (Settings → Access & records → Infer purpose).
* **unknown** — nothing above was strong enough. Unknown is an answer, not a gap to fill.

A request that carries no typed prompt (an agent sending tool results back) takes the purpose of the
earlier request in the same session, with that request named as the evidence.
"""

import re
import time

# id, name, description, keywords (comma-separated; a keyword may be a phrase)
SEED = [
    ("software-development", "Software development", "Writing, reviewing, testing and fixing code",
     "code,coding,function,class,bug,debug,refactor,unit test,tests,pytest,repository,repo,commit,pull request,"
     "compile,stack trace,exception,api,endpoint,database,sql,javascript,typescript,python,deploy,dockerfile,"
     "css,html,lint,migration,regex,git"),
    ("design", "Design", "Visual design, layouts, logos, images",
     "logo,poster,layout,typography,colour palette,color palette,mockup,figma,brand identity,illustration,"
     "banner,thumbnail,artwork,design,moodboard,font"),
    ("video-production", "Video production", "Shooting, editing, colour and motion",
     "video,edit,timeline,premiere,davinci,resolve,colour grade,color grade,footage,b-roll,storyboard,"
     "shot list,after effects,render,frame rate,music video,cut,trailer,teaser"),
    ("audio-production", "Audio production", "Voice-over, music and sound",
     "voice-over,voiceover,voice over,podcast,audio,mix,mastering,beat,vocals,sound effect,jingle,narration,"
     "song,lyrics,instrumental"),
    ("marketing", "Marketing", "Campaigns, social posts, positioning",
     "campaign,marketing,social media,instagram,tiktok,facebook,caption,hashtag,audience,engagement,brand,"
     "press release,newsletter,promo,launch,advert,ad copy,seo,influencer"),
    ("content", "Content creation", "Articles, scripts and other writing",
     "blog,article,script,story,headline,copywriting,rewrite,draft,essay,outline,write a"),
    ("research", "Research", "Finding and summarising information",
     "research,summarise,summarize,sources,compare,literature,what is,explain,overview,market size,study"),
    ("data-analysis", "Data analysis", "Spreadsheets, numbers and charts",
     "spreadsheet,excel,csv,pivot,chart,dataset,statistics,average,regression,forecast,analysis,analyse,analyze,dashboard"),
    ("finance", "Finance", "Budgets, invoices and accounts",
     "invoice,budget,expense,payroll,tax,ugx,revenue,profit,quote,quotation,receipt,accounting,cash flow"),
    ("hr", "Human resources", "Hiring, staff and policies",
     "job description,recruit,hiring,interview questions,onboarding,leave policy,performance review,staff handbook,cv,resume"),
    ("customer-support", "Customer support", "Replying to customers and clients",
     "customer,client complaint,refund,support ticket,reply to,apology,booking enquiry,faq"),
    ("sales", "Sales", "Pitches, proposals and deals",
     "pitch,proposal,sales,deal,prospect,lead,pricing,sponsorship,partnership"),
    ("administration", "Administration", "Emails, scheduling and paperwork",
     "email,meeting,agenda,minutes,schedule,memo,letter,form,calendar"),
    ("strategy", "Strategy", "Plans, priorities and decisions",
     "strategy,roadmap,swot,okr,priorities,business plan,vision,positioning"),
    ("education", "Education and training", "Learning and teaching",
     "tutorial,teach,lesson,course,learn,training,quiz,explain like"),
    ("documentation", "Documentation", "Guides, manuals and documentation",
     "documentation,readme,guide,manual,how-to,spec,specification,changelog"),
    ("automation", "Automation", "Workflows and integrations",
     "automate,automation,zapier,n8n,make.com,workflow,webhook,cron,integration,script to"),
    ("productivity", "General productivity", "Everyday help", ""),
    ("other", "Other", "Anything else", ""),
]

SOURCES = ("declared", "derived", "inferred")
MIN_STRONG = 0.6     # an inference this sure beats what the tool alone suggests
MIN_SHOWN = 0.45     # below this, the answer is "unknown"
SCAN_CHARS = 6000    # how much of the prompt the rules read


def seed(db):
    if db.get_setting("purposes_seeded") == "1":
        return
    now = time.time()
    with db.tx():
        for i, (pid, name, desc, kw) in enumerate(SEED):
            db.x("INSERT OR IGNORE INTO purposes(id, name, description, keywords, sort, builtin, updated) VALUES(?,?,?,?,?,1,?)",
                 (pid, name, desc, kw, i, now))
        db.set_setting("purposes_seeded", "1")


class Taxonomy:
    """The live taxonomy with compiled keyword patterns. Rebuilt when an admin edits it."""

    def __init__(self, db):
        self.rows = db.q("SELECT * FROM purposes WHERE archived = 0 ORDER BY sort, name")
        self.by_id = {r["id"]: r for r in self.rows}
        self.by_name = {r["name"].lower(): r for r in self.rows}
        self.patterns = []
        for r in self.rows:
            words = [w.strip().lower() for w in (r["keywords"] or "").split(",") if w.strip()]
            if words:
                rx = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?![a-z0-9])")
                self.patterns.append((r["id"], rx))

    def resolve(self, text):
        """A declared purpose by id or name -> its id, or None."""
        t = (text or "").strip().lower()
        if t in self.by_id:
            return t
        row = self.by_name.get(t)
        return row["id"] if row else None


_cache = {}


def taxonomy(db):
    tx = _cache.get(id(db))
    if tx is None:
        tx = _cache[id(db)] = Taxonomy(db)
    return tx


def invalidate(db):
    _cache.pop(id(db), None)


def infer(tx, text):
    """-> (purpose id, confidence, evidence words) or (None, 0, []). Deterministic for the same text."""
    if not text:
        return None, 0.0, []
    lower = text[:SCAN_CHARS].lower()
    scores = []
    for pid, rx in tx.patterns:
        hits = sorted(set(rx.findall(lower)))
        if hits:
            scores.append((len(hits), pid, hits))
    if not scores:
        return None, 0.0, []
    scores.sort(key=lambda s: (-s[0], tx.by_id[s[1]]["sort"]))
    top, pid, hits = scores[0]
    runner = scores[1][0] if len(scores) > 1 else 0
    if top == runner:
        return None, 0.0, []  # a tie is not evidence of anything
    confidence = round(max(0.0, min(0.95, 0.3 + 0.15 * top - 0.1 * runner)), 2)
    return pid, confidence, hits[:8]


def derived(rec):
    """What the tool alone says about the purpose -> (purpose id, evidence) or (None, '')."""
    client = rec.get("client") or ""
    if client in ("Claude Code", "Codex", "OpenCode", "Cursor", "Aider", "Cline"):
        return "software-development", f"Coding agent: {client}"
    media = rec.get("media_type") or ""
    if media in ("voice", "sound", "music", "transcription"):
        return "audio-production", f"{media.capitalize()} generation"
    if media == "video":
        return "video-production", "Video generation"
    if media == "image":
        return "design", "Image generation"
    return None, ""


def classify(db, rec, headers=None, enabled=True):
    """The purpose fields for one request record (purpose, purpose_source, purpose_confidence,
    purpose_evidence, project). Never raises: a failure here must not lose the record."""
    out = {"purpose": None, "purpose_source": None, "purpose_confidence": None, "purpose_evidence": None, "project": None}
    try:
        tx = taxonomy(db)
        headers = headers or {}
        project = (headers.get("x-swangz-project") or "").strip()[:80]
        out["project"] = project or None
        declared = (headers.get("x-swangz-purpose") or "").strip()
        if declared:
            pid = tx.resolve(declared)
            if pid:
                return {**out, "purpose": pid, "purpose_source": "declared", "purpose_confidence": 1.0,
                        "purpose_evidence": "Declared by the person or their tool"}
        prompt = rec.get("prompt") or ""
        if not prompt and rec.get("session"):
            prev = db.one("SELECT id, purpose, purpose_source, purpose_confidence FROM requests WHERE session = ? AND purpose IS NOT NULL"
                          " AND ts > ? ORDER BY id DESC LIMIT 1", (rec["session"], (rec.get("ts") or time.time()) - 6 * 3600))
            if prev:
                return {**out, "purpose": prev["purpose"], "purpose_source": prev["purpose_source"],
                        "purpose_confidence": prev["purpose_confidence"], "purpose_evidence": f"Continues request #{prev['id']} in the same session"}
        guess, conf, words = infer(tx, prompt) if enabled else (None, 0.0, [])
        tool_pid, tool_why = derived(rec)
        if guess and conf >= MIN_STRONG:
            return {**out, "purpose": guess, "purpose_source": "inferred", "purpose_confidence": conf,
                    "purpose_evidence": "Matched: " + ", ".join(words)}
        if tool_pid and tool_pid in tx.by_id:
            return {**out, "purpose": tool_pid, "purpose_source": "derived", "purpose_confidence": None, "purpose_evidence": tool_why}
        if guess and conf >= MIN_SHOWN:
            return {**out, "purpose": guess, "purpose_source": "inferred", "purpose_confidence": conf,
                    "purpose_evidence": "Matched: " + ", ".join(words)}
    except Exception:  # noqa: BLE001 — classification is a convenience; the record matters more
        return out
    return out
