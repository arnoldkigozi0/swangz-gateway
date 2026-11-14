import json,sys
from urllib.parse import urlsplit
pack=json.load(open('deploy/chrome-policy/swangz-company-chrome.json'))
allow=pack['URLAllowlist']
def rule_match(rule,url):
    u=urlsplit(url)
    if rule=='*': return True
    r=rule; scheme=None
    if '://' in r: scheme,r=r.split('://',1)
    if scheme and scheme!=u.scheme: return False
    host,_,path=r.partition('/'); path='/'+path if path else ''
    exact=host.startswith('.'); host=host.lstrip('.')
    h=u.hostname or ''
    ok = (h==host) if exact else (h==host or h.endswith('.'+host))
    return ok and (u.path or '/').startswith(path or '/')
def verdict(url):
    hits=[r for r in allow if rule_match(r,url)]
    return ('ALLOWED by '+', '.join(hits)) if hits else 'BLOCKED (falls to "*")'
urls={
 'ChatGPT start':'https://chatgpt.com/','ChatGPT login hop':'https://chatgpt.com/auth/login_with',
 'OpenAI sign-in host':'https://auth.openai.com/oauth/authorize','ChatGPT Google':'https://accounts.google.com/v3/signin/identifier',
 'Google youtube check frame':'https://accounts.youtube.com/accounts/CheckConnection','Google bscframe':'https://accounts.google.com/_/bscframe',
 'ChatGPT Apple':'https://appleid.apple.com/auth/authorize','Apple form iframe (unobserved, known Apple host)':'https://idmsa.apple.com/appleauth/auth/signin',
 'ChatGPT Microsoft (consumer)':'https://login.live.com/oauth20_authorize.srf','ChatGPT Microsoft (work/school)':'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
 'Claude start/login':'https://claude.ai/login','Claude Google popup':'https://accounts.google.com/o/oauth2/v2/auth',
 'Claude hCaptcha frame (observed)':'https://newassets.hcaptcha.com/captcha/v1/x/static/hcaptcha.html',
 'Claude docs: claude.com redirect':'https://claude.com/','Claude docs: SSO':'https://sso.claude.com/','Claude docs: platform OAuth':'https://platform.claude.com/',
 'Gemini start':'https://gemini.google.com/app','Gemini ServiceLogin':'https://accounts.google.com/ServiceLogin',
 'Cloudflare challenge frame':'https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile',
}
for k,u in urls.items(): print('%-48s %-62s %s'%(k,u[:62],verdict(u)))
