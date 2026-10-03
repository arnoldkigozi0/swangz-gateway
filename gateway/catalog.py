"""The catalog of AI tools Swangz may use — names, categories, where they live, and pricing.

Seeded from the Swangz AI Tracker registry (47 tools) plus the two developer agents. `kind`:
  api  — routed through the gateway on the company API key (Claude, OpenAI, ElevenLabs, Higgsfield)
  dev  — a developer agent on an API key, available only to people an admin assigns (Claude Code, Codex)
  site — a website staff use directly; the browser access gate enables or blocks it by entitlement

Admins can add more tools at runtime. The built-ins (builtin=1) can be removed from the catalog and
restored, but not deleted outright; tools an admin added can be deleted.

`signin` is how a person gets into the tool when they open it from the portal:
  sso   — the tool's company plan signs them in with their Swangz (Google Workspace) account
  seat  — a seat on the company plan, under their own work email (the vendor invites them)
  own   — they use their own login (free tools)
  api   — nothing to sign in to: it runs on the company API key through the gateway
"""

import json
import time

# id, name, category, kind, provider, url, hosts (for the access gate), pricing_url, entry_usd, plans
SEED = [
    ["chatgpt", "ChatGPT", "Assistant", "api", "openai", "https://chatgpt.com/", ["chat.openai.com", "chatgpt.com", "sora.com"], "https://openai.com/chatgpt/pricing/", 20, [{"name": "Plus", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 200, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Team (per seat)", "monthlyUSD": 30, "unit": None, "included": None, "unitCostUSD": None}]],
    ["claude", "Claude", "Assistant", "api", "anthropic", "https://claude.ai/", ["claude.ai"], "https://www.anthropic.com/pricing", 20, [{"name": "Pro", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Max 5x", "monthlyUSD": 100, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Max 20x", "monthlyUSD": 200, "unit": None, "included": None, "unitCostUSD": None}]],
    ["higgsfield-ai", "Higgsfield AI", "Video", "api", "higgsfield", "https://higgsfield.ai/", ["higgsfield.ai"], "https://higgsfield.ai/pricing", 19, [{"name": "Starter", "monthlyUSD": 19, "unit": "credits", "included": 270, "unitCostUSD": 0.05}, {"name": "Plus", "monthlyUSD": 59, "unit": "credits", "included": 1200, "unitCostUSD": 0.05}, {"name": "Ultra", "monthlyUSD": 129, "unit": "credits", "included": 3000, "unitCostUSD": 0.05}]],
    ["elevenlabs", "ElevenLabs", "Voice", "api", "elevenlabs", "https://elevenlabs.io/", ["elevenlabs.io"], "https://elevenlabs.io/pricing", 6, [{"name": "Free", "monthlyUSD": 0, "unit": "credits", "included": 10000, "unitCostUSD": None}, {"name": "Starter", "monthlyUSD": 6, "unit": "credits", "included": 30000, "unitCostUSD": None}, {"name": "Creator", "monthlyUSD": 22, "unit": "credits", "included": 121000, "unitCostUSD": 0.0003}, {"name": "Pro", "monthlyUSD": 99, "unit": "credits", "included": 600000, "unitCostUSD": 0.00024}, {"name": "Scale", "monthlyUSD": 299, "unit": "credits", "included": 1800000, "unitCostUSD": 0.00018}, {"name": "Business", "monthlyUSD": 990, "unit": "credits", "included": 6000000, "unitCostUSD": 0.00012}]],
    ["claude-code", "Claude Code", "Coding", "dev", "anthropic", "https://claude.com/claude-code", [], "", 0, [{"name": "Metered (our API key)", "monthlyUSD": 0}]],
    ["codex", "Codex", "Coding", "dev", "openai", "https://openai.com/codex", [], "", 0, [{"name": "Metered (our API key)", "monthlyUSD": 0}]],
    ["social-insider", "Social Insider", "Analytics", "site", "", "https://www.socialinsider.io/", ["socialinsider.io"], "https://www.socialinsider.io/pricing", 99, [{"name": "Business", "monthlyUSD": 99, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Agency", "monthlyUSD": 169, "unit": None, "included": None, "unitCostUSD": None}]],
    ["gemini", "Gemini", "Assistant", "site", "", "https://gemini.google.com/", ["gemini.google.com"], "https://one.google.com/about/google-ai-plans/", 20, [{"name": "AI Pro", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}, {"name": "AI Ultra", "monthlyUSD": 250, "unit": None, "included": None, "unitCostUSD": None}]],
    ["make", "Make", "Automation", "site", "", "https://www.make.com/", ["make.com"], "https://www.make.com/en/pricing", 10, [{"name": "Core", "monthlyUSD": 10, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 19, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Teams", "monthlyUSD": 35, "unit": None, "included": None, "unitCostUSD": None}]],
    ["zapier", "Zapier", "Automation", "site", "", "https://zapier.com/", ["zapier.com"], "https://zapier.com/pricing", 30, [{"name": "Professional", "monthlyUSD": 30, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Team", "monthlyUSD": 103, "unit": None, "included": None, "unitCostUSD": None}]],
    ["n8n", "n8n", "Automation", "site", "", "https://n8n.io/", ["n8n.io"], "https://n8n.io/pricing/", 24, [{"name": "Starter", "monthlyUSD": 24, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 60, "unit": None, "included": None, "unitCostUSD": None}]],
    ["heygen", "Heygen", "Avatar video", "site", "", "https://www.heygen.com/", ["heygen.com"], "https://www.heygen.com/pricing", 29, [{"name": "Creator", "monthlyUSD": 29, "unit": "credits", "included": 600, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 49, "unit": "credits", "included": 1000, "unitCostUSD": None}, {"name": "Business", "monthlyUSD": 149, "unit": "credits", "included": 1500, "unitCostUSD": None}]],
    ["synthesia", "Synthesia", "Avatar video", "site", "", "https://www.synthesia.io/", ["synthesia.io"], "https://www.synthesia.io/pricing", 29, [{"name": "Starter", "monthlyUSD": 29, "unit": "minutes", "included": 10, "unitCostUSD": None}, {"name": "Creator", "monthlyUSD": 89, "unit": "minutes", "included": 30, "unitCostUSD": None}]],
    ["copilot", "Copilot", "Coding", "site", "", "https://copilot.microsoft.com/", ["copilot.microsoft.com", "github.com/copilot"], "https://github.com/features/copilot/plans", 10, [{"name": "Pro", "monthlyUSD": 10, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro+", "monthlyUSD": 39, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Business", "monthlyUSD": 19, "unit": None, "included": None, "unitCostUSD": None}]],
    ["cursor", "Cursor", "Coding", "site", "", "https://www.cursor.com/", ["cursor.com"], "https://www.cursor.com/pricing", 20, [{"name": "Pro", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro+", "monthlyUSD": 60, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Ultra", "monthlyUSD": 200, "unit": None, "included": None, "unitCostUSD": None}]],
    ["canva", "Canva", "Design", "site", "", "https://www.canva.com/", ["canva.com"], "https://www.canva.com/pricing/", 10, [{"name": "Pro", "monthlyUSD": 15, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Teams (per seat)", "monthlyUSD": 10, "unit": None, "included": None, "unitCostUSD": None}]],
    ["figma-ai", "Figma AI", "Design", "site", "", "https://www.figma.com/ai/", ["figma.com"], "https://www.figma.com/pricing/", 15, [{"name": "Professional", "monthlyUSD": 15, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Organization", "monthlyUSD": 45, "unit": None, "included": None, "unitCostUSD": None}]],
    ["photoshop", "Photoshop", "Design", "site", "", "https://www.adobe.com/products/photoshop.html", ["adobe.com"], "https://www.adobe.com/products/photoshop/plans.html", 10, [{"name": "Photography", "monthlyUSD": 10, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Single app", "monthlyUSD": 23, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Creative Cloud", "monthlyUSD": 60, "unit": None, "included": None, "unitCostUSD": None}]],
    ["adobe-firefly", "Adobe Firefly", "Image", "site", "", "https://firefly.adobe.com/", ["firefly.adobe.com"], "https://www.adobe.com/products/firefly/plans.html", 10, [{"name": "Standard", "monthlyUSD": 10, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 30, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Premium", "monthlyUSD": 200, "unit": None, "included": None, "unitCostUSD": None}]],
    ["dall-e", "DALL-E", "Image", "site", "", "https://openai.com/dall-e-3", ["openai.com"], "https://openai.com/chatgpt/pricing/", 20, [{"name": "ChatGPT Plus (incl.)", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}]],
    ["ideogram", "Ideogram", "Image", "site", "", "https://ideogram.ai/", ["ideogram.ai"], "https://ideogram.ai/features/pricing", 8, [{"name": "Basic", "monthlyUSD": 8, "unit": "credits", "included": 400, "unitCostUSD": None}, {"name": "Plus", "monthlyUSD": 20, "unit": "credits", "included": 1000, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 60, "unit": "credits", "included": 3500, "unitCostUSD": None}]],
    ["krea", "Krea", "Image", "site", "", "https://www.krea.ai/", ["krea.ai"], "https://www.krea.ai/pricing", 9, [{"name": "Basic", "monthlyUSD": 9, "unit": "credits", "included": 5000, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 35, "unit": "credits", "included": 20000, "unitCostUSD": None}, {"name": "Max", "monthlyUSD": 70, "unit": "credits", "included": 60000, "unitCostUSD": None}]],
    ["magnific", "Magnific", "Image", "site", "", "https://magnific.ai/", ["magnific.ai"], "https://magnific.ai/pricing", 39, [{"name": "Plus", "monthlyUSD": 39, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 99, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Premium", "monthlyUSD": 299, "unit": None, "included": None, "unitCostUSD": None}]],
    ["midjourney", "Midjourney", "Image", "site", "", "https://www.midjourney.com/", ["midjourney.com"], "https://docs.midjourney.com/hc/en-us/articles/30760036574605-Subscriptions-Plans", 10, [{"name": "Basic", "monthlyUSD": 10, "unit": "minutes", "included": 198, "unitCostUSD": 0.0666667}, {"name": "Standard", "monthlyUSD": 30, "unit": "minutes", "included": 900, "unitCostUSD": 0.0666667}, {"name": "Pro", "monthlyUSD": 60, "unit": "minutes", "included": 1800, "unitCostUSD": 0.0666667}, {"name": "Mega", "monthlyUSD": 120, "unit": "minutes", "included": 3600, "unitCostUSD": 0.0666667}]],
    ["stable-diffusion", "Stable Diffusion", "Image", "site", "", "https://stability.ai/", ["stability.ai"], "https://stability.ai/membership", 0, []],
    ["suno", "Suno", "Music", "site", "", "https://suno.com/", ["suno.com"], "https://suno.com/pricing", 10, [{"name": "Pro", "monthlyUSD": 10, "unit": "credits", "included": 2500, "unitCostUSD": None}, {"name": "Premier", "monthlyUSD": 30, "unit": "credits", "included": 10000, "unitCostUSD": None}]],
    ["udio", "Udio", "Music", "site", "", "https://www.udio.com/", ["udio.com"], "https://www.udio.com/pricing", 10, [{"name": "Standard", "monthlyUSD": 10, "unit": "credits", "included": 2400, "unitCostUSD": 0.025}, {"name": "Pro", "monthlyUSD": 30, "unit": "credits", "included": 6000, "unitCostUSD": 0.025}]],
    ["heyeddie", "HeyEddie", "Other", "site", "", "https://heyeddie.ai/", ["heyeddie.ai"], "", 0, []],
    ["airtable-ai", "Airtable AI", "Productivity", "site", "", "https://www.airtable.com/platform/ai", ["airtable.com"], "https://www.airtable.com/pricing", 24, [{"name": "Team", "monthlyUSD": 24, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Business", "monthlyUSD": 54, "unit": None, "included": None, "unitCostUSD": None}]],
    ["loom-ai", "Loom AI", "Productivity", "site", "", "https://www.loom.com/ai", ["loom.com"], "https://www.loom.com/pricing", 15, [{"name": "Business", "monthlyUSD": 15, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Business + AI", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}]],
    ["notion-ai", "Notion AI", "Productivity", "site", "", "https://www.notion.so/product/ai", ["notion.so"], "https://www.notion.so/pricing", 12, [{"name": "Plus", "monthlyUSD": 12, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Business", "monthlyUSD": 18, "unit": None, "included": None, "unitCostUSD": None}]],
    ["otter-ai", "Otter.ai", "Productivity", "site", "", "https://otter.ai/", ["otter.ai"], "https://otter.ai/pricing", 17, [{"name": "Pro", "monthlyUSD": 17, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Business", "monthlyUSD": 30, "unit": None, "included": None, "unitCostUSD": None}]],
    ["perplexity", "Perplexity", "Research", "site", "", "https://www.perplexity.ai/", ["perplexity.ai"], "https://www.perplexity.ai/pro", 20, [{"name": "Pro", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Max", "monthlyUSD": 200, "unit": None, "included": None, "unitCostUSD": None}]],
    ["kling-ai", "Kling AI", "Video", "site", "", "https://kling.kuaishou.com/", ["kling.kuaishou.com", "klingai.com"], "https://klingai.com/pricing", 10, [{"name": "Standard", "monthlyUSD": 10, "unit": "credits", "included": 660, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 37, "unit": "credits", "included": 3000, "unitCostUSD": None}, {"name": "Premier", "monthlyUSD": 92, "unit": "credits", "included": 8000, "unitCostUSD": None}]],
    ["luma-dream-machine", "Luma Dream Machine", "Video", "site", "", "https://lumalabs.ai/dream-machine", ["lumalabs.ai"], "https://lumalabs.ai/dream-machine/pricing", 30, [{"name": "Plus", "monthlyUSD": 30, "unit": "credits", "included": 10000, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 90, "unit": "credits", "included": 40000, "unitCostUSD": None}, {"name": "Ultra", "monthlyUSD": 300, "unit": "credits", "included": 150000, "unitCostUSD": None}]],
    ["pika-labs", "Pika Labs", "Video", "site", "", "https://pika.art/", ["pika.art"], "https://pika.art/pricing", 10, [{"name": "Standard", "monthlyUSD": 10, "unit": "credits", "included": 700, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 35, "unit": "credits", "included": 2300, "unitCostUSD": None}, {"name": "Fancy", "monthlyUSD": 95, "unit": "credits", "included": 6000, "unitCostUSD": None}]],
    ["runway", "Runway", "Video", "site", "", "https://runwayml.com/", ["app.runwayml.com", "runwayml.com"], "https://runway.com/pricing", 15, [{"name": "Standard", "monthlyUSD": 15, "unit": "credits", "included": 625, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 35, "unit": "credits", "included": 2250, "unitCostUSD": None}, {"name": "Max", "monthlyUSD": 95, "unit": "credits", "included": 9500, "unitCostUSD": None}]],
    ["seedance", "Seedance", "Video", "site", "", "https://higgsfield.ai/seedance", ["higgsfield.ai"], "", 0, []],
    ["sora", "Sora", "Video", "site", "", "https://sora.com/", ["sora.com"], "https://openai.com/chatgpt/pricing/", 20, [{"name": "ChatGPT Plus", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}, {"name": "ChatGPT Pro", "monthlyUSD": 200, "unit": None, "included": None, "unitCostUSD": None}]],
    ["adobe-premiere", "Adobe Premiere", "Video editing", "site", "", "https://www.adobe.com/products/premiere.html", ["adobe.com"], "https://www.adobe.com/creativecloud/plans.html", 23, [{"name": "Single app", "monthlyUSD": 23, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Creative Cloud", "monthlyUSD": 60, "unit": None, "included": None, "unitCostUSD": None}]],
    ["capcut", "CapCut", "Video editing", "site", "", "https://www.capcut.com/", ["capcut.com"], "https://www.capcut.com/pricing", 8, [{"name": "Pro", "monthlyUSD": 8, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro+", "monthlyUSD": 20, "unit": None, "included": None, "unitCostUSD": None}]],
    ["davinci-resolve", "DaVinci Resolve", "Video editing", "site", "", "https://www.blackmagicdesign.com/products/davinciresolve", ["blackmagicdesign.com"], "https://www.blackmagicdesign.com/products/davinciresolve", 0, [{"name": "Free", "monthlyUSD": 0, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Studio (one-time)", "monthlyUSD": 0, "unit": None, "included": None, "unitCostUSD": None}]],
    ["opus-clip", "Opus Clip", "Video editing", "site", "", "https://www.opus.pro/", ["opus.pro"], "https://www.opus.pro/pricing", 9, [{"name": "Starter", "monthlyUSD": 9, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 19, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Premium", "monthlyUSD": 99, "unit": None, "included": None, "unitCostUSD": None}]],
    ["topaz-video-ai", "Topaz Video AI", "Video editing", "site", "", "https://www.topazlabs.com/topaz-video-ai", ["topazlabs.com"], "https://www.topazlabs.com/topaz-video-ai", 0, []],
    ["descript", "Descript", "Voice", "site", "", "https://www.descript.com/", ["descript.com"], "https://www.descript.com/pricing", 16, [{"name": "Hobbyist", "monthlyUSD": 16, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Creator", "monthlyUSD": 24, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Business", "monthlyUSD": 50, "unit": None, "included": None, "unitCostUSD": None}]],
    ["copy-ai", "Copy.ai", "Writing", "site", "", "https://www.copy.ai/", ["copy.ai"], "https://www.copy.ai/prices", 49, [{"name": "Starter", "monthlyUSD": 49, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Advanced", "monthlyUSD": 249, "unit": None, "included": None, "unitCostUSD": None}]],
    ["deepl", "DeepL", "Writing", "site", "", "https://www.deepl.com/", ["deepl.com"], "https://www.deepl.com/pro", 10, [{"name": "Starter", "monthlyUSD": 10, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Advanced", "monthlyUSD": 35, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Ultimate", "monthlyUSD": 69, "unit": None, "included": None, "unitCostUSD": None}]],
    ["grammarly", "Grammarly", "Writing", "site", "", "https://www.grammarly.com/", ["grammarly.com"], "https://www.grammarly.com/plans", 12, [{"name": "Pro", "monthlyUSD": 12, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Enterprise", "monthlyUSD": 25, "unit": None, "included": None, "unitCostUSD": None}]],
    ["jasper", "Jasper", "Writing", "site", "", "https://www.jasper.ai/", ["jasper.ai"], "https://www.jasper.ai/pricing", 39, [{"name": "Creator", "monthlyUSD": 39, "unit": None, "included": None, "unitCostUSD": None}, {"name": "Pro", "monthlyUSD": 59, "unit": None, "included": None, "unitCostUSD": None}]],
]

# one line about each built-in, and a brand colour for its tile when there is no logo yet
DETAILS = {
    "chatgpt": ("OpenAI's assistant for writing, research, analysis and images.", "#10A37F"),
    "claude": ("Anthropic's assistant for writing, analysis and long documents.", "#D97757"),
    "higgsfield-ai": ("Cinematic AI video and image generation.", "#7FA830"),
    "elevenlabs": ("Lifelike voice-overs, dubbing and sound effects.", "#5B5B6B"),
    "claude-code": ("Anthropic's coding agent for the terminal and editor.", "#D97757"),
    "codex": ("OpenAI's coding agent for the terminal and editor.", "#10A37F"),
    "social-insider": ("Social media analytics and competitor benchmarks.", "#3B5BDB"),
    "gemini": ("Google's assistant, connected to Workspace.", "#4285F4"),
    "make": ("Visual automation across apps and AI services.", "#6D00CC"),
    "zapier": ("Connect apps and automate workflows with AI steps.", "#FF4F00"),
    "n8n": ("Workflow automation with AI agents.", "#EA4B71"),
    "heygen": ("AI avatar videos and video translation.", "#7559FF"),
    "synthesia": ("Presenter-led AI videos from a script.", "#4C3AE3"),
    "copilot": ("Microsoft's AI assistant.", "#0078D4"),
    "cursor": ("The AI-first code editor.", "#3C4A5E"),
    "canva": ("Design anything, with Magic Studio AI.", "#00A9B0"),
    "figma-ai": ("AI features inside Figma.", "#A259FF"),
    "photoshop": ("Photoshop with Generative Fill.", "#1C8FE0"),
    "adobe-firefly": ("Adobe's generative image and video models.", "#E1251B"),
    "dall-e": ("OpenAI's image generation.", "#10A37F"),
    "ideogram": ("Image generation with strong typography.", "#5B3DF5"),
    "krea": ("Real-time image generation and upscaling.", "#2F6BFF"),
    "magnific": ("AI upscaling and image enhancement.", "#E8447A"),
    "midjourney": ("High-end image generation.", "#3A4CC0"),
    "stable-diffusion": ("Stability AI's open image models.", "#8B5CF6"),
    "suno": ("Songs and music from a prompt.", "#E8863A"),
    "udio": ("AI music generation.", "#E84D8A"),
    "heyeddie": ("From the Swangz AI Tracker registry.", "#4C9A8A"),
    "airtable-ai": ("AI fields and apps on Airtable data.", "#E0A100"),
    "loom-ai": ("Screen recordings with AI titles, summaries and edits.", "#625DF5"),
    "notion-ai": ("Write, summarise and search inside Notion.", "#5A5A55"),
    "otter-ai": ("Meeting transcription and notes.", "#2E7CF6"),
    "perplexity": ("Answers with cited sources.", "#20808D"),
    "kling-ai": ("Text- and image-to-video generation.", "#00A396"),
    "luma-dream-machine": ("Luma's video generation.", "#6E56CF"),
    "pika-labs": ("Playful AI video generation and effects.", "#D4A12A"),
    "runway": ("AI video generation and editing tools.", "#5B5F97"),
    "seedance": ("ByteDance's video model, on Higgsfield.", "#3EA6FF"),
    "sora": ("OpenAI's video generation.", "#10A37F"),
    "adobe-premiere": ("Adobe's video editor, with AI features.", "#7C6CF0"),
    "capcut": ("Video editing with AI captions and effects.", "#4A4F5A"),
    "davinci-resolve": ("Editing, colour and audio with Neural Engine AI.", "#E2643B"),
    "opus-clip": ("Turns long videos into short clips.", "#6C5CE7"),
    "topaz-video-ai": ("Video upscaling, denoising and frame interpolation.", "#2D9CDB"),
    "descript": ("Edit audio and video by editing the transcript.", "#0A5DFF"),
    "copy-ai": ("Marketing copy and go-to-market workflows.", "#6C47FF"),
    "deepl": ("High-quality translation and writing.", "#0F2B46"),
    "grammarly": ("Writing assistance and tone checks.", "#15A383"),
    "jasper": ("Marketing content in your brand voice.", "#FA4028"),
}

SIGNIN = ("sso", "seat", "own", "api")

FIELDS = ("id", "name", "category", "kind", "provider", "url", "hosts", "pricing_url", "entry_usd", "plans")


def seed(db):
    """Insert the built-in tools once. Admin edits (a different plan, extra hosts) are never overwritten."""
    if db.get_setting("catalog_seeded") == "1":
        return
    now = time.time()
    with db.tx():
        for row in SEED:
            d = dict(zip(FIELDS, row))
            db.x("INSERT OR IGNORE INTO tools(id, name, category, kind, provider, url, hosts, pricing_url,"
                 " entry_usd, plans, builtin, created) VALUES(?,?,?,?,?,?,?,?,?,?,1,?)",
                 (d["id"], d["name"], d["category"], d["kind"], d["provider"], d["url"],
                  ",".join(d["hosts"]), d["pricing_url"], d["entry_usd"], json.dumps(d["plans"]), now))
        db.set_setting("catalog_seeded", "1")


def refine(db):
    """Fill in a description and colour for built-ins that have none. Never overwrites an admin's edit."""
    if db.get_setting("catalog_details") == "1":
        return
    with db.tx():
        for tid, (description, color) in DETAILS.items():
            db.x("UPDATE tools SET description = ? WHERE id = ? AND description = ''", (description, tid))
            db.x("UPDATE tools SET color = ? WHERE id = ? AND color = ''", (color, tid))
        db.set_setting("catalog_details", "1")


def launch_target(tool):
    """Where the portal sends someone who opens this tool: its sign-in link if set, else its website.
    Only http(s) addresses — anything else (javascript:, data:) is refused."""
    for candidate in (tool.get("launch_url"), tool.get("url")):
        candidate = (candidate or "").strip()
        if candidate.lower().startswith(("https://", "http://")):
            return candidate
    return None


def hosts_from_url(url):
    """example.com from https://www.example.com/path — so a new tool is governed without typing domains."""
    url = (url or "").strip().lower()
    if not url.startswith(("https://", "http://")):
        return []
    host = url.split("://", 1)[1].split("/")[0].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return [host] if "." in host else []


def host_index(db):
    """{hostname: tool row} for the access gate, longest host first so app subdomains win.

    Covers every tool with a website, API tools included: claude.ai and chatgpt.com are reached in a
    browser even though their API also runs through the gateway, so the gate governs both.
    """
    index = {}
    for t in db.q("SELECT * FROM tools WHERE hosts != '' AND archived = 0"):
        for h in t["hosts"].split(","):
            h = h.strip().lower()
            if h:
                index[h] = t
    return dict(sorted(index.items(), key=lambda kv: -len(kv[0])))


def match_host(index, hostname):
    """The tool whose domain owns this hostname (exact, or a subdomain of it)."""
    hostname = (hostname or "").lower().split(":")[0]
    if hostname.startswith("www."):
        hostname = hostname[4:]
    for h, tool in index.items():
        if hostname == h or hostname.endswith("." + h):
            return tool
    return None


def provider_tool(db, provider, client):
    """Which catalog tool a proxied request belongs to: the dev agent by client name, else the API tool."""
    if client == "Claude Code":
        row = db.one("SELECT * FROM tools WHERE id = 'claude-code'")
        if row:
            return row
    if client == "Codex":
        row = db.one("SELECT * FROM tools WHERE id = 'codex'")
        if row:
            return row
    return db.one("SELECT * FROM tools WHERE kind = 'api' AND provider = ? LIMIT 1", (provider,))
