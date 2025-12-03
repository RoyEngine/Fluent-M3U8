# coding:utf-8
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
)
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton, InfoBar, InfoBarPosition

from ..components.interface import Interface
from ..service.localization_service import JarLocalizationSource, LocalizationService, LocalizationVariant


class LocalizationInheritanceInterface(Interface):
    """Interface for inspecting and packaging localization jars."""

    VIEW_MODES = (
        "Raw lines",
        "Quoted lines",
        "Quoted lines with values",
    )

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setTitle(self.tr("Localization inheritance"))

        self.sourceList = QListWidget(self)
        self.outputLineEdit = LineEdit(self)
        self.variantCombos: List[ComboBox] = [ComboBox(self), ComboBox(self), ComboBox(self)]
        self.viewModeCombo = ComboBox(self)
        self.viewers: List[QPlainTextEdit] = [QPlainTextEdit(self), QPlainTextEdit(self), QPlainTextEdit(self)]

        self._sources: List[JarLocalizationSource] = []
        self._current: Optional[JarLocalizationSource] = None
        self._scroll_sync = False

        self._init_widgets()

    def _init_widgets(self):
        controlsRow = QHBoxLayout()
        addJarButton = PrimaryPushButton(self.tr("Add JAR"), self)
        addFolderButton = QPushButton(self.tr("Add folder"), self)
        packageButton = PrimaryPushButton(self.tr("Package JAR"), self)
        outputButton = QPushButton(self.tr("Output"), self)

        controlsRow.addWidget(addJarButton)
        controlsRow.addWidget(addFolderButton)
        controlsRow.addStretch(1)
        controlsRow.addWidget(QLabel(self.tr("Output target:"), self))
        controlsRow.addWidget(self.outputLineEdit)
        controlsRow.addWidget(outputButton)
        controlsRow.addWidget(packageButton)

        self.viewModeCombo.addItems(self.VIEW_MODES)
        viewModeRow = QHBoxLayout()
        viewModeRow.addWidget(QLabel(self.tr("View mode:"), self))
        viewModeRow.addWidget(self.viewModeCombo)
        viewModeRow.addStretch(1)

        selectionRow = QHBoxLayout()
        for combo in self.variantCombos:
            selectionRow.addWidget(combo)
        selectionRow.addStretch(1)

        viewerRow = QHBoxLayout()
        for viewer in self.viewers:
            viewer.setPlaceholderText(self.tr("No language selected"))
            viewer.setLineWrapMode(QPlainTextEdit.NoWrap)
            viewer.setTabStopDistance(16)
            viewer.verticalScrollBar().valueChanged.connect(self._sync_scrollbars)
            viewerRow.addWidget(viewer)

        self.vBoxLayout.addLayout(controlsRow)
        self.vBoxLayout.addWidget(QLabel(self.tr("Loaded sources"), self))
        self.vBoxLayout.addWidget(self.sourceList)
        self.vBoxLayout.addLayout(viewModeRow)
        self.vBoxLayout.addLayout(selectionRow)
        self.vBoxLayout.addLayout(viewerRow)

        addJarButton.clicked.connect(self._choose_jars)
        addFolderButton.clicked.connect(self._choose_folder)
        outputButton.clicked.connect(self._choose_output)
        packageButton.clicked.connect(self._package_current)
        self.sourceList.currentItemChanged.connect(self._on_source_selected)
        self.viewModeCombo.currentIndexChanged.connect(self._refresh_viewers)
        for combo in self.variantCombos:
            combo.currentIndexChanged.connect(self._refresh_viewers)

    def _choose_jars(self):
        files, _ = QFileDialog.getOpenFileNames(self, self.tr("Select JARs"), "", "JAR Files (*.jar)")
        self._load_sources([Path(f) for f in files])

    def _choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, self.tr("Select folder"))
        if directory:
            self._load_sources([Path(directory)])

    def _choose_output(self):
        directory = QFileDialog.getExistingDirectory(self, self.tr("Select output directory"))
        if directory:
            self.outputLineEdit.setText(directory)

    def _load_sources(self, paths: List[Path]):
        if not paths:
            return

        sources = LocalizationService.collect_sources(paths)
        if not sources:
            InfoBar.warning(
                self.tr("No jars"),
                self.tr("No JAR files were found in the provided location."),
                duration=5000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )
            return

        self._sources.extend(sources)
        for source in sources:
            item = QListWidgetItem(f"{source.display_name} ({source.jar_path.name})")
            item.setData(Qt.ItemDataRole.UserRole, source)
            self.sourceList.addItem(item)

        if sources:
            self.sourceList.setCurrentRow(self.sourceList.count() - len(sources))

    def _on_source_selected(self, current: QListWidgetItem):
        source = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._current = source
        self._populate_variants(source)
        self._refresh_viewers()

    def _populate_variants(self, source: Optional[JarLocalizationSource]):
        for combo in self.variantCombos:
            combo.clear()

        if not source:
            return

        for combo in self.variantCombos:
            combo.addItem(self.tr("Select language"), None)
            for variant in source.variants:
                combo.addItem(variant.name, variant)

        for index, combo in enumerate(self.variantCombos):
            if index < len(source.variants):
                combo.setCurrentIndex(index + 1)

    def _refresh_viewers(self):
        mode = self.viewModeCombo.currentIndex()
        for combo, viewer in zip(self.variantCombos, self.viewers):
            variant: Optional[LocalizationVariant] = combo.currentData()
            viewer.clear()
            if variant:
                viewer.setPlainText(self._apply_mode(variant.content, mode))
            viewer.moveCursor(viewer.textCursor().Start)

    def _apply_mode(self, content: str, mode_index: int) -> str:
        lines = content.splitlines()
        if mode_index == 1:
            lines = [line for line in lines if '"' in line]
        elif mode_index == 2:
            lines = [line for line in lines if ('"' in line or ":" in line)]
        return "\n".join(lines)

    def _sync_scrollbars(self, value: int):
        if self._scroll_sync:
            return

        sender = self.sender()
        try:
            index = self.viewers.index(sender)
        except ValueError:
            return

        self._scroll_sync = True
        for i, viewer in enumerate(self.viewers):
            if i != index:
                viewer.verticalScrollBar().setValue(value)
        self._scroll_sync = False

    def _package_current(self):
        if not self._current:
            return

        target = self.outputLineEdit.text().strip()
        if not target:
            InfoBar.error(
                self.tr("Missing output"),
                self.tr("Please choose an output directory before packaging."),
                duration=5000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )
            return

        updates: Dict[str, str] = {}
        for combo, viewer in zip(self.variantCombos, self.viewers):
            variant: Optional[LocalizationVariant] = combo.currentData()
            if variant:
                updates[variant.archive_path] = viewer.toPlainText()

        output_path = LocalizationService.repack_with_translations(
            self._current, Path(target), updates
        )
        InfoBar.success(
            self.tr("Packaged"),
            self.tr("JAR written to {0}").format(str(output_path)),
            duration=5000,
            position=InfoBarPosition.BOTTOM,
            parent=self,
        )
