"""
Django settings for qualidade_project project.

Generated by 'django-admin startproject' using Django 4.0.1.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.0/ref/settings/
"""

from pathlib import Path
import environ
import os
import certifi, os

# from .mongo_api import conect_mongo_db

env = environ.Env()
environ.Env.read_env()

os.environ["SSL_CERT_FILE"] = certifi.where()

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")
FARMBOX_ID = env("FARM_API")
MONGO_PASS_DEFENSIVOS = env("MONGO_PASS_DEFENSIVOS")
PROTHEUS_TOKEN = env("PROTHEUS_TOKEN")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG_ENV = env("DEBUG")
if DEBUG_ENV == "1":
    DEBUG = True
if DEBUG_ENV == "0":
    DEBUG = False
print('DEBUG', DEBUG)

ALLOWED_HOSTS = ["*"]


# Application definition

CORS_ALLOW_ALL_ORIGINS = True


INSTALLED_APPS = [
    # General use templates & template tags (should appear first)
    "adminlte3",
    # Optional: Django admin theme (must be before django.contrib.admin)
    "adminlte3_theme",
    # "admin_material.apps.AdminMaterialDashboardConfig",  # <-- NEW
    "admin_confirm",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_crontab",
    "django_apscheduler",
    # "diamante.apps.DiamanteConfig",
    "csvexport",
    "debug_toolbar",
    "django_json_widget",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "usuario",
    "diamante",
    "admin_extra_buttons",
    "crispy_forms",
    "crispy_bootstrap4",
    "storages",
    "aviacao",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


CSRF_TRUSTED_ORIGINS = [
    "https://diamante-quality.up.railway.app",
    "http://localhost:3000",
    "https://diamanteubs.netlify.app",
]

ROOT_URLCONF = "qualidade_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "qualidade_project.wsgi.application"

# EMAIL CONFIG

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'patamarcelo@gmail.com'
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD_CONFIG")


# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases

DATABASES = {
    "default": {
        'ENGINE': 'dj_db_conn_pool.backends.postgresql',
        "NAME": env("DB_EL_NAME"),
        "USER": env("DB_EL_USER"),
        "PASSWORD": env("DB_EL_PASSWORD"),
        "HOST": env("DB_EL_HOST"),
        "PORT": env("DB_EL_PORT"),
        'POOL_OPTIONS': {
            'POOL_SIZE': 20,            # Number of connections in the pool
            'MAX_OVERFLOW': 10,         # Extra connections beyond the pool size
            'RECYCLE': 1800,            # Recycle connections after a certain time to avoid stale connections
            'PRE_PING': True,           # Check connections before using them to avoid using a broken connection
        }
    },
    "dev": {
        'ENGINE': 'dj_db_conn_pool.backends.postgresql',
        "NAME": env("DB_EL_NAME_LOCAL"),
        "USER": env("DB_EL_USER_LOCAL"),
        "PASSWORD": env("DB_EL_PASSWORD_LOCAL"),
        "HOST": env("DB_EL_HOST_LOCAL"),
        "PORT": env("DB_EL_PORT_LOCAL"),
        'POOL_OPTIONS': {
            'POOL_SIZE': 20,            # Number of connections in the pool
            'MAX_OVERFLOW': 10,         # Extra connections beyond the pool size
            'RECYCLE': 1800,            # Recycle connections after a certain time to avoid stale connections
            'PRE_PING': True,           # Check connections before using them to avoid using a broken connection
        }
    },
}

DATABASES["default"] = DATABASES["default" if DEBUG else "default"]


# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/


LOGOUT_REDIRECT_URL = "index"
LOGIN_URL = "index"


THOUSAND_SEPARATOR = (".",)

USE_THOUSAND_SEPARATOR = True

LANGUAGE_CODE = "pt-br"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_L10N = True

USE_TZ = False


AUTH_USER_MODEL = "usuario.CustomUsuario"


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

# STATIC_URL = "static/"

STATIC_URL = "/static/"
# STATIC_ROOT = os.path.join(BASE_DIR, "static")

# DEFAULT_FILE_STORAGE = "storages.backends.dropbox.DropBoxStorage"
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.dropbox.DropboxStorage",
        "OPTIONS": {},
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DROPBOX_ROOT_PATH = "/"


DROPBOX_OAUTH2_REFRESH_TOKEN = env("DROPBOX_OAUTH2_REFRESH_TOKEN", default="")
DROPBOX_APP_SECRET = env("DROPBOX_APP_SECRET", default="")
DROPBOX_APP_KEY = env("DROPBOX_APP_KEY", default="")


MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media/")
# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


REST_AUTH_SERIALIZERS = {
    "USER_DETAILS_SERIALIZER": "path.to.custom.UserSerializer",
}

STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
# STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"


INTERNAL_IPS = [
    "127.0.0.1",
]

CRISPY_TEMPLATE_PACK = "bootstrap4"

CRONJOBS = [
    ('* * * * *', 'diamante.cron.get_hour_test')
]
