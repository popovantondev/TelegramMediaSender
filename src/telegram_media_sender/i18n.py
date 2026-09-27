"""Small built-in translation catalog for the desktop interface."""
from __future__ import annotations

import re
import subprocess
import sys

from PySide6.QtCore import QLocale

LANGUAGES = ("de", "ru", "en")
LANGUAGE_LABELS = {"de": "Deutsch", "ru": "Русский", "en": "English"}

# Russian source strings are stable translation keys; all displayed prose lives here.
CATALOG = {
    "View diagnostics log…": ("Diagnoseprotokoll ansehen…", "Открыть журнал диагностики…", "View diagnostics log…"),
    "Could not open diagnostics log": ("Diagnoseprotokoll konnte nicht geöffnet werden", "Не удалось открыть журнал диагностики", "Could not open diagnostics log"),
    "Select media groups": ("Medienpakete auswählen", "Выберите медиакомплекты", "Select media groups"),
    'Source folder': ('Quellordner', 'Папка с материалами', 'Source folder'),
    'Choose folder…': ('Ordner wählen…', 'Выбрать папку…', 'Choose folder…'),
    'Choose a folder to see its media groups.': ('Wählen Sie einen Ordner, um seine Medienpakete anzuzeigen.', 'Выберите папку — здесь появятся медиакомплекты.', 'Choose a folder to see its media groups.'),
    'Choose a folder to see its weeks and days.': ('Wählen Sie einen Ordner, um seine Wochen und Tage anzuzeigen.', 'Выберите папку — здесь появятся недели и дни.', 'Choose a folder to see its weeks and days.'),
    'No profiles yet. Add a Telegram profile to get started.': ('Noch keine Profile. Fügen Sie ein Telegram-Profil hinzu.', 'Профилей пока нет. Добавьте профиль Telegram, чтобы начать.', 'No profiles yet. Add a Telegram profile to get started.'),
    'Selected: {selection} · {size}': ('Ausgewählt: {selection} · {size}', 'Выбрано: {selection} · {size}', 'Selected: {selection} · {size}'),
    'To send: {messages}, {files}, {size}': ('Zum Senden: {messages}, {files}, {size}', 'К отправке: {messages}, {files}, {size}', 'To send: {messages}, {files}, {size}'),
    '<b>Profile:</b> {profile} · <b>Chat:</b> {chat} · <b>Selected:</b> {selection}': ('<b>Profil:</b> {profile} · <b>Chat:</b> {chat} · <b>Ausgewählt:</b> {selection}', '<b>Профиль:</b> {profile} · <b>Чат:</b> {chat} · <b>Выбрано:</b> {selection}', '<b>Profile:</b> {profile} · <b>Chat:</b> {chat} · <b>Selected:</b> {selection}'),

    "Telegram Media Sender": ("Medien an Telegram senden", "Отправка медиа в Telegram", "Telegram Media Sender"),
    "Select a recipient, a folder, and send media groups": ("Empfänger und Ordner wählen und Medienpakete senden", "Выберите получателя, папку и отправьте медиакомплекты", "Choose a recipient and folder, then send media groups"),
    "Where to send": ("Empfänger", "Куда отправить", "Where to send"),
    "Refresh": ("Aktualisieren", "Обновить", "Refresh"),
    "Telegram account": ("Telegram-Konto", "Аккаунт Telegram", "Telegram account"),
    "Add profile…": ("Profil hinzufügen…", "Добавить профиль…", "Add profile…"),
    "Media group folder": ("Ordner mit Medienpaketen", "Папка с комплектами", "Media group folder"),
    "No folder selected": ("Kein Ordner ausgewählt", "Папка не выбрана", "No folder selected"),
    "Choose…": ("Auswählen…", "Выбрать…", "Choose…"),
    "No groups found": ("Keine Pakete gefunden", "Комплекты не найдены", "No groups found"),
    "Select all": ("Alle auswählen", "Выбрать все", "Select all"),
    "Clear selection": ("Auswahl aufheben", "Снять выбор", "Clear selection"),
    "Selection": ("Auswahl", "Выбор", "Selection"),
    "Group name": ("Paketname", "Название комплекта", "Group name"),
    "Group files": ("Paketdateien", "Файлы комплекта", "Group files"),
    "Size and status": ("Größe und Status", "Размер и статус", "Size and status"),
    "Choose a folder and load the chat list.": ("Wählen Sie einen Ordner und laden Sie die Chatliste.", "Выберите папку и загрузите список чатов.", "Choose a folder and load the chat list."),
    "Ready to review the media groups.": ("Medienpakete können geprüft werden.", "Комплекты готовы к проверке.", "Media groups are ready for review."),
    "No complete media groups found.": ("Keine Medienpakete gefunden.", "Комплекты не найдены.", "No media groups found."),
    "Current file": ("Aktuelle Datei", "Текущий файл", "Current file"),
    "Media group": ("Medienpaket", "Комплект", "Media group"),
    "All uploads": ("Gesamter Upload", "Вся отправка", "All uploads"),
    "Send to Telegram": ("An Telegram senden", "Отправка в Telegram", "Send to Telegram"),
    "File: —": ("Datei: —", "Файл: —", "File: —"),
    "Group: —": ("Paket: —", "Комплект: —", "Group: —"),
    "Send": ("Senden", "Отправить", "Send"),
    "Send selected\ngroups": ("Auswahl\nsenden", "Отправить\nвыбранные", "Send selected\ngroups"),
    "Send selected media groups to Telegram": ("Ausgewählte Medienpakete an Telegram senden", "Отправить выбранные медиакомплекты в Telegram", "Send selected media groups to Telegram"),
    "Send selected groups": ("Ausgewählte Pakete senden", "Отправить выбранные комплекты", "Send selected groups"),
    "Cancel": ("Abbrechen", "Отменить", "Cancel"),
    "Stop the current operation": ("Aktuellen Vorgang stoppen", "Остановить текущую операцию", "Stop the current operation"),
    "Select a folder with video/audio and subtitles": ("Ordner mit Dateien auswählen", "Выберите папку с файлами", "Select a folder with files"),
    "Could not read the folder": ("Ordner konnte nicht gelesen werden", "Не удалось прочитать папку", "Could not read the folder"),
    "Incomplete groups skipped: ": ("Unvollständige Pakete übersprungen: ", "Неполные наборы пропущены: ", "Incomplete groups skipped: "),
    "; and ": ("; und ", "; и ещё ", "; and "),
    "Selected groups: {selected} of {total}": ("Ausgewählte Pakete: {selected} von {total}", "Выбрано комплектов: {selected} из {total}", "Selected groups: {selected} of {total}"),
    "Chats available for sending: {count}.": ("Chats mit Sendeberechtigung: {count}.", "Доступно чатов для отправки: {count}.", "Chats available for sending: {count}."),
    "No chats available with permission to send.": ("Keine Chats mit Sendeberechtigung verfügbar.", "Нет доступных чатов с правом отправки.", "No chats available with permission to send."),
    "Forum groups with topics are not supported yet: {count}.": ("Forengruppen mit Themen werden noch nicht unterstützt: {count}.", "Группы с темами пока не поддерживаются: {count}.", "Forum groups with topics are not supported yet: {count}."),
    "File exceeds the Telegram upload limit: {name} ({limit} MB).": ("Datei überschreitet das Telegram-Uploadlimit: {name} ({limit} MB).", "Файл превышает ограничение Telegram на загрузку: {name} ({limit} МБ).", "File exceeds the Telegram upload limit: {name} ({limit} MB)."),
    "Loading available chats…": ("Verfügbare Chats werden geladen…", "Загружаю доступные чаты…", "Loading available chats…"),
    "Add a Telegram profile before loading chats.": ("Fügen Sie ein Telegram-Profil hinzu, bevor Sie Chats laden.", "Добавьте профиль Telegram перед загрузкой чатов.", "Add a Telegram profile before loading chats."),
    "Connecting to Telegram…": ("Verbindung zu Telegram wird hergestellt…", "Подключаюсь к Telegram…", "Connecting to Telegram…"),
    "Upload cancelled by the user.": ("Upload vom Benutzer abgebrochen.", "Отправка остановлена пользователем.", "Upload cancelled by the user."),
    "Telegram code was not received.": ("Telegram-Code wurde nicht empfangen.", "Ввод кода Telegram не получен.", "Telegram code was not received."),
    "Telegram sign-in cancelled.": ("Telegram-Anmeldung abgebrochen.", "Вход в Telegram отменён.", "Telegram sign-in cancelled."),
    "Duplicate review was not received.": ("Prüfung auf Duplikate wurde nicht bestätigt.", "Подтверждение проверки дубликатов не получено.", "Duplicate review was not received."),
    "Fill in the API ID and API Hash in the profile.": ("Tragen Sie API-ID und API-Hash im Profil ein.", "Укажите API ID и API Hash в профиле.", "Fill in the API ID and API Hash in the profile."),
    "This local account needs a new sign-in. Add a profile to continue.": ("Dieses lokale Konto muss neu angemeldet werden. Fügen Sie ein Profil hinzu.", "Для этого локального аккаунта нужен новый вход. Добавьте профиль.", "This local account needs a new sign-in. Add a profile to continue."),
    "The profile has no phone number.": ("Im Profil fehlt die Telefonnummer.", "В профиле не указан телефон.", "The profile has no phone number."),
    "Telegram sign-in code": ("Telegram-Anmeldecode", "Код входа из Telegram", "Telegram sign-in code"),
    "Telegram two-step verification password": ("Telegram-Passwort für die Zwei-Schritt-Verifizierung", "Пароль двухэтапной проверки Telegram", "Telegram two-step verification password"),
    "Uploading media groups separately from the subtitle album.": ("Medien werden getrennt vom Untertitelalbum gesendet.", "Медиа отправлено отдельно от группового альбома субтитров.", "Media is sent separately from the subtitle album."),
    "Sent groups: {sent}\nSkipped duplicates: {skipped}\n{note}": ("Gesendete Pakete: {sent}\nÜbersprungene Duplikate: {skipped}\n{note}", "Отправлено комплектов: {sent}\nПропущено повторов: {skipped}\n{note}", "Groups sent: {sent}\nDuplicates skipped: {skipped}\n{note}"),
    "Sign in to Telegram": ("Bei Telegram anmelden", "Вход в Telegram", "Sign in to Telegram"),
    "Stage 1/3 · Connecting to Telegram": ("Schritt 1/3 · Verbindung zu Telegram", "Этап 1/3 · Подключение к Telegram", "Stage 1/3 · Connecting to Telegram"),
    "Stage 1/3 · Checking chat for duplicates": ("Schritt 1/3 · Chat auf Duplikate prüfen", "Этап 1/3 · Проверка чата на повторы", "Stage 1/3 · Checking chat for duplicates"),
    "Upload stopped. Review the matching groups.": ("Upload gestoppt. Prüfen Sie die übereinstimmenden Pakete.", "Отправка остановлена — проверьте совпавшие комплекты.", "Upload stopped. Review the matching groups."),
    "All selected groups were skipped as duplicates.": ("Alle ausgewählten Pakete wurden als Duplikate übersprungen.", "Все выбранные комплекты пропущены как повторы.", "All selected groups were skipped as duplicates."),
    "Already in chat": ("Bereits im Chat", "Уже в чате", "Already in chat"),
    "Uploading": ("Wird gesendet", "Отправляется", "Uploading"),
    "Sent": ("Gesendet", "Отправлено", "Sent"),
    "Queued": ("In Warteschlange", "В очереди", "Queued"),
    "Partially sent": ("Teilweise gesendet", "Отправлено частично", "Partially sent"),
    "Check chat": ("Chat prüfen", "Проверьте чат", "Check chat"),
    "Error": ("Fehler", "Ошибка", "Error"),
    "Stage 2/3 · {title} · group {index}/{total}": ("Schritt 2/3 · {title} · Paket {index}/{total}", "Этап 2/3 · {title} · комплект {index}/{total}", "Stage 2/3 · {title} · group {index}/{total}"),
    "Group {index}/{total} · {name}": ("Paket {index}/{total} · {name}", "Комплект {index}/{total} · {name}", "Group {index}/{total} · {name}"),
    "Preparing · {name}": ("Vorbereitung · {name}", "Подготовка · {name}", "Preparing · {name}"),
    "Stage 2/3 · Sent groups {index}/{total}": ("Schritt 2/3 · Gesendete Pakete {index}/{total}", "Этап 2/3 · Отправлено комплектов {index}/{total}", "Stage 2/3 · Groups sent {index}/{total}"),
    "Group transferred to Telegram": ("Paket an Telegram übertragen", "Комплект передан Telegram", "Group transferred to Telegram"),
    "Stage 3/3 · Finishing upload": ("Schritt 3/3 · Upload wird abgeschlossen", "Этап 3/3 · Завершение отправки", "Stage 3/3 · Finishing upload"),
    "Video": ("Video", "Видео", "Video"),
    "Audio": ("Audio", "Аудио", "Audio"),
    "subtitles": ("Untertitel", "субтитры", "subtitles"),
    "Group {index}/{total} · {name}": ("Paket {index}/{total} · {name}", "Комплект {index}/{total} · {name}", "Group {index}/{total} · {name}"),
    "File uploaded to Telegram": ("Datei an Telegram übertragen", "Файл передан в Telegram", "File uploaded to Telegram"),
    "Done": ("Fertig", "Готово", "Done"),
    "In progress…": ("Wird ausgeführt…", "Выполнение…", "In progress…"),
    "Video": ("Video", "Видео", "Video"),
    "Audio": ("Audio", "Аудио", "Audio"),
    "B": ("B", "Б", "B"),
    "KB": ("KB", "КБ", "KB"),
    "MB": ("MB", "МБ", "MB"),
    "GB": ("GB", "ГБ", "GB"),
    "Row status": ("Status", "Статус", "Status"),
    "Queued": ("In Warteschlange", "В очереди", "Queued"),
    "Could not complete the operation": ("Vorgang konnte nicht abgeschlossen werden", "Не удалось выполнить операцию", "Could not complete the operation"),
    "Another Telegram operation is already running.": ("Ein anderer Telegram-Vorgang läuft bereits.", "Уже выполняется другая операция Telegram.", "Another Telegram operation is already running."),
    "Could not add profile": ("Profil konnte nicht hinzugefügt werden", "Не удалось добавить профиль", "Could not add profile"),
    "Cannot send": ("Vorgang nicht abgeschlossen.", "Операция не завершена.", "Operation did not complete."),
    "Stop after the current safe step…": ("Nach dem aktuellen sicheren Schritt stoppen…", "Останавливаю после текущего безопасного шага…", "Stopping after the current safe step…"),
    "Completed": ("Abgeschlossen", "Готово", "Completed"),
    "Select a folder": ("Ordner auswählen", "Выберите папку", "Select a folder"),
    "Upload confirmation": ("Upload bestätigen", "Подтвердить отправку", "Confirm upload"),
    "Send {count} group(s) to chat “{target}”?\n\n{names}\n\n{note}": ("{count} Paket(e) an den Chat „{target}“ senden?\n\n{names}\n\n{note}", "Отправить {count} комплект(а) в чат «{target}»?\n\n{names}\n\n{note}", "Send {count} group(s) to chat “{target}”?\n\n{names}\n\n{note}"),
    "Before sending, the app checks the chat history by file name and size. If it finds a match, it asks you to review the group first.": ("Vor dem Senden prüft die App den Chatverlauf anhand von Dateiname und Größe. Bei einem Treffer werden Sie gebeten, das Paket zuerst zu prüfen.", "Перед отправкой программа проверит историю чата по имени и размеру файлов. Если найдёт совпадения, сначала попросит перепроверить комплект.", "Before sending, the app checks chat history by file name and size. If it finds a match, it asks you to review the group first."),
    "Yes": ("Ja", "Да", "Yes"),
    "New Telegram profile": ("Neues Telegram-Profil", "Новый профиль Telegram", "New Telegram profile"),
    "Profile name": ("Profilname", "Название профиля", "Profile name"),
    "Telegram phone number": ("Telegram-Telefonnummer", "Телефон Telegram", "Telegram phone number"),
    "API ID": ("API-ID", "API ID", "API ID"),
    "API Hash": ("API-Hash", "API Hash", "API Hash"),
    "Get API ID and API Hash from my.telegram.org. The app will ask for your Telegram code and optional 2FA password separately. Only the authorized session is saved on this Mac.": ("API-ID und API-Hash finden Sie auf my.telegram.org. Die App fragt Ihren Telegram-Code und das optionale 2FA-Passwort getrennt ab. Auf diesem Mac wird nur die autorisierte Sitzung gespeichert.", "API ID и API Hash можно получить на my.telegram.org. Код Telegram и пароль 2FA приложение запросит отдельно. На этом Mac сохранится только авторизованная сессия.", "Get your API ID and API Hash from my.telegram.org. The app asks for your Telegram code and optional 2FA password separately. Only the authorized session is saved on this Mac."),
    "Save": ("Speichern", "Сохранить", "Save"),
    "Could not add profile: {message}": ("Profil konnte nicht hinzugefügt werden: {message}", "Не удалось добавить профиль: {message}", "Could not add profile: {message}"),
    "Review possible duplicates": ("Mögliche Duplikate prüfen", "Проверьте возможные дубликаты", "Review possible duplicates"),
    "The chat already contains files from these groups:": ("Der Chat enthält bereits Dateien aus diesen Paketen:", "В чате уже есть файлы из этих комплектов:", "The chat already contains files from these groups:"),
    "Duplicate matching uses file name and size. Spaces and underscores are treated as equal. You can skip complete groups, review manually, or send them again.": ("Duplikate werden anhand von Dateiname und Größe erkannt. Leerzeichen und Unterstriche gelten als gleich. Sie können ganze Pakete überspringen, manuell prüfen oder erneut senden.", "Совпадение проверяется по названию и размеру файла; пробелы и подчёркивания считаются одинаковыми. Можно пропустить целые комплекты, перепроверить вручную или отправить их снова.", "Duplicates are matched by file name and size. Spaces and underscores are treated as equal. You can skip complete groups, review manually, or send them again."),
    "Skip duplicates": ("Duplikate überspringen", "Пропустить повторы", "Skip duplicates"),
    "Send anyway": ("Trotzdem senden", "Отправить всё равно", "Send anyway"),
    "Cancel — I will review": ("Abbrechen — ich prüfe selbst", "Отменить — я проверю", "Cancel — I will review"),
    "{name}: {files}": ("{name}: {files}", "{name}: {files}", "{name}: {files}"),
    "• … and {count} more groups": ("• … und {count} weitere Pakete", "• … и ещё комплектов: {count}", "• … and {count} more groups"),
    "Finished": ("Fertig", "Готово", "Finished"),
    "Language": ("Sprache", "Язык", "Language"),
    "Invalid application data folder.": ("Ungültiger App-Datenordner.", "Недопустимая папка данных приложения.", "Invalid application data folder."),
    "Restart the app to apply the selected language.": ("Starte die App neu, um die ausgewählte Sprache zu übernehmen.", "Перезапустите программу, чтобы применить выбранный язык.", "Restart the app to apply the selected language."),
    "Language saved": ("Sprache gespeichert", "Язык сохранён", "Language saved"),
    "Select a regular folder containing files.": ("Wähle einen normalen Ordner mit Dateien aus.", "Выберите обычную папку с файлами.", "Select a regular folder containing files."),
    "Incomplete group: {name}; media {media}, Russian .ru.srt {russian}, German .srt {german}": ("Unvollständiges Paket: {name}; Medien {media}, russische .ru.srt {russian}, deutsche .srt {german}", "{name}: медиа {media}, русских .ru.srt {russian}, немецких .srt {german}", "Incomplete group: {name}; media {media}, Russian .ru.srt {russian}, German .srt {german}"),
    "Invalid Telegram profile folder.": ("Ungültiger Telegram-Profilordner.", "Небезопасная папка профилей Telegram.", "Invalid Telegram profile folder."),
    "Invalid Telegram sessions folder.": ("Ungültiger Telegram-Sitzungsordner.", "Небезопасная папка сессий Telegram.", "Invalid Telegram sessions folder."),
    "Invalid Telegram profiles file.": ("Ungültige Telegram-Profildatei.", "Небезопасный файл профилей Telegram.", "Invalid Telegram profiles file."),
    "Could not read local Telegram profiles.": ("Lokale Telegram-Profile konnten nicht gelesen werden.", "Не удалось прочитать локальные профили Telegram.", "Could not read local Telegram profiles."),
    "The local Telegram profiles file is damaged.": ("Die Datei mit lokalen Telegram-Profilen ist beschädigt.", "Файл локальных профилей Telegram повреждён.", "The local Telegram profiles file is damaged."),
    "Enter a profile name, phone, numeric API ID, and API Hash.": ("Geben Sie Profilname, Telefonnummer, numerische API-ID und API-Hash ein.", "Укажите имя профиля, телефон, числовой API ID и API Hash.", "Enter a profile name, phone number, numeric API ID, and API Hash."),
    "A profile with this phone number already exists.": ("Ein Profil mit dieser Telefonnummer existiert bereits.", "Профиль с таким номером уже добавлен.", "A profile with this phone number already exists."),
    "Invalid Telegram profile session folder.": ("Ungültiger Telegram-Sitzungsordner des Profils.", "Небезопасная папка профиля Telegram.", "Invalid Telegram profile session folder."),
    "Invalid Telegram session file.": ("Ungültige Telegram-Sitzungsdatei.", "Небезопасный файл сессии Telegram.", "Invalid Telegram session file."),
    "Telegram rejected the API ID or API Hash. Check the profile.": ("Telegram hat API-ID oder API-Hash abgelehnt. Prüfen Sie das Profil.", "Telegram отклонил API ID или API Hash. Проверьте профиль.", "Telegram rejected the API ID or API Hash. Check the profile."),
    "The Telegram code is invalid or expired. Try signing in again.": ("Der Telegram-Code ist ungültig oder abgelaufen. Melden Sie sich erneut an.", "Код Telegram неверный или устарел. Повторите вход.", "The Telegram code is invalid or expired. Try signing in again."),
    "The two-step verification password is incorrect.": ("Das Passwort für die Zwei-Schritt-Verifizierung ist falsch.", "Пароль двухэтапной проверки неверен.", "The two-step verification password is incorrect."),
    "You cannot send messages to this chat.": ("Sie können keine Nachrichten an diesen Chat senden.", "Вы не можете отправлять сообщения в этот чат.", "You cannot send messages to this chat."),
    "Telegram requests a pause before trying again.": ("Telegram verlangt eine Wartezeit vor dem nächsten Versuch.", "Telegram просит подождать перед повторной попыткой.", "Telegram requests a pause before trying again."),
    "Could not access local data. Check folder permissions.": ("Lokale Daten sind nicht zugänglich. Prüfen Sie die Ordnerrechte.", "Не удалось открыть локальные данные. Проверьте права доступа к папке.", "Could not access local data. Check folder permissions."),
    "Could not connect to Telegram. Check the internet connection.": ("Verbindung zu Telegram fehlgeschlagen. Prüfen Sie die Internetverbindung.", "Не удалось подключиться к Telegram. Проверьте интернет-соединение.", "Could not connect to Telegram. Check the internet connection."),
    "Telegram could not complete the request. Check your connection and account.": ("Telegram konnte die Anfrage nicht abschließen. Prüfen Sie Verbindung und Konto.", "Telegram не смог выполнить запрос. Проверьте подключение и аккаунт.", "Telegram could not complete the request. Check your connection and account."),
}

