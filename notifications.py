import requests
from telegram import Bot
import smtplib
from email.mime.text import MIMEText

class NotificationSystem:
    def __init__(self, telegram_token=None, telegram_chat_id=None, 
                 discord_webhook=None, email_config=None):
        self.telegram_bot = Bot(token=telegram_token) if telegram_token else None
        self.telegram_chat_id = telegram_chat_id
        self.discord_webhook = discord_webhook
        self.email_config = email_config
    
    async def send_telegram(self, message):
        if self.telegram_bot:
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message
            )
    
    def send_discord(self, message):
        if self.discord_webhook:
            requests.post(self.discord_webhook, 
                        json={"content": message})
    
    def send_email(self, subject, message):
        if self.email_config:
            msg = MIMEText(message)
            msg['Subject'] = subject
            msg['From'] = self.email_config['from']
            msg['To'] = self.email_config['to']
            
            with smtplib.SMTP_SSL(self.email_config['smtp_server']) as server:
                server.login(self.email_config['username'], 
                           self.email_config['password'])
                server.send_message(msg) 