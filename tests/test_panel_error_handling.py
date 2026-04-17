import builtins
import importlib
import types
from unittest import mock

# Stub ApiError similar to the real one
class ApiError(Exception):
    def __init__(self, message="API error", retryable=False):
        super().__init__(message)
        self.retryable = retryable

    def to_user_friendly_message(self):
        return "Message utilisateur"

# Helper to create a minimal Panel-like object with the decorator from panel.py
def get_panel_class():
    # Mock the heavy QGIS imports before importing the module
    mock_qgis = types.SimpleNamespace(
        core=types.SimpleNamespace(
            QgsLayerTreeGroup=object,
            QgsPalLayerSettings=object,
            QgsProject=object,
            QgsTextBufferSettings=object,
            QgsTextFormat=object,
            QgsVectorLayerSimpleLabeling=object,
        ),
        PyQt=types.SimpleNamespace(
            QtCore=types.SimpleNamespace(QStringListModel=object, Qt=object, QTimer=object),
            QtGui=types.SimpleNamespace(QFont=object),
            QtWidgets=types.SimpleNamespace(
                QComboBox=object,
                QCompleter=object,
                QDockWidget=object,
                QHBoxLayout=object,
                QLabel=lambda *a, **kw: types.SimpleNamespace(setText=lambda txt: None, setWordWrap=lambda b: None),
                QLineEdit=object,
                QProgressBar=object,
                QPushButton=object,
                QVBoxLayout=object,
                QWidget=object,
            ),
        ),
    )
    # Insert mocks into sys.modules
    with mock.patch.dict('sys.modules', {
        'qgis': mock_qgis,
        'qgis.core': mock_qgis.core,
        'qgis.PyQt.QtCore': mock_qgis.PyQt.QtCore,
        'qgis.PyQt.QtGui': mock_qgis.PyQt.QtGui,
        'qgis.PyQt.QtWidgets': mock_qgis.PyQt.QtWidgets,
    }):
        # Import the module under test
        import ui.panel as panel_mod
        importlib.reload(panel_mod)
        return panel_mod.CadreurPanel

# Dummy status label to capture setText calls
class DummyLabel:
    def __init__(self):
        self.texts = []
    def setText(self, txt):
        self.texts.append(txt)
    def setWordWrap(self, b):
        pass

# Minimal dummy iface required by CadreurPanel init (only mainWindow used)
class DummyIface:
    def mainWindow(self):
        return None

# Fixture to create a panel instance with mocked dependencies
import pytest

@pytest.fixture
def panel():
    CadreurPanel = get_panel_class()
    # Patch the methods from core.entities_selector that the panel uses
    with mock.patch('ui.panel.search_communes', return_value=[{"name": "CommuneA", "code": "001"}]),
         mock.patch('ui.panel.list_sections', return_value=[{"section": "S1"}]),
         mock.patch('ui.panel.list_parcelles', return_value=[{"section": "S1", "numero": "P1"}]),
         mock.patch('ui.panel.fetch_entity_geometry', return_value=types.SimpleNamespace(isEmpty=lambda: False)):
        p = CadreurPanel(DummyIface())
        # Replace status_label with our dummy to capture messages
        p.status_label = DummyLabel()
        return p

def test_search_communes_success(panel):
    result = panel._search_communes("test")
    assert result == [{"name": "CommuneA", "code": "001"}]
    # No error flag should be set
    assert not panel._last_api_error_occurred

def test_search_communes_error(panel):
    # Make the underlying function raise ApiError
    with mock.patch('ui.panel.search_communes', side_effect=ApiError(retryable=True)):
        result = panel._search_communes("test")
        # Fallback defined in decorator is []
        assert result == []
        assert panel._last_api_error_occurred
        assert panel._last_api_error_retryable
        # UI should have been updated with user friendly message
        assert panel.status_label.texts[-1] == "Message utilisateur"

def test_load_sections_error(panel):
    # Force fetch_sections to raise ApiError
    with mock.patch('ui.panel.list_sections', side_effect=ApiError()):
        panel._selected_code = "001"
        panel._load_sections()
        # Sections list should be empty and error flag set
        assert panel._sections == []
        assert panel._last_api_error_occurred
        # UI message should be set by decorator (fallback [] triggers no explicit UI change here)
        # The status_label is not directly updated in _load_sections on error, only flag matters

def test_get_geometry_error(panel):
    # fetch_entity_geometry raises ApiError, decorator configured with update_ui=False
    with mock.patch('ui.panel.fetch_entity_geometry', side_effect=ApiError()):
        result = panel._get_geometry(object())
        assert result is None
        assert panel._last_api_error_occurred
        # No UI update expected because update_ui=False, label texts unchanged
        assert panel.status_label.texts == []

def test_load_parcelles_error(panel):
    # Simulate error in list_parcelles
    with mock.patch('ui.panel.list_parcelles', side_effect=ApiError()):
        panel._selected_code = "001"
        panel._selected_section = "S1"
        panel._load_parcelles()
        assert panel._parcelles == []
        assert panel._last_api_error_occurred
        # UI not directly changed in this path

def test_section_loop_error_handling(panel):
    # Simulate ApiError for one section geometry fetch, then normal geometry for another
    sections = [types.SimpleNamespace(section="S1"), types.SimpleNamespace(section="S2")]
    panel._sections = sections
    panel._selected_code = "001"
    # First call raises, second returns valid geometry
    def side_effect(obj):
        if obj.section == "S1":
            raise ApiError()
        return types.SimpleNamespace(isEmpty=lambda: False)
    with mock.patch('ui.panel.fetch_entity_geometry', side_effect=side_effect):
        # Run the internal loop manually by invoking _on_show_sections which uses the same logic
        panel._on_show_sections()
        # After processing, error flag should be set due to the first ApiError
        assert panel._last_api_error_occurred
        # Status label should contain an error message for the failed section
        assert any("Erreur API pour la section" in txt for txt in panel.status_label.texts)

# Additional tests could be added for parcel loop similarly.
