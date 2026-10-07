"""
Django settings for kanban project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-key-change-me",
)
DEBUG = env_bool("DEBUG")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o and "<" not in o and "your-" not in o
]

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'kanbanapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'kanbanapp.middleware.RoleLevelMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'kanban.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'kanbanapp' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'kanbanapp.context_processors.request_user',
            ],
        },
    },
]

WSGI_APPLICATION = 'kanban.wsgi.application'

# ---------------------------------------------------------------------------
# Database
#   Docker/LAN  -> PostgreSQL (POSTGRES_HOST ayarlandığında)
#   Yerel test  -> SQLite  (POSTGRES_HOST ayarlanmadığında)
# ---------------------------------------------------------------------------
if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get("POSTGRES_DB", "kanban"),
            'USER': os.environ.get("POSTGRES_USER", "kanban"),
            'PASSWORD': os.environ.get("POSTGRES_PASSWORD", "kanban"),
            'HOST': os.environ.get("POSTGRES_HOST", "db"),
            'PORT': os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'kanbanapp.User'
LOGIN_URL = 'login'
LOGIN_REDIRECT = 'dashboard'
LOGOUT_REDIRECT = 'login'

# ---------------------------------------------------------------------------
# Proxy settings normalization (Local network bypass for urllib/requests)
# ---------------------------------------------------------------------------
def _normalize_no_proxy():
    for env_var in ("NO_PROXY", "no_proxy"):
        val = os.environ.get(env_var, "")
        if not val:
            continue
        parts = [p.strip() for p in val.split(",") if p.strip()]
        expanded = list(parts)
        for p in parts:
            if p.startswith("*."):
                dot_dom = p[1:]
                bare_dom = p[2:]
                if dot_dom not in expanded:
                    expanded.append(dot_dom)
                if bare_dom not in expanded:
                    expanded.append(bare_dom)
        for known in (
            ".gelirler.gov.tr",
            "gelirler.gov.tr",
            ".gib.gov.tr",
            "gib.gov.tr",
            ".gelbim.gov.tr",
            "gelbim.gov.tr",
            "localhost",
            "127.0.0.1",
        ):
            if known not in expanded:
                expanded.append(known)
        os.environ[env_var] = ",".join(expanded)


_normalize_no_proxy()

# ---------------------------------------------------------------------------
# Encryption key for Jira connection passwords (must be kept secret)
# ---------------------------------------------------------------------------
def _get_encryption_key():
    val = os.environ.get("ENCRYPTION_KEY") or os.environ.get("DJANGO_ENCRYPTION_KEY")
    if val:
        return val
    import base64
    import hashlib
    digest = hashlib.sha256(SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode()


ENCRYPTION_KEY = _get_encryption_key()
os.environ["ENCRYPTION_KEY"] = ENCRYPTION_KEY
os.environ["DJANGO_ENCRYPTION_KEY"] = ENCRYPTION_KEY

# ---------------------------------------------------------------------------
# Static and Media files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