CATALOG.update({
    "Extra subtitles for {name}: all {count} matching subtitle files will be sent.": (
        "Mehrere Untertitel für {name}: Alle {count} passenden Untertiteldateien werden gesendet.",
        "Для комплекта {name} найдено несколько субтитров: будут отправлены все {count} подходящих файлов.",
        "Extra subtitles for {name}: all {count} matching subtitle files will be sent."),
    "Some groups contain extra subtitles; every matching subtitle file will be sent.": (
        "Einige Pakete enthalten zusätzliche Untertitel; alle passenden Untertiteldateien werden gesendet.",
        "В некоторых комплектах есть дополнительные субтитры: будут отправлены все подходящие файлы.",
        "Some groups contain extra subtitles; every matching subtitle file will be sent."),
    "Profiles…": ("Profile…", "Профили…", "Profiles…"),
    "Telegram profiles": ("Telegram-Profile", "Профили Telegram", "Telegram profiles"),
    "Profiles stored by this app": ("Profile dieser App", "Данные новой программы", "Profiles stored by this app"),
    "Add…": ("Hinzufügen…", "Добавить…", "Add…"),
    "Delete…": ("Löschen…", "Удалить…", "Delete…"),
    "Close": ("Schließen", "Закрыть", "Close"),
    "Delete": ("Löschen", "Удалить", "Delete"),
    "Save": ("Speichern", "Сохранить", "Save"),
    "OK": ("OK", "ОК", "OK"),
    "Delete Telegram profile": ("Telegram-Profil löschen", "Удалить профиль Telegram", "Delete Telegram profile"),
    "Delete profile “{name}” and its local session from this app?": (
        "Profil „{name}“ und seine lokale Sitzung aus dieser App löschen?",
        "Удалить профиль «{name}» и его локальную сессию из этой программы?",
        "Delete profile “{name}” and its local session from this app?"),
    "Telegram messages, source media, and profiles in the old app remain unchanged.": (
        "Telegram-Nachrichten, Originaldateien und Profile der alten App bleiben erhalten.",
        "Сообщения Telegram, исходные файлы и профили старой программы сохранятся.",
        "Telegram messages, source media, and profiles in the old app remain unchanged."),
    "Could not delete profile": ("Profil konnte nicht gelöscht werden", "Не удалось удалить профиль", "Could not delete profile"),
    "Telegram profile was not found.": ("Telegram-Profil wurde nicht gefunden.", "Профиль Telegram не найден.", "Telegram profile was not found."),
    "Could not delete the Telegram profile session.": (
        "Telegram-Profilsitzung konnte nicht gelöscht werden.",
        "Не удалось удалить локальную сессию Telegram.",
        "Could not delete the Telegram profile session."),
    "Profile migration failed": ("Profilübernahme fehlgeschlagen", "Не удалось перенести профили", "Profile migration failed"),
})

