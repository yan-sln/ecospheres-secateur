import os
import shutil
from PyQt5.QtCore import Qt
from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QImage

class ImageManager:
    MAX_WIDTH = 2000
    MAX_HEIGHT = 2000

    TARGET_RATIO = 295 / 432
    RATIO_TOLERANCE = 0.15

    def validate_image(self, path: str) -> QImage:
        img = QImage(path)

        if img.isNull():
            raise ValueError("Image invalide")

        if img.width() > self.MAX_WIDTH or img.height() > self.MAX_HEIGHT:
            raise ValueError("Image trop grande")

        ratio = img.width() / img.height()
        if abs(ratio - self.TARGET_RATIO) > self.RATIO_TOLERANCE:
            raise ValueError(
                f"Ratio image incorrect (attendu ~{self.TARGET_RATIO:.2f}, obtenu {ratio:.2f})"
            )

        return img
    
    def normalize_image(self, path: str, output_path: str) -> str:
        img = self.validate_image(path)

        target_w, target_h = 295, 432

        resized = img.scaled(
            target_w,
            target_h,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )

        resized.save(output_path)
        return output_path

    @staticmethod
    def copy_to_local(path: str) -> str:
        base_dir = QgsApplication.qgisSettingsDirPath()
        dest_dir = os.path.join(base_dir, "secateur")

        os.makedirs(dest_dir, exist_ok=True)

        _, ext = os.path.splitext(path)
        dest_path = os.path.join(dest_dir, f"logo{ext}")

        shutil.copyfile(path, dest_path)

        return dest_path
    
    def safe_import_logo(self, path: str) -> str:
        self.validate_image(path)
        return self.copy_to_local(path)