from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Discord Bot Token
TOKEN = os.getenv('BOT_TOKEN')

# Guild [DPS] API key & ID
API_KEY = os.getenv('USER_API_KEY')
GUILD_ID = os.getenv('GUILD_ID')

# Discord Server (Guild) ID & Invite Link
DISCORD_GUILD_ID = os.getenv('DISCORD_SERVER_ID')
DISCORD_INVITE_URL = os.getenv('DISCORD_INVITE_URL')

# Role IDs
ROLE_ID_CONFIRMATION = int(os.getenv('ROLE_ID_CONFIRMATION'))
ROLE_ID_GUEST = int(os.getenv('ROLE_ID_GUEST'))
ROLE_ID_MEMBER = int(os.getenv('ROLE_ID_MEMBER'))
ROLE_ID_FAMED_MEMBER = int(os.getenv('ROLE_ID_FAMED_MEMBER'))
ROLE_ID_STAFF = int(os.getenv('ROLE_ID_STAFF'))
ROLE_ID_ADMIN = int(os.getenv('ROLE_ID_ADMIN'))
ROLE_ID_BIRTHDAY = int(os.getenv('ROLE_ID_BIRTHDAY'))

# Channel IDs
CHANNEL_ID_MENTORS = int(os.getenv('CHANNEL_ID_MENTORS'))
CHANNEL_ID_GENERAL = int(os.getenv('CHANNEL_ID_GENERAL'))
CHANNEL_ID_RULES = int(os.getenv('CHANNEL_ID_RULES'))

# Database
CURRENT_DB_VERSION = os.getenv('CURRENT_DB_VERSION')
DB_FILENAME_TEMPLATE = 'DPS_v{}.db'

def get_db_filename(version=CURRENT_DB_VERSION):
    return DB_FILENAME_TEMPLATE.format(version)

CURRENT_DB_FILENAME = get_db_filename()
