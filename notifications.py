import requests
from telegram import Bot
import smtplib
from email.mime.text import MIMEText
import telegram
import asyncio
from datetime import datetime

class NotificationSystem:
    def __init__(self, telegram_token, telegram_chat_id, 
                 discord_webhook=None, email_config=None):
        self.bot = telegram.Bot(token=telegram_token)
        self.chat_id = telegram_chat_id
        self.discord_webhook = discord_webhook
        self.email_config = email_config
        self.message_queue = []
    
    async def send_telegram(self, message):
        """Envía mensaje a Telegram con formato y emojis"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_message = (
                f"🤖 Trading Bot - {timestamp}\n"
                f"------------------------\n"
                f"{message}\n"
                f"------------------------"
            )
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=formatted_message,
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            print(f"Error enviando mensaje a Telegram: {e}")
            self.message_queue.append(message)
            return False
            
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
    
    async def send_error(self, error_message):
        """Envía mensaje de error"""
        message = f"❌ ERROR:\n{error_message}"
        await self.send_telegram(message)
    
    async def send_trade_notification(self, trade_type, pair, price, size, stop_loss=None, take_profit=None):
        """Envía notificación específica de trading"""
        emoji = "🟢" if trade_type == "BUY" else "🔴"
        message = (
            f"{emoji} {trade_type} {pair}\n"
            f"💰 Precio: ${price:.2f}\n"
            f"📊 Tamaño: {size:.4f}\n"
        )
        
        if stop_loss:
            message += f"🛑 Stop Loss: ${stop_loss:.2f}\n"
        if take_profit:
            message += f"🎯 Take Profit: ${take_profit:.2f}\n"
            
        await self.send_telegram(message)
    
    async def send_daily_summary(self, trades, total_profit, win_rate):
        """Envía resumen diario de trading"""
        message = (
            f"📊 Resumen Diario\n"
            f"Operaciones: {len(trades)}\n"
            f"P&L: ${total_profit:.2f}\n"
            f"Win Rate: {win_rate:.1f}%"
        )
        await self.send_telegram(message)
    
    async def close(self):
        """Cierra las conexiones pendientes"""
        try:
            if hasattr(self, 'bot'):
                await self.bot.close()
        except Exception as e:
            print(f"Error cerrando notificaciones: {e}") 