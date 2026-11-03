from dotenv import load_dotenv
import os

load_dotenv()
MARKETPLACE_URL = os.getenv('MARKETPLACE_URL', 'http://127.0.0.1:8004')
RESERVATION_LIFETIME = 30
TRANSPORT_SPEED = {'walking': 5, 'bicycle': 15, 'motorcycle': 30, 'car': 40}
