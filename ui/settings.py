from qgis.core import QgsSettings


class SettingsManager:
    """
    Gestion centralisée des paramètres du plugin.

    - Source unique de vérité
    - Encapsulation de QgsSettings
    - API typée et explicite
    """

    BASE_KEY = "secateur"

    def __init__(self):
        self._settings = QgsSettings()

    # ──────────────────────────────────────────────
    # Author
    # ──────────────────────────────────────────────

    @property
    def author(self) -> str:
        return self._settings.value(f"{self.BASE_KEY}/author", "DDT")

    @author.setter
    def author(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("Author cannot be empty")
        self._settings.setValue(f"{self.BASE_KEY}/author", value.strip())
