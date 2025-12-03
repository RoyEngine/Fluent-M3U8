# coding: utf-8
import sys

from PySide6.QtCore import QUrl, QSize, Qt, QLocale
from PySide6.QtGui import QIcon, QColor, QGuiApplication
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtSql import QSqlDatabase

from qfluentwidgets import NavigationItemPosition, MSFluentWindow, SplashScreen, MessageBox, InfoBarIcon
from qfluentwidgets import FluentIcon as FIF

from .setting_interface import SettingInterface
from .home_interface import HomeInterface
from .task_interface import TaskInterface
from .localization_inheritance_interface import LocalizationInheritanceInterface
from ..common.database import DBInitializer, DatabaseThread, sqlSignalBus, SqlResponse
from ..common.config import cfg
from ..common.icon import Icon, Logo
from ..common.utils import openUrl
from ..common.concurrent import TaskExecutor
from ..service.version_service import VersionService
from ..common.signal_bus import signalBus
from ..common.setting import DOC_URL, FEEDBACK_URL, RELEASE_URL, AFDIAN_URL, VIDEO_URL, KOFI_URL
from ..service.m3u8dl_service import m3u8Service, Task
from ..components.system_tray_icon import SystemTrayIcon
from ..components.menu_bar import MenuBar
from ..common import resource


