import os
from dotenv import load_dotenv

load_dotenv()

def get_admin_credentials():
    return os.getenv("ORDINO_ADMIN_USER", "admin"), os.getenv("ORDINO_ADMIN_PASSWORD", "1234")

def get_smtp_settings():
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", 587)),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", "")
    }
