import os

from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core.utils import get_icon_path


class SettingsManager:
    """
    Gestion centralisée des paramètres du plugin.

    - Source unique de vérité
    - Encapsulation de QgsSettings
    - API typée et explicite
    """

    BASE_KEY = "secateur"
    DEFAULT_LOGO = "PREF_Cote_d_Or_CMJN_295_432px_Marianne.jpg"

    def __init__(self):
        self._settings = QgsSettings()

    # ~~~~~~~~~~~~~~~ author ~~~~~~~~~~~~~~~#
    @property
    def author(self) -> str:
        return self._settings.value(f"{self.BASE_KEY}/author", "DDT")

    @author.setter
    def author(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("L'autheur ne peut pas être vide")
        self._settings.setValue(f"{self.BASE_KEY}/author", value.strip())

    # ~~~~~~~~~~~~~ pdf title ~~~~~~~~~~~~~~#
    @property
    def pdf_title(self) -> str:
        return self._settings.value(f"{self.BASE_KEY}/pdf_title", "Rapport")

    @pdf_title.setter
    def pdf_title(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("Le titre ne peut pas être vide")
        self._settings.setValue(f"{self.BASE_KEY}/pdf_title", value.strip())

    # ~~~~~~~~~~~~~~~ logo ~~~~~~~~~~~~~~~~#
    @property
    def logo_path(self) -> str:
        path = self._settings.value(f"{self.BASE_KEY}/logo_path", "")
        if path:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Logo introuvable : {path}")
            return path

        default_path = get_icon_path(self.DEFAULT_LOGO)

        if not default_path or not os.path.exists(default_path):
            raise ValueError("Logo par défaut introuvable dans les ressources")

        return default_path

    @logo_path.setter
    def logo_path(self, value: str) -> None:
        if value and not os.path.exists(value):
            raise ValueError(f"Chemin logo invalide : {value}")

        self._settings.setValue(f"{self.BASE_KEY}/logo_path", value)


class SettingsDialog(QDialog):
    def __init__(self, settings, image_manager, parent=None):
        super().__init__(parent)

        self.settings = settings
        self.image_manager = image_manager

        self.setWindowTitle("Paramètres")

        layout = QVBoxLayout(self)

        # ───────── Auteur ─────────
        layout.addWidget(QLabel("Auteur :"))
        self.author_input = QLineEdit(self.settings.author)
        layout.addWidget(self.author_input)

        # ───────── Logo ─────────
        layout.addWidget(QLabel("Logo :"))

        row = QHBoxLayout()

        self.logo_label = QLabel(self._display_logo_name(self.settings.logo_path))
        row.addWidget(self.logo_label)

        self.logo_button = QPushButton("Choisir…")
        self.logo_button.clicked.connect(self._select_logo)
        row.addWidget(self.logo_button)

        layout.addLayout(row)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self._selected_logo = None

    def _select_logo(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir un logo",
            "",
            "Images (*.png *.jpg *.jpeg *.svg)",
        )

        if not file_path:
            return

        try:
            self.image_manager.validate_image(file_path)
            self._selected_logo = file_path
            self.logo_label.setStyleSheet("")
            self.logo_label.setText(self._display_logo_name(file_path))

        except Exception as err:
            self.logo_label.setStyleSheet("color: red;")
            self.logo_label.setText(f"{str(err)}")
            self._selected_logo = None

    def get_values(self):
        return {
            "author": self.author_input.text().strip(),
            "logo": self._selected_logo,
        }

    def _display_logo_name(self, path):
        return path.split("/")[-1] if path else "Aucun logo"