CATALOG.update({
    "Media groups": ("Medienpakete", "Медиакомплекты", "Media groups"),
    "Study by week": ("Nach Wochen lernen", "Учёба по неделям", "Study by week"),
    "Choose study folder…": ("Lernordner auswählen…", "Выбрать папку с учёбой…", "Choose study folder…"),
    "Select weeks and days": ("Wochen und Tage auswählen", "Выберите недели и дни", "Select weeks and days"),
    "Week / materials": ("Woche / Materialien", "Неделя / материалы", "Week / materials"),
    "Contents": ("Inhalt", "Содержимое", "Contents"),
    "Size": ("Größe", "Размер", "Size"),
    "Status": ("Status", "Статус", "Status"),
    "Week materials": ("Wochenmaterialien", "Материалы недели", "Week materials"),
    "Audio and video": ("Audio und Video", "Аудио и видео", "Audio and video"),
    "Additional materials": ("Zusatzmaterial", "Дополнительные материалы", "Additional materials"),
    "Other materials": ("Weitere Materialien", "Прочие материалы", "Other materials"),
    "Waiting": ("Wartet", "Ожидает", "Waiting"),
    "days": ("Tage", "дней", "days"),
    "{count} file": ("{count} Datei", "{count} файл", "{count} file"),
    "{count} files few": ("{count} Dateien", "{count} файла", "{count} files"),
    "{count} files": ("{count} Dateien", "{count} файлов", "{count} files"),
    "Selected: {weeks} weeks · {days} days · {size}": (
        "Ausgewählt: {weeks} Wochen · {days} Tage · {size}",
        "Выбрано: {weeks} недель · {days} дней · {size}",
        "Selected: {weeks} weeks · {days} days · {size}"),
    "Scan complete: {weeks} weeks, {days} days": (
        "Scan abgeschlossen: {weeks} Wochen, {days} Tage",
        "Сканирование завершено: недель — {weeks}, дней — {days}",
        "Scan complete: {weeks} weeks, {days} days"),
    "Scanning weekly folder…": ("Wochenordner wird gescannt…", "Сканирую папку с неделями…", "Scanning weekly folder…"),
    "Choose a folder with weekly materials.": (
        "Wählen Sie einen Ordner mit Wochenmaterialien.", "Выберите папку с материалами по неделям.",
        "Choose a folder with weekly materials."),
    "Problems": ("Probleme", "Проблемы", "Problems"),
    "Excluded hidden files": ("Verborgene Dateien ausgeschlossen", "Скрытые файлы исключены", "Hidden files excluded"),
    "Check and send": ("Prüfen und senden", "Проверить и отправить", "Check and send"),
    "Import publication plan…": ("Veröffentlichungsplan importieren…", "Импортировать план публикации…", "Import publication plan…"),
    "Publication plans (*.json);;JSON files (*.json)": ("Veröffentlichungspläne (*.json);;JSON-Dateien (*.json)", "Планы публикации (*.json);;Файлы JSON (*.json)", "Publication plans (*.json);;JSON files (*.json)"),
    "Preview publication plan": ("Veröffentlichungsplan-Vorschau", "Предпросмотр плана публикации", "Preview publication plan"),
    "Use this plan": ("Diesen Plan verwenden", "Использовать этот план", "Use this plan"),
    "Publication plan: project {project}, revision {revision}": (
        "Veröffentlichungsplan: Projekt {project}, Revision {revision}",
        "План публикации: проект {project}, редакция {revision}",
        "Publication plan: project {project}, revision {revision}"),
    "Imported {items} messages · {size}": (
        "{items} Nachrichten importiert · {size}", "Импортировано: {items} · {size}", "Imported {items} messages · {size}"),
    "Publication plan is ready: project {project}, revision {revision}": (
        "Veröffentlichungsplan bereit: Projekt {project}, Revision {revision}",
        "План готов: проект {project}, редакция {revision}",
        "Publication plan is ready: project {project}, revision {revision}"),
    "Imported plan: {filename}": ("Importierter Plan: {filename}", "Импортирован план: {filename}", "Imported plan: {filename}"),
    "Validating publication plan and file checksums…": (
        "Veröffentlichungsplan und Prüfsummen werden geprüft…",
        "Проверяю план публикации и контрольные суммы файлов…",
        "Validating publication plan and file checksums…"),
    "Publication plan preview cancelled.": (
        "Vorschau des Veröffentlichungsplans abgebrochen.", "Предпросмотр плана отменён.",
        "Publication plan preview cancelled."),
    "Publication order": ("Veröffentlichungsreihenfolge", "Порядок публикации", "Publication order"),
    "Type / date": ("Typ / Datum", "Тип / дата", "Type / date"),
    "File": ("Datei", "Файл", "File"),
    "Cannot import publication plan": ("Veröffentlichungsplan kann nicht importiert werden", "Не удалось импортировать план публикации", "Cannot import publication plan"),
    "The plan version, file paths, sizes, or checksums are invalid.": (
        "Version, Dateipfade, Größen oder Prüfsummen des Plans sind ungültig.",
        "Версия, пути, размеры или контрольные суммы в плане недействительны.",
        "The plan version, file paths, sizes, or checksums are invalid."),
    "Imported plan files were revalidated.": (
        "Importierte Dateien wurden erneut geprüft.", "Файлы импортированного плана проверены повторно.",
        "Imported plan files were revalidated."),
    "Use Import publication plan… to load a publication plan.": (
        "Importieren Sie über „Veröffentlichungsplan importieren…“ einen Plan.",
        "Нажмите «Импортировать план публикации…», чтобы загрузить план.",
        "Use Import publication plan… to load a publication plan."),
    "Review upload plan": ("Uploadplan prüfen", "Проверка и план отправки", "Review upload plan"),
    "Profile: <b>{profile}</b> · Chat: <b>{chat}</b> · Selected: <b>{weeks} weeks, {days} days</b>": (
        "Profil: <b>{profile}</b> · Chat: <b>{chat}</b> · Ausgewählt: <b>{weeks} Wochen, {days} Tage</b>",
        "Профиль: <b>{profile}</b> · Чат: <b>{chat}</b> · Выбрано: <b>{weeks} недели, {days} дней</b>",
        "Profile: <b>{profile}</b> · Chat: <b>{chat}</b> · Selected: <b>{weeks} weeks, {days} days</b>"),
    "To send: {messages} messages, {files} files, {size}": (
        "Zu senden: {messages} Nachrichten, {files} Dateien, {size}",
        "К отправке: {messages} сообщений, {files} файлов, {size}",
        "To send: {messages} messages, {files} files, {size}"),
    "Already found in chat: {count}": ("Bereits im Chat gefunden: {count}", "Уже найдено в чате: {count}", "Already found in chat: {count}"),
    "Upload order": ("Reihenfolge", "Порядок отправки", "Upload order"),
    "Text message": ("Textnachricht", "Текстовое сообщение", "Text message"),
    "Back": ("Zurück", "Назад", "Back"),
    "Start upload": ("Upload starten", "Начать отправку", "Start upload"),
    "Preparing weekly upload…": ("Wochen-Upload wird vorbereitet…", "Подготавливаю отправку по неделям…", "Preparing weekly upload…"),
    "Checking the Telegram chat…": ("Telegram-Chat wird geprüft…", "Проверяю чат Telegram…", "Checking the Telegram chat…"),
    "Uploading weekly materials…": ("Wochenmaterialien werden gesendet…", "Отправляю материалы по неделям…", "Uploading weekly materials…"),
    "Waiting for network; will retry in {seconds}s": ("Warten auf Netzwerk; neuer Versuch in {seconds}s", "Ожидание сети; повтор через {seconds} с", "Waiting for network; will retry in {seconds}s"),
    "Telegram asked to wait {seconds} seconds before continuing.": (
        "Telegram verlangt eine Wartezeit von {seconds} Sekunden.",
        "Telegram просит подождать {seconds} секунд перед продолжением.",
        "Telegram asked to wait {seconds} seconds before continuing."),
    "Weekly upload complete: {sent} sent, {skipped} already in chat": (
        "Wochen-Upload fertig: {sent} gesendet, {skipped} bereits im Chat",
        "Отправка завершена: отправлено {sent}, уже были в чате — {skipped}",
        "Weekly upload complete: {sent} sent, {skipped} already in chat"),
    "Upload interrupted. Its progress is saved; you can continue later.": (
        "Upload unterbrochen. Fortschritt gespeichert; Sie können später fortsetzen.",
        "Отправка прервана. Прогресс сохранён, можно продолжить позже.",
        "Upload interrupted. Its progress is saved; you can continue later."),
    "Stop weekly upload?": ("Wochen-Upload stoppen?", "Остановить отправку?", "Stop weekly upload?"),
    "Choose when to stop the queue.": ("Wählen Sie, wann die Warteschlange stoppt.", "Выберите, когда остановить очередь.", "Choose when to stop the queue."),
    "Finish the current file": ("Aktuelle Datei fertig senden", "Дождаться текущего файла", "Finish the current file"),
    "Interrupt current transfer now": ("Aktuelle Übertragung sofort abbrechen", "Прервать передачу сейчас", "Interrupt current transfer now"),
    "Continue upload": ("Upload fortsetzen", "Продолжить загрузку", "Continue upload"),
    "Continue saved upload": ("Gespeicherten Upload fortsetzen", "Продолжить сохранённую отправку", "Continue saved upload"),
    "Continue saved upload · {chat} · {count} items": (
        "Gespeicherten Upload fortsetzen · {chat} · {count} Elemente",
        "Продолжить сохранённую отправку · {chat} · {count} элементов",
        "Continue saved upload · {chat} · {count} items"),
    "Unknown chat": ("Unbekannter Chat", "Неизвестный чат", "Unknown chat"),
    "Choose the original Telegram profile and chat to continue this saved queue.": (
        "Wählen Sie das ursprüngliche Telegram-Profil und den Chat, um diese Warteschlange fortzusetzen.",
        "Чтобы продолжить сохранённую очередь, выберите исходные профиль Telegram и чат.",
        "Choose the original Telegram profile and chat to continue this saved queue."),
    "Select a Telegram profile and chat first.": (
        "Wählen Sie zuerst ein Telegram-Profil und einen Chat aus.",
        "Сначала выберите профиль Telegram и чат.",
        "Select a Telegram profile and chat first."),
    "Stop": ("Stoppen", "Остановить", "Stop"),
    "Type / size": ("Typ / Größe", "Тип / размер", "Type / size"),
    "A Telegram operation is still running. Stop and close after it finishes?": (
        "Ein Telegram-Vorgang läuft noch. Stoppen und nach dem Ende schließen?",
        "Операция Telegram ещё выполняется. Остановить и закрыть после завершения?",
        "A Telegram operation is still running. Stop and close after it finishes?"),
    "Folder changed during upload; the active queue is unchanged.": (
        "Ordner während des Uploads geändert; die aktive Warteschlange bleibt unverändert.",
        "Папка изменилась во время отправки; активная очередь не меняется.",
        "Folder changed during upload; the active queue is unchanged."),
    "Folder changed": ("Ordner geändert", "Папка изменилась", "Folder changed"),
    "The folder changed during upload. Refresh it now?": (
        "Der Ordner wurde während des Uploads geändert. Jetzt aktualisieren?",
        "Папка изменилась во время отправки. Обновить её сейчас?",
        "The folder changed during upload. Refresh it now?"),
    "Review chat-history matches": ("Treffer im Chatverlauf prüfen", "Проверка совпадений в чате", "Review chat-history matches"),
    "Some items match more than one chat-history result. Choose an action for each row.": (
        "Einige Elemente passen zu mehreren Treffern. Wählen Sie für jede Zeile eine Aktion.",
        "Некоторые материалы совпали с несколькими сообщениями. Выберите действие для каждой строки.",
        "Some items match more than one chat-history result. Choose an action for each row."),
    "File / message": ("Datei / Nachricht", "Файл / сообщение", "File / message"),
    "Matches": ("Treffer", "Совпадений", "Matches"),
    "Action": ("Aktion", "Действие", "Action"),
    "Choose an action…": ("Aktion auswählen…", "Выберите действие…", "Choose an action…"),
    "Send this item": ("Dieses Element senden", "Отправить этот материал", "Send this item"),
    "Mark as found in chat · message {id}": ("Im Chat gefunden · Nachricht {id}", "Найдено в чате · сообщение {id}", "Mark as found in chat · message {id}"),
    "Cancel upload": ("Upload abbrechen", "Отменить отправку", "Cancel upload"),
    "Apply choices": ("Auswahl übernehmen", "Применить выбор", "Apply choices"),
    "Choose an action for every row.": ("Wählen Sie für jede Zeile eine Aktion.", "Выберите действие для каждой строки.", "Choose an action for every row."),
    "Use each Telegram message only once.": ("Jede Telegram-Nachricht darf nur einmal verwendet werden.", "Одно сообщение Telegram можно использовать только один раз.", "Use each Telegram message only once."),
})

# Catalog values are ordered German, Russian, English.
_INDEX = {"de": 0, "ru": 1, "en": 2}


def normalize_language(language: str | None) -> str:
    code = (language or "").lower().replace("_", "-").split("-", 1)[0]
    return code if code in LANGUAGES else "en"


def system_language() -> str:
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"],
                capture_output=True, text=True, check=True, timeout=2,
            )
            preferred = re.search(r"[\"']?([A-Za-z]{2,3}(?:[-_][A-Za-z]{2,4})?)[\"']?", result.stdout)
            if preferred:
                return normalize_language(preferred.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
    return normalize_language(QLocale.system().name())


def tr(key: str, language: str | None = None, **values) -> str:
    code = normalize_language(language)
    row = CATALOG.get(key)
    value = row[_INDEX[code]] if row else key
    return value.format(**values) if values else value
