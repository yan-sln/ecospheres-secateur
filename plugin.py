import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .ui.panel import SecateurPanel


class Plugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.panel = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "Ecosphères Secateur", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_panel)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Ecosphères Secateur", self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("Ecosphères Secateur", self.action)
        if self.panel:
            self.iface.removeDockWidget(self.panel)
            self.panel.deleteLater()
            self.panel = None

    def _toggle_panel(self, checked):
        if self.panel is None:
            self.panel = SecateurPanel(self.iface)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.panel)
            self.panel.visibilityChanged.connect(self.action.setChecked)
        if checked:
            self.panel.show()
        else:
            self.panel.hide()