class MainWindow(MSFluentWindow):

    def __init__(self):
        super().__init__()

        self.initDatabase()
        self.initWindow()

        self.versionManager = VersionService()

        self.homeInterface = HomeInterface(self)
        self.taskInterface = TaskInterface(self)
        self.settingInterface = SettingInterface(self)
        self.localizationInterface = LocalizationInheritanceInterface(self)
        self.systemTrayIcon = SystemTrayIcon(self)

        self.connectSignalToSlot()

        # add items to navigation interface
        self.initMenuBar()
        self.initNavigation()

        # check for updates
        self.onInitFinished()

    def connectSignalToSlot(self):
        signalBus.micaEnableChanged.connect(self.setMicaEffectEnabled)
        signalBus.switchToTaskInterfaceSig.connect(self.onSwitchToTaskInterface)
        signalBus.appErrorSig.connect(self.onAppError)
        signalBus.appMessageSig.connect(self.onAppMessage)
        signalBus.checkUpdateSig.connect(self.checkUpdate)

        m3u8Service.downloadFinished.connect(self.onDownloadFinished)

        self.systemTrayIcon.messageClicked.connect(self.onSystemTrayMessageClicked)

    def initNavigation(self):
        self.addSubInterface(self.homeInterface, FIF.HOME, self.tr('Home'), FIF.HOME_FILL, isTransparent=True)
        self.addSubInterface(
            self.localizationInterface, Logo.GLOBE, self.tr('Localization'), Logo.GLOBE, isTransparent=True)
        self.addSubInterface(self.taskInterface, Icon.CLOUD_DOWNLOAD, self.tr('Task'), Icon.CLOUD_DOWNLOAD_FILLED)

        self.navigationInterface.addItem(
            'sponsor', FIF.HEART, self.tr("Sponsor"), self.support, False, position=NavigationItemPosition.BOTTOM)
        self.addSubInterface(
            self.settingInterface, Icon.SETTINGS, self.tr('Settings'), Icon.SETTINGS_FILLED, NavigationItemPosition.BOTTOM)

    def initWindow(self):
        self.resize(960, 754 if sys.platform == "win32" else 773)
        self.setMinimumWidth(760)
        self.setWindowIcon(QIcon(':/app/images/logo.png'))
        self.setWindowTitle('Fluent M3U8')
        QApplication.setQuitOnLastWindowClosed(False)

        self.setCustomBackgroundColor(QColor(240, 244, 249), QColor(32, 32, 32))
        self.setMicaEffectEnabled(False)

        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)
        self.show()
        QApplication.processEvents()

    def initDatabase(self):
        """ initialize song library """
        DBInitializer.init()

        self.databaseThread = DatabaseThread(
            QSqlDatabase.database(DBInitializer.CONNECTION_NAME), self)

        sqlSignalBus.dataFetched.connect(self.onDataFetched)

    def initMenuBar(self):
        if sys.platform != "darwin":
            return

        self.menuBar = MenuBar(self)
        self.menuBar.openFileAct.triggered.connect(self.openFile)
        self.menuBar.closeWindowAct.triggered.connect(self.close)
        self.menuBar.donateAct.triggered.connect(self.support)
        self.menuBar.docAct.triggered.connect(lambda: openUrl(DOC_URL))
        self.menuBar.settingsAct.triggered.connect(lambda: self.switchTo(self.settingInterface))
        self.menuBar.videoTutorialAct.triggered.connect(lambda: openUrl(VIDEO_URL))
        self.menuBar.feedbackAct.triggered.connect(lambda: openUrl(FEEDBACK_URL))

    def onDataFetched(self, response: SqlResponse):
        if response.slot:
            response.slot(response.data)

    def onAppError(self, message: str):
        """ app error slot """
        QApplication.clipboard().setText(message)
        self.showMessageBox(
            self.tr("Unhandled exception occurred"),
            self.tr("The error message has been written to the paste board and log. Do you want to report?"),
            True,
            lambda: openUrl(FEEDBACK_URL)
        )

    def onAppMessage(self, message: str):
        if message == "show":
            if self.windowState() & Qt.WindowMinimized:
                self.showNormal()
            else:
                self.show()
                self.raise_()
        else:
            # TODO: parse command line args

            self.switchTo(self.homeInterface)
            self.show()

    def showMessageBox(self, title: str, content: str, showYesButton=False, yesSlot=None):
        """ show message box """
        w = MessageBox(title, content, self)
        if not showYesButton:
            w.cancelButton.setText(self.tr('Close'))
            w.yesButton.hide()
            w.buttonLayout.insertStretch(0, 1)

        if w.exec() and yesSlot is not None:
            yesSlot()

    def checkUpdate(self, ignore=False):
        """ check software update

        Parameters
        ----------
        ignore: bool
            ignore message box when no updates are available
        """
        TaskExecutor.runTask(self.versionManager.hasNewVersion).then(
            lambda success: self.onVersionInfoFetched(success, ignore))

    def onVersionInfoFetched(self, success, ignore=False):
        if success:
            self.showMessageBox(
                self.tr('Updates available'),
                self.tr('A new version')+f" {self.versionManager.lastestVersion} " +self.tr('is available. Do you want to download this version?'),
                True,
                lambda: openUrl(RELEASE_URL)
            )
        elif not ignore:
            self.showMessageBox(
                self.tr('No updates available'),
                self.tr(
                    'Fluent M3U8 has been updated to the latest version, feel free to use it.'),
            )

    def onDownloadFinished(self, task: Task, success: bool, errorMsg: str):
        if success:
            self.systemTrayIcon.showMessage(
                self.tr("Task finished"),
                f'"{task.fileName}"' + self.tr("download successfully"),
                InfoBarIcon.SUCCESS.icon()
            )
        else:
            content = f'"{task.fileName}"' + self.tr("download failed")
            if errorMsg:
                content += (": " + errorMsg)

            self.systemTrayIcon.showMessage(self.tr("Task failed"), content, InfoBarIcon.ERROR.icon())

    def onSystemTrayMessageClicked(self):
        self.switchTo(self.taskInterface)
        self.taskInterface.stackedWidget.setCurrentIndex(1)

    def onSwitchToTaskInterface(self):
        self.taskInterface.stackedWidget.setCurrentIndex(0)
        self.switchTo(self.taskInterface)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'splashScreen'):
            self.splashScreen.resize(self.size())

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def onInitFinished(self):
        self.splashScreen.finish()
        self.systemTrayIcon.show()

        if cfg.get(cfg.checkUpdateAtStartUp):
            self.checkUpdate(True)

    def support(self):
        language = cfg.get(cfg.language).value
        if language.name() == "zh_CN":
            openUrl(AFDIAN_URL)
        else:
            openUrl(KOFI_URL)

    def openFile(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Open File"), cfg.get(
            cfg.saveFolder), "Text Files (*.txt);;M3U8 Files (*.m3u8,*.m3u);;MPD Files (*.mpd)")
        if not path:
            return

        self.homeInterface.setDownloadLink(path)
        self.switchTo(self.homeInterface)

    def onExit(self):
        """ exit main window """
        self.systemTrayIcon.hide()

        # clear tasks
        m3u8Service.clearTasks()

        # close database
        QSqlDatabase.database(DBInitializer.CONNECTION_NAME).close()
        QSqlDatabase.removeDatabase(DBInitializer.CONNECTION_NAME)