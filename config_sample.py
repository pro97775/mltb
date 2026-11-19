# REQUIRED CONFIG
BOT_TOKEN = ""
OWNER_ID = 0
TELEGRAM_API = 0
TELEGRAM_HASH = ""
# OPTIONAL CONFIG
BOT_PM = False
TG_PROXY = {}
USER_SESSION_STRING = ""
CMD_SUFFIX = ""
AUTHORIZED_CHATS = ""
SUDO_USERS = ""
DATABASE_URL = ""
DATABASE_NAME = "cloudbot"
STATUS_LIMIT = 4
DEFAULT_UPLOAD = "rc"
STATUS_UPDATE_INTERVAL = 15
FILELION_API = ""
STREAMWISH_API = ""
ALLDEBRID_API_KEY = ""
BUZZHEAVIER_ACCOUNT_ID = ""
BUZZHEAVIER_FOLDER_ID = ""
GOFILE_API_KEY = ""
TLDV_TOKEN = ""
# Instagram downloader API token (optional)
INSTADL_API = ""
EXCLUDED_EXTENSIONS = ""
INCLUDED_EXTENSIONS = ""
# Notify about incomplete tasks after restart / auto-resume them
INC_TASK_NOTIFY = False
INC_TASK_RESUME = False
YT_DLP_OPTIONS = ""
GALLERY_DL_OPTIONS = ""
USE_SERVICE_ACCOUNTS = False
NAME_SUBSTITUTE = r""
FFMPEG_CMDS = {"merge": ["-f concat -safe 0 -i mltb.txt -c copy mltb.mp4 -del"]}
UPLOAD_PATHS = {}
# GDrive Tools
GDRIVE_ID = ""
IS_TEAM_DRIVE = False
STOP_DUPLICATE = False
INDEX_URL = ""
# Rclone
RCLONE_PATH = ""
RCLONE_FLAGS = ""
RCLONE_SERVE_URL = ""
RCLONE_SERVE_PORT = 0
RCLONE_SERVE_USER = ""
RCLONE_SERVE_PASS = ""
# JDownloader
JD_EMAIL = ""
JD_PASS = ""
# Sabnzbd
USENET_SERVERS = [
    {
        "name": "main",
        "host": "",
        "port": 563,
        "timeout": 60,
        "username": "",
        "password": "",
        "connections": 8,
        "ssl": 1,
        "ssl_verify": 2,
        "ssl_ciphers": "",
        "enable": 1,
        "required": 0,
        "optional": 0,
        "retention": 0,
        "send_group": 0,
        "priority": 0,
    }
]
# Nzb search
HYDRA_IP = ""
HYDRA_API_KEY = ""
# Update
UPSTREAM_REPO = ""
UPSTREAM_BRANCH = "master"
# Leech
LEECH_SPLIT_SIZE = 0
AS_DOCUMENT = False
EQUAL_SPLITS = False
MEDIA_GROUP = False
USER_TRANSMISSION = False
HYBRID_LEECH = False
LEECH_FILENAME_PREFIX = ""
LEECH_DUMP_CHAT = ""
CLONE_DUMP_CHATS = ""
THUMBNAIL_LAYOUT = ""
FILES_LINKS = False
# qBittorrent/Aria2c
TORRENT_TIMEOUT = 0
# Torrent batching (0 = disabled). Files per batch and/or bytes per batch
FILES_PER_BATCH = 0
BATCH_MAX_SIZE = 0
# Only download these file types in batch mode (space/comma separated: video audio photo document apps); empty = all
TORRENT_FILE_TYPES = ""
# Skip files already uploaded for this torrent (tracked in MongoDB)
SKIP_UPLOADED_FILES = True
BASE_URL = ""
BASE_URL_PORT = 0
WEB_PINCODE = False
# Queueing system
QUEUE_ALL = 0
QUEUE_DOWNLOAD = 0
QUEUE_UPLOAD = 0
# RSS
RSS_DELAY = 600
RSS_CHAT = ""
RSS_SIZE_LIMIT = 0
# Torrent Search
SEARCH_API_LINK = ""
SEARCH_LIMIT = 0
SEARCH_PLUGINS = []
