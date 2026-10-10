"""Optional Hub email using the Gateway SMTP transport. In-app state survives failed delivery."""
import os
import time
from email.message import EmailMessage
from . import notify


def deliver(gw,send=None):
    host=os.environ.get('GATEWAY_SMTP_HOST','')
    if not host and send is None:
        return 0
    cfg={'host':host,'port':int(os.environ.get('GATEWAY_SMTP_PORT','587') or 587),
         'user':os.environ.get('GATEWAY_SMTP_USER',''),'password':os.environ.get('GATEWAY_SMTP_PASSWORD',''),
         'sender':os.environ.get('GATEWAY_SMTP_FROM','') or os.environ.get('GATEWAY_SMTP_USER','') or 'swangz-ai@localhost'}
    sent=0
    for row in gw.db.q("SELECT n.*,p.email FROM hub_notifications n JOIN people p ON p.id=n.person_id WHERE n.email_state IN ('pending','not_configured','failed') AND n.attempts<3 ORDER BY n.id LIMIT 50"):
        if not gw.settings.email_allowed(row['email']):
            gw.db.x("UPDATE hub_notifications SET email_state='failed',attempts=3 WHERE id=?",(row['id'],));continue
        message=EmailMessage()
        message['Subject']='Swangz AI Hub: reporting or request update'
        message['From']=cfg['sender'];message['To']=row['email']
        base=gw.settings.web_url or gw.public_url()
        message.set_content(row['title']+'\n\nOpen your authenticated workspace: '+base.rstrip('/')+'/'+row['href']+'\n\nSwangz AI Hub')
        try:
            (send or notify._smtp_send)(cfg,message)
        except Exception:
            # Do not log SMTP replies, account details or credentials.
            gw.db.x("UPDATE hub_notifications SET email_state='failed',attempts=attempts+1 WHERE id=?",(row['id'],))
        else:
            gw.db.x("UPDATE hub_notifications SET email_state='sent',emailed=?,attempts=attempts+1 WHERE id=?",(time.time(),row['id']))
            sent+=1
    return sent
