from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Discord Bot Token
TOKEN = os.getenv('BOT_TOKEN')

# Guild [DPS] API key & ID
API_KEY = os.getenv('USER_API_KEY')
GUILD_ID = os.getenv('GUILD_ID')


# Discord Server (Guild) ID
DISCORD_GUILD_ID = os.getenv('DISCORD_SERVER_ID')

# Role IDs
ROLE_ID_CONFIRMATION = os.getenv('ROLE_ID_CONFIRMATION')
ROLE_ID_GUEST = os.getenv('ROLE_ID_GUEST')
ROLE_ID_MEMBER = os.getenv('ROLE_ID_MEMBER')
ROLE_ID_FAMED_MEMBER = os.getenv('ROLE_ID_FAMED_MEMBER')
ROLE_ID_STAFF = os.getenv('ROLE_ID_STAFF')
ROLE_ID_ADMIN = os.getenv('ROLE_ID_ADMIN')
ROLE_ID_BIRTHDAY = os.getenv('ROLE_ID_BIRTHDAY')

# Channel IDs
CHANNEL_ID_MENTORS = os.getenv('CHANNEL_ID_MENTORS')
CHANNEL_ID_GENERAL = os.getenv('CHANNEL_ID_GENERAL')
CHANNEL_ID_RULES = os.getenv('CHANNEL_ID_RULES')

# Database
CURRENT_DB_VERSION = os.getenv('CURRENT_DB_VERSION')
DB_FILENAME_TEMPLATE = 'DPS_v{}.db'

def get_db_filename(version=CURRENT_DB_VERSION):
    return DB_FILENAME_TEMPLATE.format(version)

CURRENT_DB_FILENAME = get_db_filename()
