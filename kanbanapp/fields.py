"""Custom reusable fields for kanbanapp."""
from django.db.models import TextField
from django.core.validators import MaxValueValidator, MinValueValidator


class EncryptedCharField(TextField):
    """A TextField that stores its value encrypted with Fernet.

    The encryption key comes from ``settings.ENCRYPTION_KEY`` (a Fernet key).
    """

    def __init__(self, *args, **kwargs):
        self._key = kwargs.pop("key", None)
        super().__init__(*args, **kwargs)

    @property
    def _fernet(self):
        from cryptography.fernet import Fernet

        if self._key is None:
            self._key = getattr(
                __import__("django").settings, "ENCRYPTION_KEY", ""
            )
        return Fernet(self._key.encode() if isinstance(self._key, str) else self._key)

    def get_prep_value(self, value):
        # Encrypt before saving; decrypt on read.
        if value is not None:
            return self._fernet.encrypt(str(value).encode()).decode()
        return value

    def to_python(self, value):
        if value is None or value == "":
            return value
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except Exception:
            return value
